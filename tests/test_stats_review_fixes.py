"""Findings of the whole-branch review, each pinned by the case that showed it."""
import os
import sqlite3
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from core import config, stats_db, stats_enrich, stats_import, stats_ingest
from core.stats_db import track_key
from core.stats_import import ImportRefused, run_import
from core.stats_queries import recap, search_plays
from tests.fixtures import make_maloja, make_navidrome
from tests.test_stats_db import reset
from tests.test_stats_import import ImportCase

NOW = int(time.time())


def stamp(year, month, day):
    return int(datetime(year, month, day, 12, tzinfo=timezone.utc).timestamp())


def replace_nav(case, plays):
    case.nav.unlink()
    make_navidrome(case.nav, plays)


def add_live(ts, title="One", artists=("Artist",), album=None, album_artist=None, duration=None):
    conn = stats_db.connect()
    track = stats_db.upsert_track(conn, title, list(artists))
    stats_db.add_play(conn, track, stats_db.upsert_album(conn, album, album_artist), duration, ts, "live")
    conn.commit()
    conn.close()


class DoubleCounting(ImportCase):
    def totals(self, runs=3):
        return [run_import("merge")["after"] for _ in range(runs)]

    def test_maloja_first_then_navidrome_stays_one_play(self):
        make_maloja(self.mal, [{"ts": 1060, "title": "One"}])
        run_import("merge")
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        self.assertEqual(self.totals(), [1, 1, 1])
        self.assertEqual(self.rows()[0]["ts"], 1000)

    def test_live_play_off_by_seconds_stays_one_play(self):
        add_live(1003)
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        self.assertEqual(self.totals(), [1, 1, 1])

    def test_repeat_with_only_later_play_live(self):
        add_live(1100)
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}, {"ts": 1100, "title": "One"}])
        self.assertEqual(self.totals(), [2, 2, 2])

    def test_maloja_first_then_navidrome_minutes_apart(self):
        make_maloja(self.mal, [{"ts": 1300, "title": "One"}])
        run_import("merge")
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        self.assertEqual(self.totals(), [1, 1, 1])

    def test_retag_with_drifted_maloja_partner(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Old name", "file": "f1"}])
        make_maloja(self.mal, [{"ts": 1060, "title": "Old name"}])
        run_import("merge")
        replace_nav(self, [{"ts": 1000, "title": "Entirely different", "file": "f1"}])
        self.assertEqual(self.totals(), [1, 1, 1])

    def test_artist_retag_with_far_maloja_partner(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Song", "artist": "Old", "file": "f1"}])
        make_maloja(self.mal, [{"ts": 1300, "title": "Song", "artist": "Old"}])
        run_import("merge")
        replace_nav(self, [{"ts": 1000, "title": "Song", "artist": "New", "file": "f1"}])
        self.assertEqual(self.totals(), [1, 1, 1])

    def test_start_clean_keeps_the_pairing_after_a_retag(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Old name", "file": "f1"}])
        make_maloja(self.mal, [{"ts": 1060, "title": "Old name"}])
        run_import("merge")
        replace_nav(self, [{"ts": 1000, "title": "Entirely different", "file": "f1"}])
        self.assertEqual(run_import("clean")["after"], 1)

    def test_start_clean_gives_back_a_maloja_play_navidrome_lost(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "Gone", "file": "f1"}, {"ts": 9000, "title": "Stays", "file": "f2"}])
        make_maloja(self.mal, [{"ts": 1000, "title": "Gone"}])
        run_import("merge")
        replace_nav(self, [{"ts": 9000, "title": "Stays", "file": "f2"}])
        report = run_import("clean")
        self.assertEqual(report["after"], 2)
        self.assertEqual(report["maloja_only"], 1)


class NeverLoses(ImportCase):
    def test_two_tracks_in_the_same_second_in_any_order(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "AAA", "file": "a"}, {"ts": 1000, "title": "BBB", "file": "b"}])
        run_import("merge")
        conn = sqlite3.connect(self.nav)
        conn.execute("UPDATE scrobbles SET media_file_id = CASE media_file_id WHEN 'a' THEN 'b' ELSE 'a' END")
        conn.commit()
        conn.close()
        report = run_import("merge")
        self.assertEqual(sorted(r["title"] for r in self.rows()), ["AAA", "BBB"])
        self.assertEqual(report["merged"], 0)

    def test_play_arriving_during_start_clean_is_kept(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        run_import("merge")
        real = stats_import._load_sources

        def arrives_meanwhile(*args):
            result = real(*args)
            add_live(50000, title="Just played", artists=("Late", "Guest"), album="Now", album_artist="Late", duration=99)
            return result

        with mock.patch.object(stats_import, "_load_sources", arrives_meanwhile):
            report = run_import("clean")
        rows = self.rows()
        self.assertEqual([r["title"] for r in rows], ["One", "Just played"])
        self.assertEqual((rows[1]["artists"], rows[1]["album"], rows[1]["duration"]), ("Late • Guest", "Now", 99))
        self.assertEqual(report["removed"], 0)


class StartCleanChecks(ImportCase):
    def test_empty_navidrome_is_refused(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        run_import("merge")
        replace_nav(self, [])
        with self.assertRaisesRegex(ImportRefused, "no plays"):
            run_import("clean")
        self.assertEqual(self.count(), 1)

    def test_preview_counts_what_would_be_lost_and_changes_nothing(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        run_import("merge")
        add_live(50000, title="App only")
        backups = len(list(Path(config.DATA_DIR).glob("stats.db.bak-*")))
        preview = stats_import.preview_clean()
        self.assertEqual((preview["before"], preview["after"], preview["removed"]), (2, 1, 1))
        self.assertEqual(self.count(), 2)
        self.assertEqual(len(list(Path(config.DATA_DIR).glob("stats.db.bak-*"))), backups)
        conn = stats_db.connect()
        self.assertNotEqual(stats_db.get_meta(conn, "last_import")["mode"], "preview")
        conn.close()

    def test_preview_refused_without_navidrome(self):
        with self.assertRaises(ImportRefused):
            stats_import.preview_clean()


class MalojaCopySafety(ImportCase):
    def kept(self):
        return Path(config.DATA_DIR) / "stats_sources" / "malojadb.sqlite"

    def test_unreadable_maloja_does_not_replace_the_copy(self):
        make_maloja(self.mal, [{"ts": 1000, "title": "One"}])
        run_import("merge")
        before = self.kept().read_bytes()
        conn = sqlite3.connect(self.mal)
        conn.execute("INSERT INTO scrobbles(timestamp, origin, track_id) VALUES (2000, 'x', 1)")
        conn.commit()
        conn.close()
        with mock.patch.object(stats_import, "_read_maloja", side_effect=sqlite3.DatabaseError("malformed")):
            with self.assertRaises(ImportRefused):
                run_import("merge")
        self.assertEqual(self.kept().read_bytes(), before)

    def test_damaged_copy_does_not_block_navidrome(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One"}])
        self.kept().parent.mkdir(parents=True, exist_ok=True)
        self.kept().write_bytes(b"garbage" * 500)
        report = run_import("merge")
        self.assertEqual(report["after"], 1)
        self.assertTrue(any("saved Maloja copy" in w for w in report["warnings"]))


class LivePlays(unittest.TestCase):
    def setUp(self):
        reset()
        stats_import._library_cache.clear()

    def listen(self, ts, title, artist, album):
        return {"listened_at": 1700000000 + ts, "track_metadata": {"track_name": title, "artist_name": artist, "release_name": album}}

    def test_live_plays_keep_the_album_they_already_have(self):
        conn = stats_db.connect()
        track = stats_db.upsert_track(conn, "One", ["Main"])
        stats_db.add_play(conn, track, stats_db.upsert_album(conn, "Big Album", "Main"), 100, 1000, "navidrome")
        conn.commit()
        conn.close()
        stats_ingest.record_listens([
            self.listen(2000, "One", "Main", "Big Album"),
            self.listen(3000, "Two", "Feat Person • Main", "Big Album"),
        ])
        conn = stats_db.connect()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0], 1)
        conn.close()

    def test_feat_in_the_artist_field_is_not_a_new_artist(self):
        stats_ingest.record_listens([self.listen(2000, "Dup", "Main", "A"), self.listen(3000, "Dup", "Main feat. Guest", "A")])
        conn = stats_db.connect()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0], 1)
        self.assertEqual({r[0] for r in conn.execute("SELECT name FROM artists")} - {"Guest"}, {"Main"})
        conn.close()


