import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, mix_builder as mb, mix_candidates as mc, mix_taste, mixes_db, stats_db, trial
from core.deezer import load_playlists, playlist_kind, save_playlists

NOW = 1_800_000_000
DAY = 86400


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.downloads = self.root / "deezer-dl"
        (self.downloads / "songs").mkdir(parents=True)
        self.playlists_dir = self.root / "playlists"
        self.library_dir = self.root / "library"
        self.library_dir.mkdir()
        for db in (mixes_db.db_path(), stats_db.db_path()):
            for suffix in ("", "-wal", "-shm"):
                Path(f"{db}{suffix}").unlink(missing_ok=True)
        save_playlists([])
        config.save_preview_state({})
        self.entries = []
        mappings = {self.library_dir: self.root / "nd" / "music", self.downloads: self.root / "nd" / "deezer-dl",
                    self.playlists_dir: self.root / "nd" / "playlists"}
        paths = ([self.library_dir], self.playlists_dir, self.root / "cache.json", mappings)
        patches = [
            mock.patch("core.deezer_dl.download_dir", return_value=self.downloads),
            mock.patch("core.deezer_dl.download_arl", return_value="arl"),
            mock.patch("core.deezer_dl.download_dir_status", return_value={"writable": True}),
            mock.patch("core.mix_builder.library_entries", side_effect=lambda: self.entries),
            mock.patch("core.config.get_paths_from_config", return_value=paths),
            mock.patch("core.deezer.get_paths_from_config", return_value=paths),
            mock.patch("core.deezer.cache_cover", return_value=None),
            mock.patch("core.stats_import._navidrome_path", return_value=self.root / "absent.db"),
            mock.patch("core.mix_builder._refresh_library"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)
        self.stats = stats_db.connect()
        self.addCleanup(self.stats.close)

    def own(self, artist, title, genre="Rock", bpm=120, plays=0, album=None):
        path = self.library_dir / artist / f"{title}.flac"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"audio")
        self.entries.append({"path": str(path), "tag_artist": artist, "tag_title": title, "tag_album": album or "A",
                             "duration": 200, "mtime_ns": 1})
        self.conn.execute("INSERT OR REPLACE INTO track_features VALUES (?,?,?,?,?)", (str(path), 1, bpm, genre, NOW))
        if plays:
            track = stats_db.upsert_track(self.stats, title, [artist], genre=genre, genre_source="file")
            album_id = stats_db.upsert_album(self.stats, album, artist) if album else None
            for i in range(plays):
                stats_db.add_play(self.stats, track, album_id, 200, NOW - DAY - i * 60, "navidrome")
        return path

    def rich_library(self):
        for a in range(8):
            for t in range(10):
                self.own(f"Artist{a}", f"Song{t}", plays=6 if t < 6 else 0, album=f"Album{a}")
        self.conn.commit()
        self.stats.commit()


class Plumbing(unittest.TestCase):
    def test_generated_ids_are_their_own_kind(self):
        for pid in ("auto-daily-1", "auto-blend-4", "auto-discover", "auto-trial"):
            self.assertEqual(playlist_kind(pid), "auto", pid)
        for pid in ("auto-x", "auto-daily-0", "auto-daily-x", "auto-trial-1"):
            self.assertEqual(playlist_kind(pid), "playlist", pid)


