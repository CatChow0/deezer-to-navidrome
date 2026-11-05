import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, mixes_db, stats_db, trial

NOW = 1_800_000_000
DAY = 86400


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.downloads = self.root / "deezer-dl"
        (self.downloads / "songs").mkdir(parents=True)
        patcher = mock.patch("core.deezer_dl.download_dir", return_value=self.downloads)
        patcher.start()
        self.addCleanup(patcher.stop)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)

    def add(self, deezer_id="1", artist="Artist", title="Song", when=NOW, content=b"audio"):
        path = trial.trial_dir() / f"{artist} - {title}.flac"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        trial.add_download(self.conn, deezer_id, artist, title, "Album", path, "auto-blend-1", when)
        return path

    def state(self, deezer_id="1"):
        return trial.get(self.conn, deezer_id)["state"]

    def evaluate(self, plays=None, marks=None, used=(), owned=(), now=NOW):
        return trial.evaluate(self.conn, plays or {}, marks or {}, set(used), set(owned), now)


class Adding(Base):
    def test_new_track_is_on_trial_for_30_days(self):
        self.add()
        row = trial.get(self.conn, "1")
        self.assertEqual(row["state"], "on_trial")
        self.assertEqual(row["trial_ends_at"], NOW + 30 * DAY)
        self.assertEqual(row["size"], 5)

    def test_key_comes_from_the_name_the_plays_will_carry(self):
        self.add(artist="Vald", title="Song (feat. X)")
        self.assertEqual(trial.get(self.conn, "1")["track_key"], stats_db.track_key(["Vald"], "Song"))

    def test_key_follows_the_tags_of_the_file_when_they_differ_from_deezer(self):
        with mock.patch("core.trial.read_tags", return_value={"artist": "Shiny", "title": "Blooming"}):
            self.add(artist="Shiny", title="Blooming Kitty")
        self.assertEqual(trial.get(self.conn, "1")["track_key"], stats_db.track_key(["Shiny"], "Blooming"))

    def test_downloading_again_does_not_restart_a_decision(self):
        self.add()
        self.conn.execute("UPDATE trial_tracks SET state='trash'")
        self.add()
        self.assertEqual(self.state(), "trash")


class Verdicts(Base):
    def test_two_plays_keep_it(self):
        path = self.add()
        self.evaluate(plays={"1": 2})
        self.assertEqual(self.state(), "kept")
        self.assertFalse(path.exists())
        self.assertTrue((self.downloads / "songs" / path.name).exists())

    def test_one_play_is_not_enough(self):
        self.add()
        self.evaluate(plays={"1": 1})
        self.assertEqual(self.state(), "on_trial")

    def test_star_or_good_rating_keeps_it(self):
        self.add("1", title="A")
        self.add("2", title="B")
        self.evaluate(marks={"1": {"starred": True, "rating": 0}, "2": {"starred": False, "rating": 4}})
        self.assertEqual(self.state("1"), "kept")
        self.assertEqual(self.state("2"), "kept")

    def test_bad_rating_goes_to_review_at_once(self):
        path = self.add()
        self.evaluate(marks={"1": {"starred": False, "rating": 2}})
        self.assertEqual(self.state(), "pending")
        self.assertTrue(path.exists())

    def test_track_used_by_a_regular_playlist_is_kept(self):
        path = self.add()
        self.evaluate(used=[str(path)])
        self.assertEqual(self.state(), "kept")

    def test_track_you_also_own_elsewhere_is_kept(self):
        self.add()
        self.evaluate(owned=[trial.get(self.conn, "1")["track_key"]])
        self.assertEqual(self.state(), "kept")

    def test_end_of_trial_asks_and_removes_nothing(self):
        path = self.add()
        self.evaluate(now=NOW + 29 * DAY)
        self.assertEqual(self.state(), "on_trial")
        self.evaluate(now=NOW + 31 * DAY)
        self.assertEqual(self.state(), "pending")
        self.assertTrue(path.exists())
        self.evaluate(now=NOW + 400 * DAY)
        self.assertEqual(self.state(), "pending")
        self.assertTrue(path.exists())

    def test_waiting_for_review_can_still_be_earned_back(self):
        self.add()
        self.evaluate(now=NOW + 31 * DAY)
        self.evaluate(plays={"1": 2}, now=NOW + 32 * DAY)
        self.assertEqual(self.state(), "kept")

    def test_file_gone_from_elsewhere_only_updates_the_state(self):
        path = self.add()
        path.unlink()
        self.evaluate()
        self.assertEqual(self.state(), "gone")


