"""Sorting the album folders where two releases with one name were mixed
before 1.21.1 (the explicit and clean versions of The Life of Pablo)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TXXX

from core import deezer_dl, download_sort

EXPLICIT, CLEAN, OTHER = "55", "66", "77"
ALBUMS = {
    EXPLICIT: {"tracks": ["1", "2", "3"], "censored": False},
    CLEAN: {"tracks": ["11", "12", "13"], "censored": True},
    OTHER: {"tracks": ["21", "22"], "censored": False},
}
TRACK_ALBUM = {track: album for album, info in ALBUMS.items() for track in info["tracks"]}


def fetch_album(album_id):
    info = ALBUMS[album_id]
    return [{"SNG_ID": track, "ALB_ID": album_id, "ALB_TITLE": "Album", "ALB_ART_NAME": "Artist",
             "ALB_CENSORED": info["censored"]} for track in info["tracks"]]


def audio_file(path, deezer_id=None, fmt="FLAC"):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.zeros(22050, dtype="float32"), 22050, format=fmt)
    if deezer_id:
        if fmt == "FLAC":
            audio = FLAC(path)
            audio[deezer_dl.DEEZER_ID_TAG.lower()] = deezer_id
            audio.save()
        else:
            tags = ID3()
            tags.add(TXXX(encoding=3, desc=deezer_dl.DEEZER_ID_TAG, text=deezer_id))
            tags.save(path, v2_version=3)
    return path


def album_version(path):
    if path.suffix == ".flac":
        return FLAC(path).get("albumversion")
    return EasyID3(path).get("albumversion")


class Sort(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.albums = self.root / "albums"
        for target, value in ((deezer_dl, "download_dir"), (download_sort, "PAUSE")):
            patch = (mock.patch.object(target, value, return_value=self.root) if value == "download_dir"
                     else mock.patch.object(target, value, 0))
            patch.start()
            self.addCleanup(patch.stop)
        self.lookups = []

    def lookup(self, track_id):
        self.lookups.append(track_id)
        return TRACK_ALBUM.get(track_id)

    def sort(self):
        return download_sort.sort_albums(lookup_album=self.lookup, fetch_album=fetch_album)

    def names(self, folder):
        return sorted(p.name for p in (self.albums / folder).iterdir())

    def test_the_two_versions_are_sorted_and_queued_again(self):
        mixed = self.albums / "Artist - Album"
        audio_file(mixed / "01 - Artist A.flac", "11")
        audio_file(mixed / "02 - Artist B.flac", "2")
        audio_file(mixed / "03 - Artist C.flac", "13")
        summary = self.sort()
        self.assertEqual(self.names("Artist - Album"), ["02 - Artist B.flac"])
        self.assertEqual(self.names("Artist - Album (Clean)"), ["01 - Artist A.flac", "03 - Artist C.flac"])
        for name in self.names("Artist - Album (Clean)"):
            self.assertEqual(album_version(self.albums / "Artist - Album (Clean)" / name), ["Clean"])
        self.assertIsNone(album_version(mixed / "02 - Artist B.flac"))
        self.assertEqual(summary["sorted"], ["Artist - Album"])
        self.assertEqual(summary["moved"], 2)
        self.assertEqual({r["id"] for r in summary["refill"]}, {EXPLICIT, CLEAN})
        # One lookup per release, not one per file.
        self.assertEqual(len(self.lookups), 2)

    def test_a_second_explicit_release_with_the_name_gets_its_id(self):
        mixed = self.albums / "Artist - Album"
        audio_file(mixed / "01 - Artist A.flac", "1")
        audio_file(mixed / "02 - Artist B.flac", "2")
        audio_file(mixed / "01 - Artist X.flac", "21")
        self.sort()
        self.assertEqual(self.names("Artist - Album"), ["01 - Artist A.flac", "02 - Artist B.flac"])
        self.assertEqual(self.names(f"Artist - Album [{OTHER}]"), ["01 - Artist X.flac"])

    def test_a_clean_album_alone_gets_its_tag_and_stays(self):
        clean = self.albums / "Artist - Album"
        audio_file(clean / "01 - Artist A.flac", "11")
        audio_file(clean / "02 - Artist B.mp3", "12", fmt="MP3")
        summary = self.sort()
        self.assertEqual(self.names("Artist - Album"), ["01 - Artist A.flac", "02 - Artist B.mp3"])
        self.assertEqual(album_version(clean / "01 - Artist A.flac"), ["Clean"])
        self.assertEqual(album_version(clean / "02 - Artist B.mp3"), ["Clean"])
        self.assertEqual((summary["tagged"], summary["sorted"], summary["refill"]), (2, [], []))
        # Already tagged: nothing to write the second time.
        self.assertEqual(self.sort()["tagged"], 0)

    def test_an_explicit_album_alone_is_left_alone(self):
        audio_file(self.albums / "Artist - Album" / "01 - Artist A.flac", "1")
        summary = self.sort()
        self.assertEqual((summary["tagged"], summary["sorted"], summary["moved"]), (0, [], 0))

    def test_files_it_cannot_place_stay_where_they_are(self):
        folder = self.albums / "Artist - Album"
        audio_file(folder / "01 - Artist A.flac", "1")
        audio_file(folder / "02 - Artist Unknown.flac", "999")
        audio_file(folder / "03 - Artist By hand.flac")
        summary = self.sort()
        self.assertEqual(len(self.names("Artist - Album")), 3)
        self.assertEqual(summary["unknown"], ["Artist - Album/02 - Artist Unknown.flac"])
        self.assertEqual(summary["sorted"], [])

    def test_a_file_already_in_the_target_is_not_overwritten(self):
        mixed = self.albums / "Artist - Album"
        audio_file(mixed / "01 - Artist A.flac", "1")
        audio_file(mixed / "01 - Artist C.flac", "11")
        audio_file(self.albums / "Artist - Album (Clean)" / "01 - Artist C.flac", "11")
        summary = self.sort()
        self.assertIn("01 - Artist C.flac", self.names("Artist - Album"))
        self.assertEqual(summary["left"], ["Artist - Album/01 - Artist C.flac"])

    def test_it_stops_when_asked(self):
        audio_file(self.albums / "Artist - Album" / "01 - Artist A.flac", "11")
        summary = download_sort.sort_albums(lookup_album=self.lookup, fetch_album=fetch_album, should_stop=lambda: True)
        self.assertTrue(summary["cancelled"])
        self.assertEqual(self.lookups, [])

    def test_no_albums_folder(self):
        self.assertEqual(self.sort()["folders"], 0)


class Task(unittest.TestCase):
    """Repair downloads: the decryption repair, then the albums."""

    REPAIRED = {"checked": 3, "repaired": [], "fine": 3, "unknown": [], "errors": [], "cancelled": False}

    def albums(self, **changes):
        return {"folders": 4, "sorted": ["Artist - Album"], "moved": 2, "tagged": 2, "unknown": [], "left": [],
                "errors": [], "refill": [{"id": EXPLICIT, "label": "Artist - Album"},
                                         {"id": CLEAN, "label": "Artist - Album (Clean)"}],
                "cancelled": False, **changes}

    def run_task(self, repaired=None, albums=None):
        from routes import system

        events, cancelled, queued = [], [], []
        with mock.patch("core.download_repair.repair_downloads", return_value=repaired or self.REPAIRED), \
                mock.patch("core.download_sort.sort_albums", return_value=albums) as sort, \
                mock.patch.object(system, "push_task_event", side_effect=lambda *a, **k: events.append((a, k))), \
                mock.patch.object(system, "finish_cancelled", side_effect=lambda task, message: cancelled.append(message)), \
                mock.patch.object(system, "_start_download",
                                  side_effect=lambda kind, music_id, label, deezer_account=None: queued.append((kind, music_id))):
            system._run_repair("t1", "dz1")
        return events, cancelled, queued, sort

    def test_the_albums_are_queued_and_the_message_says_it(self):
        events, cancelled, queued, _ = self.run_task(albums=self.albums())
        self.assertEqual(queued, [("album", EXPLICIT), ("album", CLEAN)])
        message = events[-1][0][1]
        self.assertIn("1 mixed folder sorted", message)
        self.assertIn("2 albums queued for their missing tracks", message)
        self.assertIn("Refresh the library", message)
        self.assertEqual(cancelled, [])

    def test_sorted_albums_are_queued_even_when_cancelled(self):
        _, cancelled, queued, _ = self.run_task(albums=self.albums(cancelled=True))
        self.assertEqual(len(queued), 2)
        self.assertIn("Cancelled while sorting the albums", cancelled[0])

    def test_a_cancelled_repair_does_not_sort(self):
        _, cancelled, queued, sort = self.run_task(repaired=dict(self.REPAIRED, cancelled=True))
        sort.assert_not_called()
        self.assertEqual(queued, [])
        self.assertEqual(len(cancelled), 1)

    def test_nothing_mixed(self):
        events, _, queued, _ = self.run_task(albums=self.albums(sorted=[], moved=0, tagged=0, refill=[]))
        self.assertEqual(queued, [])
        self.assertIn("albums: none mixed", events[-1][0][1])
        self.assertNotIn("Refresh the library", events[-1][0][1])


if __name__ == "__main__":
    unittest.main()
