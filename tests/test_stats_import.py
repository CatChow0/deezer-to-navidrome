import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, stats_db, stats_import
from core.stats_import import ImportRefused, run_import, same_play, source_status
from tests.fixtures import make_maloja, make_navidrome


class ImportCase(unittest.TestCase):
    def setUp(self):
        self.src = Path(tempfile.mkdtemp(prefix="d2n-src-"))
        self.nav = self.src / "navidrome.db"
        self.mal = self.src / "malojadb.sqlite"
        env = {"STATS_NAVIDROME_DB": str(self.nav), "STATS_MALOJA_DB": str(self.mal)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.src, True)
        data = Path(config.DATA_DIR)
        for item in data.glob("stats.db*"):
            item.unlink()
        shutil.rmtree(data / "stats_sources", True)
        if Path(config.LIBRARY_CACHE_FILE).exists():
            Path(config.LIBRARY_CACHE_FILE).unlink()
        stats_import._library_cache.clear()

    def rows(self):
        conn = stats_db.connect("nd1")
        try:
            return conn.execute(
                "SELECT p.listened_at ts, t.title, t.artist_display artists, a.title album, p.duration_sec duration, p.source"
                " FROM plays p JOIN tracks t ON t.id=p.track_id LEFT JOIN albums a ON a.id=p.album_id ORDER BY p.listened_at"
            ).fetchall()
        finally:
            conn.close()

    def count(self):
        return len(self.rows())


class SamePlay(unittest.TestCase):
    def test_same_play_rules(self):
        self.assertTrue(same_play(100, "a|x", "X", 103, "b|y", "Y"))        # within 5 s, any title
        self.assertTrue(same_play(100, "a|x", "X", 200, "a|x", "X"))        # 120 s, same key
        self.assertTrue(same_play(100, "a|love galore", "Love Galore", 200, "b|love galore feat", "Love Galore Feat"))  # similar title
        self.assertFalse(same_play(100, "a|x", "Abc", 200, "b|y", "Zzz"))   # 120 s, different
        self.assertFalse(same_play(100, "a|x", "X", 221, "a|x", "X"))       # beyond 120 s


