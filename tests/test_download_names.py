"""Names of downloaded files: each version and each disc its own file, and no
name too long for the disk."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf
from mutagen.flac import FLAC
from mutagen.id3 import ID3

from core import deezer_dl

EDITED = {"EXPLICIT_LYRICS_STATUS": 3}
EXPLICIT = {"EXPLICIT_LYRICS_STATUS": 1}


def song(title, version="", number=3, disc=1, artist="Artist", **extra):
    return {"SNG_TITLE": title, "VERSION": version, "TRACK_NUMBER": number, "DISK_NUMBER": disc, "ART_NAME": artist,
            **extra}


def album(title="Album", artist="Artist", **extra):
    return {"ALB_TITLE": title, "ALB_ART_NAME": artist, **extra}


def audio_file(path, deezer_id=None, fmt="FLAC"):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.zeros(2205, dtype="float32"), 22050, format=fmt)
    if fmt == "FLAC" and deezer_id:
        audio = FLAC(path)
        audio[deezer_dl.DEEZER_ID_TAG.lower()] = deezer_id
        audio.save()
    return path


class Names(unittest.TestCase):
    def test_a_remix_and_its_original_get_two_files(self):
        self.assertNotEqual(deezer_dl.track_filename(song("Song"), "flac"),
                            deezer_dl.track_filename(song("Song", "(Remix)"), "flac"))
        self.assertEqual("Artist - Song (Remix).flac", deezer_dl.track_filename(song("Song", "(Remix)"), "flac"))

    def test_a_version_already_in_the_title_is_not_added_twice(self):
        self.assertEqual("Song (Remix)", deezer_dl.song_title(song("Song (Remix)", "(Remix)")))

    def test_the_second_disc_has_its_own_names(self):
        first = deezer_dl.track_filename(song("Song", disc=1), "flac", with_number=True)
        second = deezer_dl.track_filename(song("Song", disc=2), "flac", with_number=True)
        self.assertEqual("03 - Artist Song.flac", first)
        self.assertEqual("2-03 - Artist Song.flac", second)

    def test_a_long_name_fits_the_disk(self):
        name = deezer_dl.track_filename(song("Ж" * 300), "flac")
        self.assertLessEqual(len(name.encode("utf-8")), 255)
        self.assertTrue(name.endswith(".flac"))
        name.encode("utf-8").decode("utf-8")


class Versions(unittest.TestCase):
    """The clean and explicit versions of one album, or two albums with one
    title, must not share a folder: the second would be mixed into the first."""

    def test_the_censored_album_has_its_own_folder(self):
        self.assertEqual("Artist - Album", deezer_dl.album_folder(album()))
        self.assertEqual("Artist - Album (Clean)", deezer_dl.album_folder(album(ALB_CENSORED=True)))

    def test_clean_is_not_added_to_a_title_that_says_it(self):
        self.assertEqual("Artist - Album (Clean)", deezer_dl.album_folder(album("Album (Clean)", ALB_CENSORED=True)))
        self.assertEqual("Artist - Album [Edited]", deezer_dl.album_folder(album("Album [Edited]", ALB_CENSORED=True)))

    def test_the_folder_id_survives_a_long_name(self):
        name = deezer_dl.album_folder(album("Ж" * 300, ALB_ID="12345"), with_id=True)
        self.assertTrue(name.endswith(" [12345]"))
        self.assertLessEqual(len(name.encode("utf-8")), deezer_dl.MAX_NAME_BYTES)

    def test_a_censored_single_says_so_but_not_a_censored_album_track(self):
        clean = song("Famous", EXPLICIT_TRACK_CONTENT=EDITED)
        self.assertEqual("Artist - Famous (Clean).flac", deezer_dl.track_filename(clean, "flac"))
        self.assertEqual("Artist - Famous.flac", deezer_dl.track_filename(song("Famous", EXPLICIT_TRACK_CONTENT=EXPLICIT), "flac"))
        self.assertEqual("03 - Artist Famous.flac", deezer_dl.track_filename(clean, "flac", with_number=True))

    def test_a_single_with_its_id(self):
        self.assertEqual("Artist - Song [77].flac", deezer_dl.track_filename(song("Song", SNG_ID="77"), "flac", with_id=True))


class FakeSession:
    def __init__(self, page=None):
        self.page = page

    def gw(self, method, params):
        return self.page

    def sound_format(self):
        return "FLAC"


class FetchAlbum(unittest.TestCase):
    def fetch(self, album_content=None, tracks=()):
        data = {"ART_NAME": "Artist", "TITLE": "Album"}
        if album_content is not None:
            data["EXPLICIT_ALBUM_CONTENT"] = album_content
        page = {"DATA": data, "SONGS": {"data": [dict(song("T"), SNG_ID=str(i), EXPLICIT_TRACK_CONTENT=content)
                                                 for i, content in enumerate(tracks or [{}])]}}
        with mock.patch.object(deezer_dl, "session", return_value=FakeSession(page)):
            return deezer_dl.fetch_album(42)

    def test_an_album_marked_edited_is_censored(self):
        songs = self.fetch(EDITED, [{"EXPLICIT_LYRICS_STATUS": 0}, EDITED])
        self.assertTrue(all(s["ALB_CENSORED"] for s in songs))
        self.assertEqual({s["ALB_ID"] for s in songs}, {"42"})

    def test_one_edited_track_is_enough(self):
        self.assertTrue(self.fetch(None, [{"EXPLICIT_LYRICS_STATUS": 0}, EDITED])[0]["ALB_CENSORED"])

    def test_the_explicit_album_and_an_album_without_lyrics_are_not(self):
        self.assertFalse(self.fetch(EXPLICIT, [EXPLICIT])[0]["ALB_CENSORED"])
        self.assertFalse(self.fetch({"EXPLICIT_LYRICS_STATUS": 0}, [{"EXPLICIT_LYRICS_STATUS": 0}])[0]["ALB_CENSORED"])


class Folders(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patch = mock.patch.object(deezer_dl, "session", return_value=FakeSession())
        patch.start()
        self.addCleanup(patch.stop)
        self.downloaded = []

        def fake_download(song, target, on_bytes=None, on_note=None):
            self.downloaded.append(target)
            return audio_file(target, song["SNG_ID"])

        patch = mock.patch.object(deezer_dl, "download_song", side_effect=fake_download)
        patch.start()
        self.addCleanup(patch.stop)

    def release(self, album_id, song_id, censored=False):
        return [dict(song("Song", number=1), **album(), SNG_ID=song_id, ALB_ID=album_id, ALB_CENSORED=censored)]

    def download(self, songs):
        with mock.patch.object(deezer_dl, "fetch_album", return_value=songs):
            return deezer_dl.download_album(songs[0]["ALB_ID"], base_dir=self.root)

    def test_a_second_release_with_the_same_name_gets_its_own_folder(self):
        # The clean version downloaded before 1.21.1: no "(Clean)" in its folder.
        old = audio_file(self.root / "Artist - Album" / "01 - Artist Song.flac", "999")
        paths = self.download(self.release("55", "1"))
        self.assertEqual(paths[0].parent.name, "Artist - Album [55]")
        self.assertEqual(self.downloaded, paths)
        self.assertEqual(deezer_dl.file_deezer_id(old), "999")

    def test_the_same_release_again_reuses_its_folder(self):
        audio_file(self.root / "Artist - Album" / "01 - Artist Song.flac", "1")
        paths = self.download(self.release("55", "1"))
        self.assertEqual(paths[0].parent.name, "Artist - Album")
        self.assertEqual(self.downloaded, [])

    def test_untagged_files_do_not_move_the_album(self):
        audio_file(self.root / "Artist - Album" / "02 - Artist Other.flac")
        self.assertEqual(self.download(self.release("55", "1"))[0].parent.name, "Artist - Album")

    def test_clean_then_explicit_never_share_a_folder(self):
        clean = self.download(self.release("66", "2", censored=True))
        explicit = self.download(self.release("55", "1"))
        self.assertEqual((clean[0].parent.name, explicit[0].parent.name), ("Artist - Album (Clean)", "Artist - Album"))

    def test_a_single_with_the_name_of_another_track(self):
        audio_file(self.root / "Artist - Song.flac", "999")
        with mock.patch.object(deezer_dl, "fetch_track", return_value=song("Song", SNG_ID="1")):
            path = deezer_dl.download_track("1", base_dir=self.root)
            self.assertEqual(path.name, "Artist - Song [1].flac")
            self.assertEqual(deezer_dl.download_track("1", base_dir=self.root), path)
        self.assertEqual(self.downloaded, [path])


class Tags(unittest.TestCase):
    """Navidrome groups albums by tags: the censored one needs its own version."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for name in ("_cover", "_album_genre"):
            patch = mock.patch.object(deezer_dl, name, return_value=None)
            patch.start()
            self.addCleanup(patch.stop)

    def test_flac(self):
        path = audio_file(self.root / "a.flac")
        deezer_dl._write_tags(path, dict(song("S"), **album(ALB_CENSORED=True)), True)
        self.assertEqual(FLAC(path)["albumversion"], ["Clean"])
        other = audio_file(self.root / "b.flac")
        deezer_dl._write_tags(other, dict(song("S"), **album(ALB_CENSORED=False)), True)
        self.assertNotIn("albumversion", FLAC(other))

    def test_mp3_single(self):
        path = audio_file(self.root / "a.mp3", fmt="MP3")
        deezer_dl._write_tags(path, song("S", EXPLICIT_TRACK_CONTENT=EDITED), False)
        self.assertEqual(str(ID3(path)["TXXX:ALBUMVERSION"]), "Clean")


if __name__ == "__main__":
    unittest.main()
