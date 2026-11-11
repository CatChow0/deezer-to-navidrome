"""Duplicate removal never removes every copy of a track, and what goes to the
quarantine can be put back."""
import json
import tempfile
import unittest
from pathlib import Path

from core import config, dedup


def group(group_id, paths, artist="Artist", title="Song"):
    return {"group_id": group_id, "identity": {"artist": artist, "album": "Album", "base_title": title,
                                               "version_flags": []},
            "entries": [{"path_str": p} for p in paths], "keeper": {"path_str": paths[0]}}


class Base(unittest.TestCase):
    def setUp(self):
        self.music = Path(tempfile.mkdtemp())
        self.addCleanup(config.clear_dedup_choices_file)
        self.addCleanup(config.clear_dedup_report_file)
        config.clear_dedup_choices_file()

    def file(self, name):
        path = self.music / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return str(path)


class Hints(Base):
    def test_a_kept_file_moved_since_is_not_hinted(self):
        old, renamed, new = str(self.music / "a.flac"), str(self.music / "a2.flac"), str(self.music / "b.flac")
        dedup.save_dedup_choices({dedup.dedup_group_key(group("g", [old])): {"keep_paths": [old]}})
        filtered, hints = dedup.filter_and_preselect_dedup_groups([group("g", [renamed, new])])
        self.assertEqual(1, len(filtered))
        self.assertEqual({}, hints)

    def test_a_kept_file_still_there_is_hinted(self):
        kept, new = str(self.music / "a.flac"), str(self.music / "b.flac")
        dedup.save_dedup_choices({dedup.dedup_group_key(group("g", [kept])): {"keep_paths": [kept]}})
        _, hints = dedup.filter_and_preselect_dedup_groups([group("g", [kept, new])])
        self.assertEqual({"g": [kept]}, hints)


class Sizes(unittest.TestCase):
    def test_the_report_keeps_each_file_size(self):
        from core.normalization import normalize_entry

        self.assertEqual(1234, normalize_entry({"path_str": "/a.flac", "size": 1234})["size"])


class Groups(unittest.TestCase):
    def test_two_copies_make_one_group_with_their_sizes(self):
        from core.normalization import enrich_library_entry_for_dedup

        def entry(path, size):
            return enrich_library_entry_for_dedup({"path": path, "path_str": path, "size": size, "duration": 200,
                                                   "tag_artist": "Artist", "tag_title": "Song", "tag_album": "Album"})

        groups, _ = dedup.build_dedup_groups([entry("/m/a/Song.flac", 30_000_000), entry("/m/b/Song.mp3", 8_000_000)])
        self.assertEqual(1, len(groups))
        self.assertEqual("/m/a/Song.flac", groups[0]["keeper"]["path_str"])
        sizes = sorted(e["size"] for folder in groups[0]["folders"] for e in folder["entries"])
        self.assertEqual([8_000_000, 30_000_000], sizes)


class Apply(Base):
    def test_keeping_none_of_the_copies_removes_nothing(self):
        a, b = self.file("a.flac"), self.file("b.flac")
        dedup.save_dedup_report({"groups": [group("g", [a, b])]})
        result = dedup.apply_dedup_decisions([{"group_id": "g", "keep_paths": [str(self.music / "gone.flac")]}],
                                             mode="delete")
        self.assertEqual((0, ["g"]), (result["processed"], result["skipped"]))
        self.assertTrue(Path(a).exists() and Path(b).exists())

    def test_a_decision_that_is_not_an_object_is_ignored(self):
        a, b = self.file("a.flac"), self.file("b.flac")
        dedup.save_dedup_report({"groups": [group("g", [a, b])]})
        result = dedup.apply_dedup_decisions(["g", {"group_id": "g", "keep_paths": [a]}], mode="delete")
        self.assertEqual(1, result["processed"])
        self.assertFalse(Path(b).exists())

    def test_the_quarantine_remembers_where_each_file_was(self):
        a, b = self.file("x/song.flac"), self.file("y/song.flac")
        dedup.save_dedup_report({"groups": [group("g", [a, b])]})
        self.addCleanup(lambda: [p.unlink() for p in config.DEDUP_QUARANTINE_DIR.glob("*")])
        result = dedup.apply_dedup_decisions([{"group_id": "g", "keep_paths": [a]}], mode="quarantine")
        target = result["results"][0]["target"]
        lines = (config.DEDUP_QUARANTINE_DIR / dedup.QUARANTINE_MANIFEST).read_text(encoding="utf-8").splitlines()
        self.assertIn({"from": b, "to": target}, [{k: v for k, v in json.loads(l).items() if k != "at"} for l in lines])
        self.assertTrue(Path(target).exists())


if __name__ == "__main__":
    unittest.main()
