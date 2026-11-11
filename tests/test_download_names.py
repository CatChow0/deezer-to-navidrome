"""Names of downloaded files: each version and each disc its own file, and no
name too long for the disk."""
import unittest

from core import deezer_dl


def song(title, version="", number=3, disc=1, artist="Artist"):
    return {"SNG_TITLE": title, "VERSION": version, "TRACK_NUMBER": number, "DISK_NUMBER": disc, "ART_NAME": artist}


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


if __name__ == "__main__":
    unittest.main()