class Decisions(Base):
    def test_remove_goes_to_the_trash(self):
        path = self.add()
        trial.remove(self.conn, "1", NOW)
        self.assertEqual(self.state(), "trash")
        self.assertFalse(path.exists())
        self.assertTrue(Path(trial.get(self.conn, "1")["path"]).exists())
        self.assertTrue(Path(trial.get(self.conn, "1")["path"]).is_relative_to(trial.trash_dir()))

    def test_restore_brings_it_back_as_kept(self):
        self.add()
        trial.remove(self.conn, "1", NOW)
        trial.restore(self.conn, "1", NOW + DAY)
        row = trial.get(self.conn, "1")
        self.assertEqual(row["state"], "kept")
        self.assertTrue(Path(row["path"]).is_relative_to(self.downloads / "songs"))
        self.assertEqual(Path(row["path"]).read_bytes(), b"audio")

    def test_keep_by_hand_never_overwrites(self):
        path = self.add(content=b"new")
        existing = self.downloads / "songs" / path.name
        existing.write_bytes(b"existing")
        trial.keep(self.conn, "1", NOW)
        self.assertEqual(existing.read_bytes(), b"existing")
        self.assertEqual(Path(trial.get(self.conn, "1")["path"]).read_bytes(), b"new")

    def test_remove_all_waiting_only_touches_the_waiting_list(self):
        self.add("1", title="Waiting")
        self.evaluate(now=NOW + 31 * DAY)
        keep = self.add("2", title="Current", when=NOW + 31 * DAY)
        self.assertEqual(trial.remove_all_pending(self.conn, NOW + 31 * DAY), 1)
        self.assertEqual(self.state("1"), "trash")
        self.assertEqual(self.state("2"), "on_trial")
        self.assertTrue(keep.exists())

    def test_kept_track_cannot_be_removed(self):
        self.add()
        trial.keep(self.conn, "1", NOW)
        with self.assertRaises(trial.TrialError):
            trial.remove(self.conn, "1", NOW)
        self.assertEqual(self.state(), "kept")


class Purge(Base):
    def test_trash_is_emptied_after_30_days_only(self):
        self.add()
        trial.remove(self.conn, "1", NOW)
        file = Path(trial.get(self.conn, "1")["path"])
        trial.purge(self.conn, NOW + 29 * DAY)
        self.assertTrue(file.exists())
        trial.purge(self.conn, NOW + 31 * DAY)
        self.assertFalse(file.exists())
        self.assertEqual(self.state(), "deleted")

    def test_nothing_else_is_ever_deleted(self):
        self.add("1", title="Kept")
        trial.keep(self.conn, "1", NOW)
        self.add("2", title="Trial")
        self.add("3", title="Waiting")
        self.conn.execute("UPDATE trial_tracks SET state='pending' WHERE deezer_id='3'")
        self.conn.commit()
        trial.purge(self.conn, NOW + 1000 * DAY)
        for deezer_id in ("1", "2", "3"):
            self.assertTrue(Path(trial.get(self.conn, deezer_id)["path"]).exists())

    def test_removed_track_is_remembered_after_the_file_is_gone(self):
        self.add(artist="Bad", title="Song")
        trial.remove(self.conn, "1", NOW)
        trial.purge(self.conn, NOW + 31 * DAY)
        self.assertIn("1", trial.rejected(self.conn)["ids"])
        self.assertIn(stats_db.track_key(["Bad"], "Song"), trial.rejected(self.conn)["keys"])


