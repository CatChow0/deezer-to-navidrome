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


if __name__ == "__main__":
    unittest.main()