class Daily(Base):
    def test_builds_four_named_mixes_and_their_files(self):
        self.rich_library()
        result = mb.generate(["daily"], now=NOW)
        self.assertEqual(result["built"]["daily"], [f"auto-daily-{i}" for i in range(1, 5)])
        titles = {p["id"]: p for p in load_playlists()}
        self.assertEqual(titles["auto-daily-1"]["title"], "Daily Mix 1")
        self.assertEqual(titles["auto-daily-1"]["kind"], "auto")
        self.assertTrue(titles["auto-daily-1"]["subtitle"])
        m3u = self.playlists_dir / "Daily Mix 1" / "Daily Mix 1.m3u8"
        self.assertTrue(m3u.exists())
        self.assertGreaterEqual(len(m3u.read_text(encoding="utf-8").splitlines()), mix_taste.MIN_MIX_SIZE)

    def test_downloads_nothing(self):
        self.rich_library()
        with mock.patch("core.mix_builder.download_to_trial") as download:
            mb.generate(["daily"], now=NOW)
        download.assert_not_called()

    def test_works_without_a_deezer_account(self):
        self.rich_library()
        with mock.patch("core.deezer_dl.download_arl", return_value=""):
            self.assertTrue(mb.generate(["daily"], now=NOW)["built"]["daily"])

    def test_seeds_change_the_next_day(self):
        self.rich_library()
        mb.generate(["daily"], now=NOW)
        first = set(mixes_db.get_meta(self.conn, "seeds_daily"))
        mb.generate(["daily"], now=NOW + DAY)
        self.assertEqual(first & set(mixes_db.get_meta(self.conn, "seeds_daily")), set())

    def test_a_mix_takes_the_picture_of_its_seed(self):
        from core.stats_covers import covers_dir
        self.rich_library()
        covers_dir().mkdir(parents=True, exist_ok=True)
        (covers_dir() / "seed.jpg").write_bytes(b"picture")
        self.stats.execute("INSERT OR REPLACE INTO covers(kind, item_key, file, checked_at) SELECT 'artist', key, 'seed.jpg', 1 FROM artists")
        self.stats.execute("INSERT OR REPLACE INTO covers(kind, item_key, file, checked_at) SELECT 'track', key, 'seed.jpg', 1 FROM tracks")
        self.stats.execute("INSERT OR REPLACE INTO covers(kind, item_key, file, checked_at) SELECT 'album', key, 'seed.jpg', 1 FROM albums")
        self.stats.commit()
        self.addCleanup(lambda: [config.delete_playlist_cache(f"auto-daily-{i}") for i in range(1, 5)])
        mb.generate(["daily"], now=NOW)
        self.assertEqual((config.COVERS_DIR / "auto-daily-1.jpg").read_bytes(), b"picture")

    def test_a_file_that_vanished_is_not_proposed(self):
        self.rich_library()
        gone = Path(self.entries[0]["path"])
        gone.unlink()
        mb.generate(["daily"], now=NOW)
        rows = [r for p in load_playlists() for r in config.get_preview_state(p["id"])["rows"]]
        self.assertNotIn(str(gone), [r["local_path"] for r in rows])

    def test_tracks_on_trial_are_not_your_own_tracks(self):
        self.rich_library()
        path = trial.trial_dir() / "Artist0 - New.flac"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"audio")
        self.entries.append({"path": str(path), "tag_artist": "Artist0", "tag_title": "New", "mtime_ns": 1})
        mb.generate(["daily"], now=NOW)
        rows = [r for i in range(1, 5) for r in config.get_preview_state(f"auto-daily-{i}")["rows"]]
        self.assertNotIn(str(path), [r["local_path"] for r in rows])

    def test_mix_no_longer_possible_leaves(self):
        self.rich_library()
        mb.generate(["daily"], now=NOW)
        self.entries.clear()
        mb.generate(["daily"], now=NOW + DAY)
        self.assertFalse([p for p in load_playlists() if p["id"].startswith("auto-daily")])
        self.assertFalse((self.playlists_dir / "Daily Mix 1" / "Daily Mix 1.m3u8").exists())

    def test_one_run_at_a_time(self):
        self.assertTrue(mb._run_lock.acquire(blocking=False))
        self.addCleanup(mb._run_lock.release)
        with self.assertRaises(RuntimeError):
            mb.generate(["daily"], now=NOW)

    def test_empty_install_does_not_fail(self):
        self.assertEqual(mb.generate(["daily", ], now=NOW)["built"]["daily"], [])

    def test_regular_playlists_are_left_alone(self):
        self.rich_library()
        save_playlists([{"id": "123", "title": "Mine", "picture": "x"}])
        mb.generate(["daily"], now=NOW)
        self.entries.clear()
        mb.generate(["daily"], now=NOW + DAY)
        self.assertIn("123", [p["id"] for p in load_playlists()])