class Merging(ImportCase):
    def test_merge_retitled_maloja_play_counts_once(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Love Galore (feat. Travis Scott)", "artists": ["SZA", "Travis Scott"]}])
        make_maloja(self.mal, [{"ts": 1000, "title": "Love Galore", "artist": "SZA"}])
        report = run_import("nd1", "merge")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Love Galore (feat. Travis Scott)")
        self.assertEqual(report["from_maloja"], 0)

    def test_maloja_only_play_is_kept(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        make_maloja(self.mal, [{"ts": 9000, "title": "Two"}])
        report = run_import("nd1", "merge")
        self.assertEqual(report["from_maloja"], 1)
        self.assertEqual(report["maloja_only"], 1)
        self.assertEqual(self.count(), 2)

    def test_navidrome_exact_duplicates_dropped(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}, {"ts": 1000, "title": "One"}])
        run_import("nd1", "merge")
        self.assertEqual(self.count(), 1)

    def test_real_repeats_are_not_merged(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}, {"ts": 1020, "title": "One"}])
        run_import("nd1", "merge")
        self.assertEqual(self.count(), 2)

    def test_each_play_matches_once(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "A"}, {"ts": 1003, "title": "B"}])
        make_maloja(self.mal, [{"ts": 1001, "title": "A"}, {"ts": 1004, "title": "B"}, {"ts": 1005, "title": "C"}])
        report = run_import("nd1", "merge")
        # C has no partner left: both nearby Navidrome plays are already taken.
        self.assertEqual(self.count(), 3)
        self.assertEqual(report["from_maloja"], 1)

    def test_an_import_reviews_the_quarantine(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        with mock.patch("core.mix_builder.review_quarantine") as review:
            run_import("nd1", "merge")
        review.assert_called_once()

    def test_a_preview_does_not(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        with mock.patch("core.mix_builder.review_quarantine") as review:
            run_import("nd1", "clean", dry_run=True)
        review.assert_not_called()

    def test_a_failed_review_does_not_fail_the_import(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        with mock.patch("core.mix_builder.review_quarantine", side_effect=OSError("disk")):
            self.assertEqual(run_import("nd1", "merge")["after"], 1)

    def test_import_twice_same_totals(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}, {"ts": 2000, "title": "Two"}])
        make_maloja(self.mal, [{"ts": 1000, "title": "One"}, {"ts": 9000, "title": "Three"}])
        first = run_import("nd1", "merge")
        second = run_import("nd1", "merge")
        self.assertEqual(first["after"], 3)
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["after"], 3)

    def test_merge_keeps_app_only_plays(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        conn = stats_db.connect("nd1")
        stats_db.add_play(conn, stats_db.upsert_track(conn, "Live one", ["X"]), None, 100, 50000, "live")
        conn.commit()
        conn.close()
        run_import("nd1", "merge")
        self.assertEqual(self.count(), 2)

    def test_merge_never_deletes_after_source_shrinks(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}, {"ts": 2000, "title": "Two"}])
        run_import("nd1", "merge")
        self.nav.unlink()
        make_navidrome(self.nav, [{"ts": 2000, "title": "Two"}])
        report = run_import("nd1", "merge")
        self.assertEqual(self.count(), 2)
        self.assertEqual(report["removed"], 0)

    def test_retag_is_not_double_counted(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Old name", "file": "f1"}])
        run_import("nd1", "merge")
        self.nav.unlink()
        make_navidrome(self.nav, [{"ts": 1000, "title": "New name", "file": "f1"}])
        run_import("nd1", "merge")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "New name")
        conn = stats_db.connect("nd1")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0], 1)
        conn.close()

    def test_live_then_navidrome_same_timestamp(self):
        conn = stats_db.connect("nd1")
        stats_db.add_play(conn, stats_db.upsert_track(conn, "One", ["Artist"]), None, None, 1000, "live")
        conn.commit()
        conn.close()
        make_navidrome(self.nav, [{"ts": 1000, "title": "One", "duration": 180}])
        run_import("nd1", "merge")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["source"], rows[0]["duration"]), ("navidrome", 180))

    def test_per_play_album_and_length_kept(self):
        make_navidrome(self.nav, [
            {"ts": 1000, "title": "One", "album": "A", "duration": 100, "file": "f1"},
            {"ts": 2000, "title": "One", "album": "B", "duration": 130, "file": "f2"},
        ])
        run_import("nd1", "merge")
        self.assertEqual([(r["album"], r["duration"]) for r in self.rows()], [("A", 100), ("B", 130)])

    def test_offset_maloja_play_of_same_track_counts_once(self):
        # Seen on real data: Maloja's clock 2-3 minutes off Navidrome's for an evening.
        make_navidrome(self.nav, [{"ts": 1000, "title": "Sugar"}, {"ts": 1300, "title": "Oh Dove"}])
        make_maloja(self.mal, [{"ts": 1170, "title": "Sugar"}, {"ts": 1470, "title": "Oh Dove"}])
        report = run_import("nd1", "merge")
        self.assertEqual(self.count(), 2)
        self.assertEqual(report["from_maloja"], 0)

    def test_real_replay_in_maloja_is_kept(self):
        # The Navidrome play is already paired with the exact Maloja play.
        make_navidrome(self.nav, [{"ts": 1000, "title": "Sugar"}])
        make_maloja(self.mal, [{"ts": 1000, "title": "Sugar"}, {"ts": 1300, "title": "Sugar"}])
        report = run_import("nd1", "merge")
        self.assertEqual(self.count(), 2)
        self.assertEqual(report["from_maloja"], 1)

    def test_far_apart_same_track_stays_separate(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Sugar"}])
        make_maloja(self.mal, [{"ts": 1000 + 601, "title": "Sugar"}])
        run_import("nd1", "merge")
        self.assertEqual(self.count(), 2)

    def test_offset_maloja_play_stays_merged_on_second_run(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Sugar"}])
        make_maloja(self.mal, [{"ts": 1170, "title": "Sugar"}])
        run_import("nd1", "merge")
        self.assertEqual(run_import("nd1", "merge")["added"], 0)

    def test_maloja_combined_artist_is_split(self):
        make_maloja(self.mal, [{"ts": 1000, "title": "One", "artists": ["Vald • Todiefor"]}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        self.assertEqual([r[0] for r in conn.execute("SELECT name FROM artists ORDER BY name")], ["Todiefor", "Vald"])
        conn.close()

    def test_new_key_rule_merges_tracks_and_moves_plays(self):
        conn = stats_db.connect("nd1")
        one = stats_db.upsert_track(conn, "Song", ["A"])
        two = stats_db.upsert_track(conn, "Song 2", ["A"])
        stats_db.add_play(conn, one, None, None, 1000, "live")
        stats_db.add_play(conn, two, None, None, 2000, "live")
        conn.execute("UPDATE tracks SET key='stale-key' WHERE id=?", (two,))
        conn.execute("UPDATE tracks SET title='Song' WHERE id=?", (two,))
        conn.commit()
        conn.close()
        make_navidrome(self.nav, [{"ts": 9000, "title": "Other"}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        titles = [r[0] for r in conn.execute(
            "SELECT t.title FROM plays p JOIN tracks t ON t.id=p.track_id WHERE p.listened_at IN (1000, 2000)")]
        self.assertEqual(titles, ["Song", "Song"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tracks WHERE title='Song'").fetchone()[0], 1)
        conn.close()


class StartClean(ImportCase):
    def test_clean_removes_app_only_plays(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        stats_db.add_play(conn, stats_db.upsert_track(conn, "Live", ["X"]), None, None, 50000, "live")
        conn.commit()
        conn.close()
        report = run_import("nd1", "clean")
        self.assertEqual(self.count(), 1)
        self.assertEqual(report["removed"], 1)

    def test_clean_refused_without_navidrome(self):
        make_maloja(self.mal, [{"ts": 1000, "title": "One"}])
        run_import("nd1", "merge")
        with self.assertRaises(ImportRefused):
            run_import("nd1", "clean")
        self.assertEqual(self.count(), 1)
        self.assertFalse(source_status("nd1")["can_clean"])

    def test_merge_refused_with_no_sources(self):
        with self.assertRaises(ImportRefused):
            run_import("nd1", "merge")
        self.assertFalse(source_status("nd1")["can_merge"])

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            run_import("nd1", "everything")


class Failures(ImportCase):
    def seed(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        run_import("nd1", "merge")
        before = stats_db.connect("nd1")
        report = stats_db.get_meta(before, "last_import")
        before.close()
        return report

    def test_failed_import_changes_nothing(self):
        report = self.seed()
        self.nav.unlink()
        make_navidrome(self.nav, [{"ts": 2000, "title": "Two"}, {"ts": 3000, "title": "Three"}])
        with mock.patch.object(stats_import, "_fill_lengths", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                run_import("nd1", "merge")
        self.assertEqual(self.count(), 1)
        conn = stats_db.connect("nd1")
        self.assertEqual(stats_db.get_meta(conn, "last_import"), report)
        conn.close()

    def test_damaged_source_clear_error(self):
        self.seed()
        self.nav.unlink()
        self.nav.write_bytes(b"this is not a database" * 100)
        with self.assertRaisesRegex(ImportRefused, "(?i)navidrome"):
            run_import("nd1", "merge")
        self.assertEqual(self.count(), 1)

    def test_changed_navidrome_schema_clear_error(self):
        conn = sqlite3.connect(self.nav)
        conn.execute("CREATE TABLE media_file (id TEXT)")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(ImportRefused, "scrobbles"):
            run_import("nd1", "merge")

    def test_changed_navidrome_column_clear_error(self):
        conn = sqlite3.connect(self.nav)
        conn.execute("CREATE TABLE media_file (id TEXT)")
        conn.execute("CREATE TABLE scrobbles (media_file_id TEXT, user_id TEXT, submission_time INTEGER)")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(ImportRefused, "media_file"):
            run_import("nd1", "merge")

    def test_a_navidrome_without_users_in_its_plays_is_refused(self):
        # Without scrobbles.user_id, one user's plays cannot be told from another's.
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        conn = sqlite3.connect(self.nav)
        conn.executescript("CREATE TABLE s2 AS SELECT id, media_file_id, submission_time FROM scrobbles;"
                           " DROP TABLE scrobbles; ALTER TABLE s2 RENAME TO scrobbles;")
        conn.close()
        with self.assertRaisesRegex(ImportRefused, "user_id"):
            run_import("nd1", "merge")

    def test_temp_copies_are_removed(self):
        self.seed()
        leftovers = [p.name for p in Path(config.DATA_DIR).iterdir() if p.name.startswith("stats_import")]
        self.assertEqual(leftovers, [])


class Backups(ImportCase):
    def test_backups_keep_last_three(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        for _ in range(5):
            run_import("nd1", "merge")
        backups = list(Path(config.DATA_DIR).glob("stats.db.bak-*"))
        self.assertEqual(len(backups), 3)
        conn = sqlite3.connect(sorted(backups)[-1])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0], 1)
        conn.close()

    def test_report_names_the_backup(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        report = run_import("nd1", "merge")
        self.assertTrue((Path(config.DATA_DIR) / report["backup"]).exists())


class MalojaCopy(ImportCase):
    def test_maloja_copy_kept_then_used(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        make_maloja(self.mal, [{"ts": 9000, "title": "Only in Maloja"}])
        run_import("nd1", "merge")
        self.mal.unlink()
        status = source_status("nd1")
        self.assertFalse(status["maloja"]["found"])
        self.assertTrue(status["maloja"]["kept_copy"])
        report = run_import("nd1", "clean")
        self.assertEqual(report["maloja_only"], 1)
        self.assertEqual(self.count(), 2)

    def test_smaller_maloja_does_not_replace_copy(self):
        make_maloja(self.mal, [{"ts": 1000, "title": "One"}, {"ts": 2000, "title": "Two"}])
        run_import("nd1", "merge")
        self.mal.unlink()
        make_maloja(self.mal, [{"ts": 1000, "title": "One"}])
        run_import("nd1", "merge")
        kept = sqlite3.connect(Path(config.DATA_DIR) / "stats_sources" / "malojadb.sqlite")
        self.assertEqual(kept.execute("SELECT COUNT(*) FROM scrobbles").fetchone()[0], 2)
        kept.close()


class Metadata(ImportCase):
    def test_junk_genres_ignored(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One", "genres": ["125", "<unknown>", "Rap"]}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        self.assertEqual(conn.execute("SELECT genre FROM tracks").fetchone()[0], "Rap")
        conn.close()

    def test_participants_split_artists(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One", "artists": ["A", "B"]}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        self.assertEqual([r[0] for r in conn.execute("SELECT name FROM artists ORDER BY name")], ["A", "B"])
        conn.close()

    def test_length_from_library_index(self):
        make_maloja(self.mal, [{"ts": 1000, "title": "One", "artist": "A"}])
        Path(config.LIBRARY_CACHE_FILE).write_text(json.dumps(
            {"library": [{"tag_artist": "A", "tag_title": "One", "duration": 210.0, "path": "/x"}]}), encoding="utf-8")
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        row = conn.execute("SELECT duration_sec, duration_source FROM tracks").fetchone()
        self.assertEqual((row["duration_sec"], row["duration_source"]), (210.0, "library"))
        conn.close()

    def test_wal_plays_are_read(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        live = sqlite3.connect(self.nav)
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("PRAGMA wal_autocheckpoint=0")
        live.execute("INSERT INTO scrobbles(media_file_id, user_id, submission_time) VALUES ('Artist/One', 'u', 5000)")
        live.commit()
        self.assertTrue(Path(str(self.nav) + "-wal").stat().st_size > 0)
        run_import("nd1", "merge")
        live.close()
        self.assertEqual(self.count(), 2)


if __name__ == "__main__":
    unittest.main()
