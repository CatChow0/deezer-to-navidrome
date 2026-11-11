"""The app's JSON files: never seen half-written, never wiped by a read that
failed, and edited under a lock so that two writers at once both keep their
change."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from core import config, crypto, deezer, files


class AtomicWrites(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_the_text_replaces_the_file_and_no_partial_file_stays(self):
        target = self.dir / "a.json"
        target.write_text("old", encoding="utf-8")
        files.write_json(target, {"é": 1})
        self.assertEqual({"é": 1}, json.loads(target.read_text(encoding="utf-8")))
        self.assertEqual(["a.json"], [p.name for p in self.dir.iterdir()])

    def test_a_failed_write_leaves_the_old_file(self):
        target = self.dir / "a.json"
        target.write_text('{"kept": true}', encoding="utf-8")
        with mock.patch("core.files.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                files.write_json(target, {"new": True})
        self.assertEqual({"kept": True}, json.loads(target.read_text(encoding="utf-8")))
        self.assertEqual(["a.json"], [p.name for p in self.dir.iterdir()])

    def test_a_damaged_file_is_set_aside_not_overwritten(self):
        target = self.dir / "a.json"
        target.write_text('{"half": ', encoding="utf-8")
        self.assertEqual({}, files.read_json(target, {}))
        aside = [p for p in self.dir.iterdir() if p.name.startswith("a.json.corrupt-")]
        self.assertEqual(1, len(aside))
        self.assertEqual('{"half": ', aside[0].read_text(encoding="utf-8"))

    def test_a_missing_file_gives_the_default(self):
        self.assertEqual([], files.read_json(self.dir / "none.json", []))


class SettingsPaths(unittest.TestCase):
    def test_a_path_outside_the_data_folder_is_not_used(self):
        outside = Path(tempfile.mkdtemp()) / "secrets.json"
        self.assertEqual(config.LIBRARY_CACHE_FILE, config.data_file(str(outside), config.LIBRARY_CACHE_FILE))

    def test_a_path_inside_the_data_folder_is_kept(self):
        inside = config.DATA_DIR / "sub" / "cache.json"
        self.assertEqual(inside, config.data_file(str(inside), config.LIBRARY_CACHE_FILE))

    def test_clearing_the_cache_never_deletes_a_file_elsewhere(self):
        victim = Path(tempfile.mkdtemp()) / "precious.json"
        victim.write_text("{}", encoding="utf-8")
        with mock.patch.object(config, "load_config", return_value={"library_cache_file": str(victim)}):
            config.clear_library_cache_file()
        self.assertTrue(victim.exists())


class PreviewState(unittest.TestCase):
    def setUp(self):
        self.addCleanup(config.save_preview_state, {})

    def test_deleting_one_playlist_keeps_the_others(self):
        config.save_preview_state({"1": {"rows": [{"n": 1}]}, "2": {"rows": [{"n": 2}]}})
        config.delete_playlist_cache("1")
        self.assertEqual({"2": {"rows": [{"n": 2}]}}, config.load_preview_state())

    def test_deleting_waits_for_a_scan_that_is_saving(self):
        config.save_preview_state({"1": {"rows": []}})
        inside = threading.Event()
        release = threading.Event()

        def slow(old):
            inside.set()
            release.wait(5)
            return {"rows": [{"n": "fresh"}]}

        scan = threading.Thread(target=config.modify_preview_state, args=("2", slow))
        scan.start()
        inside.wait(5)
        deleting = threading.Thread(target=config.delete_playlist_cache, args=("1",))
        deleting.start()
        release.set()
        scan.join(5)
        deleting.join(5)
        self.assertEqual({"2": {"rows": [{"n": "fresh"}]}}, config.load_preview_state())


class PlaylistsFile(unittest.TestCase):
    def setUp(self):
        deezer.save_playlists([])
        deezer._refresh_failed_at.clear()
        self.addCleanup(deezer.save_playlists, [])

    def test_writers_at_once_all_keep_their_playlist(self):
        def add(i):
            deezer.add_entry({"id": f"xp-csv-{i}", "title": f"P{i}", "picture": "p"})

        threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual({f"xp-csv-{i}" for i in range(20)}, {e["id"] for e in deezer.saved_entries()})

    def test_adding_twice_keeps_one(self):
        self.assertTrue(deezer.add_entry({"id": "xp-csv-a", "title": "A", "picture": "p"}))
        self.assertFalse(deezer.add_entry({"id": "xp-csv-a", "title": "B", "picture": "p"}))
        self.assertEqual(["A"], [e["title"] for e in deezer.saved_entries()])

    def test_put_replaces_and_remove_removes(self):
        deezer.add_entry({"id": "xp-csv-a", "title": "A", "picture": "p"})
        deezer.add_entry({"id": "xp-csv-b", "title": "B", "picture": "p"})
        deezer.put_entry({"id": "xp-csv-a", "title": "A2", "picture": "p"})
        deezer.remove_entries(["xp-csv-b"])
        self.assertEqual([("xp-csv-a", "A2")], [(e["id"], e["title"]) for e in deezer.saved_entries()])

    def test_a_deezer_failure_is_not_retried_on_every_read(self):
        deezer.add_entry({"id": "123", "title": "", "picture": ""})
        with mock.patch.object(deezer, "fetch_deezer_playlist_info", side_effect=RuntimeError("down")) as fetch, \
                mock.patch.object(deezer, "cache_cover", return_value=None):
            first = deezer.load_playlists()
            deezer.load_playlists()
        self.assertEqual(1, fetch.call_count)
        self.assertEqual("Unknown title", first[0]["title"])

    def test_found_details_are_saved_without_losing_a_change_made_meanwhile(self):
        deezer.add_entry({"id": "123", "title": "Mine", "picture": "", "accounts": ["nd1"]})

        def fetched(pid, *args, **kwargs):
            # Another route changes the playlist while Deezer answers.
            deezer.set_accounts("123", ["nd2"])
            return {"id": pid, "title": "Found", "picture": "http://pic"}

        with mock.patch.object(deezer, "fetch_deezer_playlist_info", side_effect=fetched), \
                mock.patch.object(deezer, "cache_cover", return_value=None):
            deezer.load_playlists()
        entry = deezer.saved_entries()[0]
        self.assertEqual(("Mine", "http://pic", ["nd2"]), (entry["title"], entry["picture"], entry["accounts"]))


class GeneratedPlaylistPreview(unittest.TestCase):
    def setUp(self):
        self.addCleanup(deezer.save_playlists, [])

    def test_a_mix_never_scanned_has_an_empty_preview(self):
        deezer.add_entry({"id": "auto-daily-1", "title": "Daily Mix 1", "picture": ""})
        preview = deezer.build_playlist_preview("auto-daily-1")
        self.assertEqual(("Daily Mix 1", []), (preview["playlist_title"], preview["rows"]))


class DamagedSecret(unittest.TestCase):
    def test_a_damaged_value_does_not_stop_the_others_being_encrypted(self):
        self.assertFalse(crypto.needs_rewrap(crypto.PREFIX + "!!!not base64!!!"))


if __name__ == "__main__":
    unittest.main()