class Unpublishing(Base):
    def test_refuses_a_regular_playlist(self):
        with self.assertRaises(ValueError):
            mb.unpublish("123")

    def test_only_its_own_files_leave(self):
        self.rich_library()
        mb.generate(["daily"], now=NOW)
        other = self.playlists_dir / "Daily Mix 1" / "my notes.txt"
        other.write_text("mine")
        mb.unpublish("auto-daily-1")
        self.assertEqual(other.read_text(), "mine")
        self.assertFalse((self.playlists_dir / "Daily Mix 1" / "Daily Mix 1.m3u8").exists())

    def test_turning_off_removes_playlists_and_keeps_the_quarantine(self):
        self.rich_library()
        mb.generate(["daily"], now=NOW)
        path = trial.trial_dir() / "x.flac"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"a")
        trial.add_download(self.conn, "1", "A", "S", "", path, "auto-blend-1", NOW)
        mb.set_enabled(self.conn, "daily", False)
        self.assertFalse([p for p in load_playlists() if p["id"].startswith("auto-daily")])
        self.assertTrue(path.exists())
        self.assertEqual(trial.get(self.conn, "1")["state"], "on_trial")


class FakeQueue:
    """Saves a small file where the real queue would, or fails for the ids given."""

    def __init__(self, failing=()):
        self.failing = {str(i) for i in failing}
        self.calls = []

    def __call__(self, kind, music_id, on_done=None, base_dir=None):
        self.calls.append((music_id, base_dir))
        task = mock.Mock(music_id=music_id)
        if str(music_id) in self.failing:
            on_done(task, None, RuntimeError("no"))
            return task
        path = Path(base_dir) / f"{music_id}.flac"
        path.write_bytes(b"audio")
        on_done(task, {"path": str(path)}, None)
        return task


def cand(track_id, artist=None):
    return mc.parse({"id": track_id, "title": f"New {track_id}", "artist": {"name": artist or f"N{track_id}"},
                     "album": {"title": "B"}, "preview": ""})


class Downloading(Base):
    def test_saved_in_the_trial_folder_and_registered(self):
        queue = FakeQueue()
        saved = mb.download_to_trial(self.conn, [cand(1), cand(2)], 2, "auto-discover", NOW, enqueue=queue)
        self.assertEqual(len(saved), 2)
        self.assertEqual({c[1] for c in queue.calls}, {str(trial.trial_dir())})
        self.assertEqual(trial.get(self.conn, "1")["state"], "on_trial")

    def test_a_failure_moves_on_to_the_spares(self):
        saved = mb.download_to_trial(self.conn, [cand(1), cand(2), cand(3)], 2, "m", NOW, enqueue=FakeQueue(failing=[1]))
        self.assertEqual({t["deezer_id"] for t in saved}, {"2", "3"})

    def test_never_more_than_asked(self):
        queue = FakeQueue()
        mb.download_to_trial(self.conn, [cand(i) for i in range(1, 9)], 3, "m", NOW, enqueue=queue)
        self.assertEqual(len(queue.calls), 3)

    def test_all_failed_gives_an_empty_list(self):
        self.assertEqual(mb.download_to_trial(self.conn, [cand(1)], 1, "m", NOW, enqueue=FakeQueue(failing=[1])), [])