class Safety(Base):
    """Whatever the database says, a file outside the trial folder or the trash stays."""

    def forge(self, target, state):
        self.add()
        self.conn.execute("UPDATE trial_tracks SET path=?, state=? WHERE deezer_id='1'", (str(target), state))
        self.conn.commit()

    def outside(self):
        target = self.root / "library" / "My album" / "01.flac"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"precious")
        return target

    def test_remove_refuses_a_path_outside(self):
        target = self.outside()
        self.forge(target, "pending")
        with self.assertRaises(trial.TrialError):
            trial.remove(self.conn, "1", NOW)
        self.assertEqual(target.read_bytes(), b"precious")

    def test_keep_refuses_a_path_outside(self):
        target = self.outside()
        self.forge(target, "on_trial")
        with self.assertRaises(trial.TrialError):
            trial.keep(self.conn, "1", NOW)
        self.assertEqual(target.read_bytes(), b"precious")

    def test_purge_leaves_a_path_outside(self):
        target = self.outside()
        self.forge(target, "trash")
        self.conn.execute("UPDATE trial_tracks SET state_at=?", (NOW - 100 * DAY,))
        self.conn.commit()
        trial.purge(self.conn, NOW)
        self.assertEqual(target.read_bytes(), b"precious")

    def test_a_path_climbing_out_of_the_folder_is_refused(self):
        target = self.outside()
        sneaky = trial.trial_dir() / ".." / ".." / "library" / "My album" / "01.flac"
        self.forge(sneaky, "pending")
        with self.assertRaises(trial.TrialError):
            trial.remove(self.conn, "1", NOW)
        self.assertEqual(target.read_bytes(), b"precious")

    def test_folder_with_a_similar_name_is_outside(self):
        twin = self.downloads / "trial2" / "x.flac"
        twin.parent.mkdir()
        twin.write_bytes(b"precious")
        self.forge(twin, "pending")
        with self.assertRaises(trial.TrialError):
            trial.remove(self.conn, "1", NOW)
        self.assertEqual(twin.read_bytes(), b"precious")

    def test_evaluate_survives_a_refused_path(self):
        target = self.outside()
        self.forge(target, "on_trial")
        self.add("2", title="Fine")
        self.evaluate(plays={"1": 5, "2": 5})
        self.assertEqual(target.read_bytes(), b"precious")
        self.assertEqual(self.state("2"), "kept")


class Moved(Base):
    def test_kept_file_updates_the_history(self):
        reset_stats()
        path = self.add(artist="Vald", title="Song")
        conn = stats_db.connect()
        track = stats_db.upsert_track(conn, "Song", ["Vald"])
        conn.execute("UPDATE tracks SET file_path=? WHERE id=?", (str(path), track))
        conn.commit()
        conn.close()
        trial.keep(self.conn, "1", NOW)
        conn = stats_db.connect()
        self.addCleanup(conn.close)
        moved = conn.execute("SELECT file_path FROM tracks WHERE id=?", (track,)).fetchone()[0]
        self.assertEqual(moved, str(self.downloads / "songs" / path.name))

    def test_kept_file_updates_saved_playlist_rows(self):
        path = self.add()
        rows = [{"number": 1, "matched": True, "local_path": str(path)}]
        config.update_preview_state("777", {"rows": rows})
        self.addCleanup(lambda: config.delete_playlist_cache("777"))
        with mock.patch("core.trial._rewrite_playlist") as rewrite:
            trial.keep(self.conn, "1", NOW)
        self.assertEqual(config.get_preview_state("777")["rows"][0]["local_path"], str(self.downloads / "songs" / path.name))
        rewrite.assert_called_once_with("777")


