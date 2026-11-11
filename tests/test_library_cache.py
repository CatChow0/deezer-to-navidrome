"""The library cache: a disk not mounted for a moment keeps its tracks, and two
refreshes at once never lose what the other found."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from core import library
from core.utils import get_file_signature


def entry(path, scan_dirs=None):
    mtime_ns, size = get_file_signature(path)
    return {"path_str": str(path), "mtime_ns": mtime_ns, "size": size}


class Base(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.disk_a, self.disk_b = root / "a", root / "b"
        for disk in (self.disk_a, self.disk_b):
            disk.mkdir()
        self.cache = root / "cache.json"
        paths = ([self.disk_a, self.disk_b], root / "playlists", self.cache, {})
        for patch in (mock.patch.object(library, "get_paths_from_config", return_value=paths),
                      mock.patch.object(library, "build_library_entry", side_effect=entry)):
            patch.start()
            self.addCleanup(patch.stop)

    def song(self, disk, name):
        path = disk / name
        path.write_bytes(b"audio")
        return str(path)

    def cached(self):
        return sorted(e["path_str"] for e in library.load_library_cache(self.cache))


class UnmountedDisk(Base):
    def test_an_empty_mount_point_keeps_its_tracks(self):
        a, b = self.song(self.disk_a, "1.flac"), self.song(self.disk_b, "2.flac")
        library.rebuild_library_cache_full()
        Path(b).unlink()  # the disk is gone: its mount point is empty
        new = self.song(self.disk_a, "3.flac")
        library.refresh_library_cache_incremental()
        self.assertEqual(sorted([a, b, new]), self.cached())

    def test_a_file_deleted_on_a_mounted_disk_leaves_the_cache(self):
        a, b = self.song(self.disk_a, "1.flac"), self.song(self.disk_a, "2.flac")
        library.rebuild_library_cache_full()
        Path(b).unlink()
        library.refresh_library_cache_incremental()
        self.assertEqual([a], self.cached())

    def test_the_plain_and_the_progress_versions_agree(self):
        self.song(self.disk_a, "1.flac")
        messages = []
        result = library.rebuild_library_cache_full_with_progress(lambda **kw: messages.append(kw["message"]))
        self.assertEqual({"count": 1}, result)
        self.assertEqual("Library cache rebuilt", messages[-1])
        self.assertEqual({"count": 1, "reused": 1, "rebuilt": 0}, library.refresh_library_cache_incremental())


class Renormalized(Base):
    def test_an_old_cache_gets_the_new_keys_without_reading_the_files(self):
        import json

        song = self.song(self.disk_a, "Кино - Группа крови.flac")
        old = {"path": song, "path_str": song, "mtime_ns": 1, "size": 5, "tag_artist": "Кино",
               "tag_title": "Группа крови", "tag_album": "", "duration": 200, "norm_tag_artist": ""}
        self.cache.write_text(json.dumps({"library": [old]}), encoding="utf-8")
        with mock.patch.object(library, "read_tags", side_effect=AssertionError("no file read")):
            self.assertEqual(1, library.renormalize_cache())
            self.assertEqual(0, library.renormalize_cache())
        entry = library.load_library_cache(self.cache)[0]
        self.assertEqual(("кино", 1), (entry["norm_tag_artist"], entry["mtime_ns"]))


class NonLatinNames(unittest.TestCase):
    def test_every_script_keeps_its_letters(self):
        from core.normalization import normalize_text

        self.assertEqual("кино", normalize_text("Кино"))
        self.assertEqual("røyksopp", normalize_text("Røyksopp"))
        self.assertNotEqual(normalize_text("宇多田ヒカル"), normalize_text("Кино"))
        self.assertEqual("beyonce and jay z", normalize_text("Beyoncé & Jay-Z"))
        self.assertEqual("clean", normalize_text("Clean"))
        # Marks make another word outside Latin: glass and crow.
        self.assertNotEqual(normalize_text("ガラス"), normalize_text("カラス"))

    def test_version_words_are_whole_words(self):
        from core.normalization import extract_version_flags

        self.assertEqual([], extract_version_flags("Alive", "Demons", "Monochrome", "Obsession"))
        self.assertEqual(["live"], extract_version_flags("Alive (Live)"))


class OneAtATime(Base):
    def test_a_refresh_waits_for_a_rebuild(self):
        self.song(self.disk_a, "1.flac")
        inside, release = threading.Event(), threading.Event()
        real = library.scan_audio_files

        def slow_scan(dirs):
            inside.set()
            release.wait(5)
            return real(dirs)

        with mock.patch.object(library, "scan_audio_files", side_effect=slow_scan):
            rebuild = threading.Thread(target=library.rebuild_library_cache_full)
            rebuild.start()
            inside.wait(5)
            self.assertFalse(library._cache_lock.acquire(blocking=False))
            release.set()
            rebuild.join(5)
        self.assertTrue(library._cache_lock.acquire(blocking=False))
        library._cache_lock.release()


class Routes(unittest.TestCase):
    def test_both_library_tasks_still_run_from_the_api(self):
        import os
        import time as clock

        from app import app
        from core import config

        client = app.test_client()
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}),                 mock.patch("routes.cache.refresh_library_cache_incremental_with_progress",
                           return_value={"count": 3, "rebuilt": 1, "reused": 2}),                 mock.patch("routes.cache.rebuild_library_cache_full_with_progress", return_value={"count": 3}),                 mock.patch("routes.cache.notify"):
            for path, expected in (("/api/v1/library/refresh", "Incremental refresh done: 3 entries, 1 rebuilt"),
                                   ("/api/v1/library/rebuild", "Full rebuild done: 3 entries")):
                task_id = client.post(path).get_json()["task_id"]
                for _ in range(50):
                    task = config.TASKS.get(task_id) or {}
                    if task.get("done"):
                        break
                    clock.sleep(0.05)
                self.assertEqual(expected, task.get("message"))


if __name__ == "__main__":
    unittest.main()