class BadValues(unittest.TestCase):
    def setUp(self):
        reset()
        stats_import._library_cache.clear()

    def entry(self, ts=1700000000, title="Song", artist="A", info=None):
        return {"listened_at": ts, "track_metadata": {"track_name": title, "artist_name": artist, "additional_info": info or {}}}

    def plays(self):
        conn = stats_db.connect()
        count = stats_db.play_count(conn)
        conn.close()
        return count

    def test_impossible_times_are_skipped(self):
        result = stats_ingest.record_listens([
            self.entry(ts=int(time.time() * 1000)),  # milliseconds
            self.entry(ts=10 ** 30),
            self.entry(ts=5),
            self.entry(title="Fine"),
        ])
        self.assertEqual((result["added"], result["skipped"]), (1, 3))

    def test_infinite_length_is_ignored(self):
        stats_ingest.record_listens([self.entry(info={"duration_ms": float("inf")})])
        conn = stats_db.connect()
        self.assertIsNone(conn.execute("SELECT duration_sec FROM plays").fetchone()[0])
        conn.close()

    def test_no_artist_left_after_splitting_is_skipped(self):
        result = stats_ingest.record_listens([self.entry(artist=" • "), self.entry(title="Fine")])
        self.assertEqual((result["added"], result["skipped"]), (1, 1))

    def test_broken_unicode_is_skipped(self):
        result = stats_ingest.record_listens([self.entry(title="\ud800 bad"), self.entry(artist="\ud800"), self.entry(title="Fine")])
        self.assertEqual((result["added"], result["skipped"]), (1, 2))

    def test_stats_survive_after_bad_batch(self):
        stats_ingest.record_listens([self.entry(ts=int(time.time() * 1000)), self.entry(info={"duration_ms": float("inf")})])
        from core.stats_queries import overview, recap_index
        self.assertEqual(overview("all", "", "UTC")["totals"]["plays"], 1)
        self.assertEqual(len(recap_index("UTC")["months"]), 1)


class HugeNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        reset()
        patcher = mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.app.test_client()

    def test_huge_entity_id_is_404(self):
        self.assertEqual(self.client.get(f"/api/stats/artist/{10 ** 30}?tz=UTC").status_code, 404)

    def test_huge_page_is_empty(self):
        response = self.client.get(f"/api/stats/plays?page={10 ** 30}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["plays"], [])

    def test_preview_route(self):
        response = self.client.post("/api/stats/import/preview")
        self.assertEqual(response.status_code, 409)


class NewBadge(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = stats_db.connect()

    def tearDown(self):
        self.conn.close()

    def play(self, ts, title, artist):
        track = stats_db.upsert_track(self.conn, title, [artist])
        stats_db.add_play(self.conn, track, stats_db.upsert_album(self.conn, f"{title} album", artist), 100, ts, "live")
        self.conn.commit()

    def test_row_is_new_only_on_first_ever_play(self):
        self.play(stamp(2026, 1, 5), "Back", "Returning")
        self.play(stamp(2026, 3, 5), "Back", "Returning")
        self.play(stamp(2026, 3, 6), "Fresh", "Newcomer")
        top = recap("month", "2026-03", "UTC")["top"]
        for kind, field in (("artists", "name"), ("tracks", "title"), ("albums", "title")):
            flags = {row[field].split(" album")[0]: row["is_new"] for row in top[kind]}
            self.assertEqual(flags, {"Returning" if kind == "artists" else "Back": False, "Newcomer" if kind == "artists" else "Fresh": True}, kind)

    def test_first_period_has_no_new_flags(self):
        self.play(stamp(2026, 1, 5), "Song", "A")
        self.assertFalse(recap("month", "2026-01", "UTC")["top"]["artists"][0]["is_new"])


class StaleLookups(unittest.TestCase):
    def setUp(self):
        reset()

    def test_lookup_finished_after_a_rebuild_does_not_touch_another_track(self):
        conn = stats_db.connect()
        track = stats_db.upsert_track(conn, "Song", ["A"])
        stats_db.add_play(conn, track, None, None, 1000, "live")
        conn.commit()
        conn.close()

        def rebuild_meanwhile(path, params=None):
            other = stats_db.connect()
            other.execute("UPDATE tracks SET key='z|other', title='Totally Other' WHERE id=?", (track,))
            other.commit()
            other.close()
            return {"data": [{"id": 11, "title": "Song", "duration": 200, "artist": {"id": 3, "name": "A"},
                              "album": {"id": 22, "title": "Album", "cover_medium": "http://img/x.jpg"}}]}

        with mock.patch("core.deezer._public_api", rebuild_meanwhile):
            stats_enrich.enrich_batch(1)
        conn = stats_db.connect()
        row = conn.execute("SELECT deezer_track_id, cover_url, duration_sec FROM tracks WHERE id=?", (track,)).fetchone()
        self.assertEqual(tuple(row), (None, None, None))
        conn.close()

    def test_failed_lookup_after_a_rebuild_leaves_the_retry_alone(self):
        conn = stats_db.connect()
        track = stats_db.upsert_track(conn, "Song", ["A"])
        stats_db.add_play(conn, track, None, None, 1000, "live")
        conn.commit()
        conn.close()

        def rebuild_then_fail(path, params=None):
            other = stats_db.connect()
            other.execute("UPDATE tracks SET key='z|other' WHERE id=?", (track,))
            other.commit()
            other.close()
            raise OSError("no network")

        with mock.patch("core.deezer._public_api", rebuild_then_fail):
            stats_enrich.enrich_batch(1)
        conn = stats_db.connect()
        self.assertIsNone(conn.execute("SELECT lookup_at FROM tracks WHERE id=?", (track,)).fetchone()[0])
        conn.close()


class DistinctNames(unittest.TestCase):
    def test_non_latin_marks_keep_names_apart(self):
        for one, other in (("ガラス", "カラス"), ("Мой", "Мои"), ("ไม้", "ไม"), ("🔥 Song", "💧 Song")):
            self.assertNotEqual(track_key(["A"], one), track_key(["A"], other), (one, other))
            self.assertNotEqual(track_key([one], "S"), track_key([other], "S"), (one, other))

    def test_latin_accents_still_fold(self):
        self.assertEqual(track_key(["Beyoncé"], "Déjà Vu"), track_key(["BEYONCE"], "deja vu"))
        self.assertEqual(track_key(["Øneheart"], "x"), track_key(["Øneheart"], "x"))

    def test_same_japanese_title_in_both_unicode_forms(self):
        import unicodedata
        self.assertEqual(track_key(["A"], unicodedata.normalize("NFC", "ガラス")), track_key(["A"], unicodedata.normalize("NFD", "ガラス")))

    def test_search_finds_non_latin_title(self):
        reset()
        conn = stats_db.connect()
        stats_db.add_play(conn, stats_db.upsert_track(conn, "ガラス", ["A"]), None, 100, 1000, "live")
        conn.commit()
        conn.close()
        self.assertEqual(search_plays("ガラス", 1)["total"], 1)
        self.assertEqual(search_plays("カラス", 1)["total"], 0)


if __name__ == "__main__":
    unittest.main()