class WithDownloads(Base):
    def setUp(self):
        super().setUp()
        self.rich_library()
        self.new_id = 1000
        queue = FakeQueue()
        real = mb.download_to_trial
        patcher = mock.patch("core.mix_builder.download_to_trial",
                             side_effect=lambda conn, c, want, mix, now: real(conn, c, want, mix, now, enqueue=queue))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.queue = queue
        for target, value in (("core.mix_candidates.seed_pool", self.pool), ("core.mix_candidates.habit_pool", self.pool),
                              ("core.mix_candidates.release_pool", lambda *a, **k: [])):
            p = mock.patch(target, side_effect=value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("core.mix_candidates.preview_tempo", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def pool(self, *args, **kwargs):
        found = []
        for _ in range(120):
            self.new_id += 1
            found.append(cand(self.new_id))
        return found

    def set(self, **changes):
        mb.save_settings(self.conn, changes)

    def test_blend_mixes_your_tracks_with_new_ones(self):
        self.set(blend_new_per_run=8)
        mb.generate(["blend"], now=NOW)
        rows = [r for p in load_playlists() if p["id"].startswith("auto-blend") for r in config.get_preview_state(p["id"])["rows"]]
        in_trial = [r for r in rows if "trial" in Path(r["local_path"]).parts]
        self.assertEqual(len(in_trial), 8)
        self.assertGreater(len(rows) - len(in_trial), 40)

    def test_blend_replays_unheard_tracks_before_fetching_more(self):
        self.set(blend_new_per_run=8)
        mb.generate(["blend"], now=NOW)
        before = len(self.queue.calls)
        self.set(blend_new_per_run=2)
        mb.generate(["blend"], now=NOW + DAY)
        rows = [r for p in load_playlists() if p["id"].startswith("auto-blend") for r in config.get_preview_state(p["id"])["rows"]]
        self.assertGreaterEqual(len([r for r in rows if "trial" in Path(r["local_path"]).parts]), 8)
        self.assertLessEqual(len(self.queue.calls) - before, 2)

    def test_discover_only_has_new_tracks(self):
        self.set(discover_size=12)
        mb.generate(["discover"], now=NOW)
        rows = config.get_preview_state("auto-discover")["rows"]
        self.assertEqual(len(rows), 12)
        self.assertTrue(all("trial" in Path(r["local_path"]).parts for r in rows))

    def test_on_trial_playlist_lists_every_track_in_quarantine(self):
        self.set(discover_size=5)
        mb.generate(["discover"], now=NOW)
        self.assertEqual(len(config.get_preview_state("auto-trial")["rows"]), 5)

    def test_on_trial_playlist_leaves_when_empty(self):
        self.set(discover_size=2)
        mb.generate(["discover"], now=NOW)
        for row in trial.active(self.conn):
            trial.remove(self.conn, row["deezer_id"], NOW)
        mb.publish_trial_playlist(self.conn)
        self.assertNotIn("auto-trial", [p["id"] for p in load_playlists()])

    def test_limit_of_unheard_tracks_stops_downloads_and_says_so(self):
        self.set(discover_size=5, max_unheard=3)
        result = mb.generate(["discover"], now=NOW)
        self.assertEqual(len(self.queue.calls), 3)
        result = mb.generate(["discover"], now=NOW + 7 * DAY)
        self.assertEqual(len(self.queue.calls), 3)
        self.assertIn("unheard", " ".join(result["notes"]))

    def test_limit_of_space_stops_downloads_and_says_so(self):
        self.set(discover_size=5, max_trial_gb=1)
        path = trial.trial_dir() / "big.flac"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"a")
        trial.add_download(self.conn, "1", "A", "Big", "", path, "m", NOW)
        self.conn.execute("UPDATE trial_tracks SET size=?", (2 * 1024 ** 3,))
        self.conn.commit()
        result = mb.generate(["discover"], now=NOW)
        self.assertEqual(self.queue.calls, [])
        self.assertIn("GB", " ".join(result["notes"]))

    def test_refused_track_never_comes_back(self):
        self.set(discover_size=1)
        mb.generate(["discover"], now=NOW)
        refused = trial.active(self.conn)[0]["deezer_id"]
        trial.remove(self.conn, refused, NOW)
        self.new_id = int(refused) - 1
        mb.generate(["discover"], now=NOW + 7 * DAY)
        self.assertEqual([c[0] for c in self.queue.calls].count(refused), 1)

    def test_no_deezer_account_builds_nothing_and_says_so(self):
        with mock.patch("core.deezer_dl.download_arl", return_value=""):
            result = mb.generate(["blend", "discover"], now=NOW)
        self.assertEqual(result["built"], {})
        self.assertIn("Deezer account", " ".join(result["notes"]))
        self.assertEqual(self.queue.calls, [])

    def test_downloads_refresh_the_library(self):
        self.set(discover_size=2)
        mb.generate(["discover"], now=NOW)
        mb._refresh_library.assert_called_once()

    def test_empty_week_keeps_last_weeks_discover(self):
        self.set(discover_size=3)
        mb.generate(["discover"], now=NOW)
        self.set(max_unheard=1)
        mb.generate(["discover"], now=NOW + 7 * DAY)
        self.assertIn("auto-discover", [p["id"] for p in load_playlists()])

    def test_regular_daily_pass_runs_with_generation(self):
        self.set(discover_size=1)
        mb.generate(["discover"], now=NOW)
        row = trial.active(self.conn)[0]
        self.assertEqual(row["state"], "on_trial")
        mb.generate([], now=NOW + 31 * DAY)
        self.assertEqual(trial.get(self.conn, row["deezer_id"])["state"], "pending")


class Timing(Base):
    def test_nothing_is_due_when_off(self):
        self.assertEqual(mb.due_versions(self.conn, NOW), [])

    def test_due_after_its_interval_only(self):
        mb.save_settings(self.conn, {"daily": True, "discover": True})
        self.assertEqual(mb.due_versions(self.conn, NOW), ["daily", "discover"])
        mixes_db.set_meta(self.conn, "last_daily", NOW)
        mixes_db.set_meta(self.conn, "last_discover", NOW)
        self.assertEqual(mb.due_versions(self.conn, NOW + DAY - 1), [])
        self.assertEqual(mb.due_versions(self.conn, NOW + DAY), ["daily"])
        self.assertEqual(mb.due_versions(self.conn, NOW + 7 * DAY), ["daily", "discover"])

    def test_tick_waits_for_the_tempo_analysis(self):
        self.entries.extend({"path": f"/x/{i}.flac", "mtime_ns": 1} for i in range(10))
        mb.save_settings(self.conn, {"daily": True})
        with mock.patch("core.mix_builder.start_task") as start, \
                mock.patch("core.mix_features.start_background") as analysis:
            mb.tick(NOW)
        analysis.assert_called_once()
        start.assert_not_called()

    def test_tick_starts_once_analysed(self):
        self.rich_library()
        mb.save_settings(self.conn, {"daily": True})
        with mock.patch("core.mix_builder.start_task") as start:
            mb.tick(NOW)
        start.assert_called_once_with(["daily"])

    def test_tick_does_nothing_when_off(self):
        self.entries.append({"path": "/x/1.flac", "mtime_ns": 1})
        with mock.patch("core.mix_features.start_background") as analysis:
            mb.tick(NOW)
        analysis.assert_not_called()


class Settings(Base):
    def test_values_are_cleaned(self):
        saved = mb.save_settings(self.conn, {"daily": 1, "max_unheard": "5", "unknown": 3})
        self.assertIs(saved["daily"], True)
        self.assertEqual(saved["max_unheard"], 5)
        self.assertNotIn("unknown", saved)


class SurvivesStartClean(Base):
    def test_quarantine_is_not_in_the_history_database(self):
        path = trial.trial_dir() / "x.flac"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"a")
        trial.add_download(self.conn, "1", "A", "S", "", path, "m", NOW)
        self.stats.execute("DELETE FROM plays")
        self.stats.commit()
        self.assertEqual(trial.get(self.conn, "1")["state"], "on_trial")
        self.assertNotIn("trial_tracks", [r[0] for r in self.stats.execute("SELECT name FROM sqlite_master")])


if __name__ == "__main__":
    unittest.main()
