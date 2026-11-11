"""The .m3u8 files: one folder per playlist, kept when its title changes, never
outside the playlists folder, and written even when one track is unmapped."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import deezer, publish
from core.utils import sanitize_filename


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.library = self.root / "library"
        self.library.mkdir()
        self.playlists = self.root / "nested" / "playlists"
        paths = ([self.library], self.playlists, self.root / "cache.json",
                 {self.library: Path("/music"), self.playlists: Path("/playlists")})
        for target in ("core.deezer.get_paths_from_config", "core.config.get_paths_from_config"):
            patcher = mock.patch(target, return_value=paths)
            patcher.start()
            self.addCleanup(patcher.stop)
        deezer.save_playlists([])
        self.addCleanup(deezer.save_playlists, [])

    def rows(self, *paths):
        return [{"number": i, "matched": True, "local_path": str(p), "deezer_name": f"T{i}"}
                for i, p in enumerate(paths, start=1)]

    def write(self, playlist_id, title, rows=None):
        return deezer.write_playlist_outputs(playlist_id, title, rows or self.rows(self.library / "a.flac"))[0]


class Folders(Base):
    def test_two_playlists_with_one_title_keep_their_own_files(self):
        deezer.add_entry({"id": "111", "title": "Chill", "picture": ""})
        deezer.add_entry({"id": "xp-csv-chill", "title": "Chill", "picture": ""})
        first, second = self.write("111", "Chill"), self.write("xp-csv-chill", "Chill")
        self.assertNotEqual(first, second)
        self.assertEqual(self.playlists / "Chill" / "Chill.m3u8", first)
        publish.remove_file("xp-csv-chill", "Chill")
        self.assertTrue(first.exists())
        self.assertFalse(second.exists())

    def test_a_title_changed_on_deezer_keeps_its_file(self):
        deezer.add_entry({"id": "222", "title": "Old", "picture": ""})
        first = self.write("222", "Old")
        self.assertEqual(first, self.write("222", "New name"))
        self.assertEqual(first, publish.remove_file("222", "New name"))
        self.assertFalse(first.exists())

    def test_a_title_of_dots_stays_in_the_playlists_folder(self):
        deezer.add_entry({"id": "333", "title": "..", "picture": ""})
        path = self.write("333", "..")
        self.assertIn(self.playlists, path.parents)
        self.assertFalse((self.playlists.parent / "report.json").exists())

    def test_one_unmapped_track_leaves_the_others_written(self):
        deezer.add_entry({"id": "444", "title": "Mixed", "picture": ""})
        elsewhere = self.root / "elsewhere" / "b.flac"
        path = self.write("444", "Mixed", self.rows(self.library / "a.flac", elsewhere))
        self.assertEqual(["#EXTM3U", "../../music/a.flac", ""], path.read_text(encoding="utf-8").split("\n"))


class Names(unittest.TestCase):
    def test_unsafe_names(self):
        self.assertEqual("", sanitize_filename(".."))
        self.assertEqual("a_b", sanitize_filename("a/b"))
        self.assertEqual("NUL_", sanitize_filename("NUL"))
        self.assertEqual("Song", sanitize_filename(" Song. "))


if __name__ == "__main__":
    unittest.main()
