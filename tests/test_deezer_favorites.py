"""The favorite artists the release feed follows: from the public API for a
public profile, through the account's own session for a private one."""
import unittest
from unittest import mock

from core import deezer_account

PRIVATE = {"error": {"type": "OAuthException",
                     "message": "An active access token must be used. This user's profile is private",
                     "code": 200}}


def answer(payload):
    response = mock.Mock()
    response.json.return_value = payload
    return response


class FavoriteArtists(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(deezer_account, "_user_id", return_value="101")
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_public_profile_is_read_from_the_public_api(self):
        pages = [answer({"data": [{"id": 27, "name": "Daft Punk", "picture_medium": "https://p/27"}], "total": 1})]
        with mock.patch.object(deezer_account.requests, "get", side_effect=pages), \
                mock.patch.object(deezer_account, "_gw") as gw:
            artists = deezer_account.favorite_artists("acc")
        self.assertEqual([{"id": "27", "name": "Daft Punk", "picture": "https://p/27"}], artists)
        gw.assert_not_called()

    def test_a_private_profile_is_read_through_the_accounts_own_session(self):
        page = {"TAB": {"artists": {"data": [
            {"ART_ID": "27", "ART_NAME": "Daft Punk", "ART_PICTURE": "abc"},
            {"ART_ID": 1424821, "ART_NAME": "Vald", "ART_PICTURE": ""},
        ], "total": 2}}}
        with mock.patch.object(deezer_account.requests, "get", return_value=answer(PRIVATE)), \
                mock.patch.object(deezer_account, "_gw", return_value=page) as gw:
            artists = deezer_account.favorite_artists("acc")
        self.assertEqual(["27", "1424821"], [a["id"] for a in artists])
        self.assertEqual(["Daft Punk", "Vald"], [a["name"] for a in artists])
        self.assertIn("/images/artist/abc/250x250", artists[0]["picture"])
        self.assertEqual("", artists[1]["picture"])
        method, body = gw.call_args.args
        self.assertEqual("deezer.pageProfile", method)
        self.assertEqual({"USER_ID": "101", "tab": "artists"}, {k: body[k] for k in ("USER_ID", "tab")})
        self.assertEqual("acc", gw.call_args.kwargs["account"])

    def test_both_refusing_says_why_instead_of_an_empty_feed(self):
        with mock.patch.object(deezer_account.requests, "get", return_value=answer(PRIVATE)), \
                mock.patch.object(deezer_account, "_gw", return_value={"DATA": {}}):
            with self.assertRaises(deezer_account.DeezerAccountError) as caught:
                deezer_account.favorite_artists("acc")
        self.assertIn("profile is private", str(caught.exception))
        self.assertIn("own session", str(caught.exception))

    def test_a_private_profile_without_favorites_is_an_empty_list(self):
        with mock.patch.object(deezer_account.requests, "get", return_value=answer(PRIVATE)), \
                mock.patch.object(deezer_account, "_gw", return_value={"TAB": {"artists": {"data": [], "total": 0}}}):
            self.assertEqual([], deezer_account.favorite_artists("acc"))


if __name__ == "__main__":
    unittest.main()
