"""The account's own Deezer playlists, read from its profile page: Loved tracks,
those it made and those it added to its favorites, private ones too."""
import unittest
from unittest import mock

from core import deezer_account

PROFILE = {"TAB": {"playlists": {"data": [
    {"PLAYLIST_ID": "900", "TITLE": "Chill", "PARENT_USER_ID": "55", "PARENT_USERNAME": "Deezer Editors",
     "PLAYLIST_PICTURE": "fav", "PICTURE_TYPE": "playlist", "NB_SONG": "80"},
    {"PLAYLIST_ID": 123, "TITLE": "Road trip", "PARENT_USER_ID": 101, "PLAYLIST_PICTURE": "road", "NB_SONG": 58},
    {"PLAYLIST_ID": "777", "TITLE": "Loved Tracks", "PARENT_USER_ID": "101", "PLAYLIST_PICTURE": "heart",
     "PICTURE_TYPE": "cover", "NB_SONG": "412"},
    {"PLAYLIST_ID": "", "TITLE": "broken"},
]}}}


class AccountPlaylists(unittest.TestCase):
    def setUp(self):
        session = mock.Mock(user={"id": "101", "name": "me", "loved": "777"})
        patch = mock.patch.object(deezer_account, "_session_for", return_value=session)
        patch.start()
        self.addCleanup(patch.stop)

    def test_loved_tracks_then_made_then_favorites(self):
        with mock.patch.object(deezer_account, "_gw", return_value=PROFILE) as gw:
            found = deezer_account.account_playlists("dz1")
        self.assertEqual([("777", "Loved tracks"), ("123", "Created by you"), ("900", "Favorites")],
                         [(p["id"], p["group"]) for p in found])
        self.assertEqual([412, 58, 80], [p["tracks"] for p in found])
        self.assertEqual("Deezer Editors", found[2]["subtitle"])
        self.assertIn("/images/cover/heart/250x250", found[0]["picture"])
        method, body = gw.call_args.args
        self.assertEqual(("deezer.pageProfile", "101", "playlists"), (method, body["USER_ID"], body["tab"]))
        self.assertEqual("dz1", gw.call_args.kwargs["account"])

    def test_an_answer_of_another_shape_is_said_not_shown_empty(self):
        with mock.patch.object(deezer_account, "_gw", return_value={"DATA": {}}):
            with self.assertRaises(deezer_account.DeezerAccountError):
                deezer_account.account_playlists()


class Covers(unittest.TestCase):
    def test_an_albums_cover_is_asked_as_such(self):
        page = {"DATA": {"TITLE": "Initial D", "PLAYLIST_PICTURE": "alb", "PICTURE_TYPE": "cover", "NB_SONG": 12}}
        with mock.patch.object(deezer_account, "_gw", return_value=page):
            self.assertIn("/images/cover/alb/1000x1000", deezer_account.playlist_info(5)["picture"])

    def test_playlists_saved_with_the_placeholder_ask_again_once(self):
        import tempfile
        from pathlib import Path

        from core import migrations
        from core.deezer import saved_entries, save_playlists

        entries = [{"id": "5", "title": "Initial D", "picture": "https://e-cdns-images.dzcdn.net/images/playlist/alb/1000x1000.jpg"},
                   {"id": "6", "title": "Pink", "picture": "https://e-cdns-images.dzcdn.net/images/cover/x/1000x1000.jpg"}]
        save_playlists(entries)
        self.addCleanup(save_playlists, [])
        with tempfile.TemporaryDirectory() as folder:
            covers = Path(folder)
            (covers / "5.jpg").write_bytes(b"grey")
            with mock.patch("core.config.COVERS_DIR", covers), mock.patch("core.config.DATA_DIR", covers):
                self.assertEqual(1, migrations.playlist_covers())
                self.assertEqual(["", entries[1]["picture"]], [e["picture"] for e in saved_entries()])
                self.assertFalse((covers / "5.jpg").exists())
                save_playlists(entries)
                self.assertEqual(0, migrations.playlist_covers())


if __name__ == "__main__":
    unittest.main()