class Forgotten(Base):
    def test_removed_track_leaves_generated_playlists_and_regular_ones_show_it_missing(self):
        path = self.add()
        other = {"number": 2, "matched": True, "local_path": "/m/other.flac"}
        config.update_preview_state("auto-daily-1", {"rows": [{"number": 1, "matched": True, "local_path": str(path)}, other]})
        config.update_preview_state("779", {"rows": [{"number": 1, "matched": True, "local_path": str(path)}]})
        self.addCleanup(lambda: config.delete_playlist_cache("auto-daily-1"))
        self.addCleanup(lambda: config.delete_playlist_cache("779"))
        with mock.patch("core.trial._rewrite_playlist") as rewrite:
            trial.remove(self.conn, "1", NOW)
        self.assertEqual(config.get_preview_state("auto-daily-1")["rows"], [other])
        self.assertFalse(config.get_preview_state("779")["rows"][0]["matched"])
        self.assertEqual(rewrite.call_count, 2)


class Paths(Base):
    def test_only_regular_playlists_protect_a_track(self):
        path = self.add()
        config.update_preview_state("auto-daily-1", {"rows": [{"local_path": str(path)}]})
        self.addCleanup(lambda: config.delete_playlist_cache("auto-daily-1"))
        self.assertEqual(trial.paths_in_regular_playlists(), set())
        config.update_preview_state("778", {"rows": [{"local_path": str(path)}]})
        self.addCleanup(lambda: config.delete_playlist_cache("778"))
        self.assertEqual(trial.paths_in_regular_playlists(), {str(path)})


class Usage(Base):
    def test_counts_unheard_and_size(self):
        self.add("1", title="A", content=b"12345")
        self.add("2", title="B", content=b"123")
        self.conn.execute("UPDATE trial_tracks SET state='kept' WHERE deezer_id='2'")
        self.conn.commit()
        self.assertEqual(trial.usage(self.conn, {"1": 0}), {"unheard": 1, "bytes": 5})
        self.assertEqual(trial.usage(self.conn, {"1": 1}), {"unheard": 0, "bytes": 5})


class Plays(Base):
    def test_only_plays_since_the_download_count(self):
        reset_stats()
        self.add(artist="Vald", title="Song")
        conn = stats_db.connect()
        self.addCleanup(conn.close)
        track = stats_db.upsert_track(conn, "Song", ["Vald"])
        stats_db.add_play(conn, track, None, 200, NOW - DAY, "navidrome")
        stats_db.add_play(conn, track, None, 200, NOW + DAY, "navidrome")
        conn.commit()
        self.assertEqual(trial.plays_since_download(self.conn, conn), {"1": 1})


class NavidromeMarks(Base):
    def test_reads_marks_of_files_on_trial_from_a_copy(self):
        import sqlite3
        db = self.root / "navidrome.db"
        nd = sqlite3.connect(db)
        nd.executescript("""
            CREATE TABLE media_file (id TEXT PRIMARY KEY, path TEXT);
            CREATE TABLE annotation (user_id TEXT, item_id TEXT, item_type TEXT, starred INT, rating INT);
            INSERT INTO media_file VALUES ('a', 'trial/Artist - Song.flac'), ('b', 'songs/Other.flac');
            INSERT INTO annotation VALUES ('u', 'a', 'media_file', 1, 0), ('u', 'b', 'media_file', 1, 5);
        """)
        nd.commit()
        nd.close()
        self.add()
        with mock.patch("core.stats_import._navidrome_path", return_value=db):
            marks = trial.navidrome_marks(self.conn)
        self.assertEqual(marks, {"1": {"starred": True, "rating": 0}})

    def test_no_mount_means_no_marks(self):
        self.add()
        with mock.patch("core.stats_import._navidrome_path", return_value=self.root / "absent.db"):
            self.assertIsNone(trial.navidrome_marks(self.conn))


def reset_stats():
    for suffix in ("", "-wal", "-shm"):
        Path(f"{stats_db.db_path()}{suffix}").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
