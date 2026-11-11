"""The favorite artists the release feed follows: through the account's own
session (gateway), which sees a private profile too; the public API stands in
should the gateway change."""
import unittest
from unittest import mock

import requests

from core import deezer_account

PRIVATE = {"error": {"type": "OAuthException",
                     "message": "An active access token must be used. This user's profile is private",
                     "code": 200}}

PROFILE = {"TAB": {"artists": {"data": [
    {"ART_ID": "27", "ART_NAME": "Daft Punk", "ART_PICTURE": "abc"},
    {"ART_ID": 1424821, "ART_NAME": "Vald", "ART_PICTURE": ""},
], "total": 2}}}


def answer(payload):
    response = mock.Mock()
    response.json.return_value = payload
    return response


class FavoriteArtists(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(deezer_account, "_user_id", return_value="101")
        patch.start()
        self.addCleanup(patch.stop)

    def test_read_through_the_accounts_own_session_private_or_not(self):
        with mock.patch.object(deezer_account, "_gw", return_value=PROFILE) as gw, \
                mock.patch.object(deezer_account.requests, "get") as public:
            artists = deezer_account.favorite_artists("acc")
        self.assertEqual(["27", "1424821"], [a["id"] for a in artists])
        self.assertEqual(["Daft Punk", "Vald"], [a["name"] for a in artists])
        self.assertIn("/images/artist/abc/250x250", artists[0]["picture"])
        self.assertEqual("", artists[1]["picture"])
        method, body = gw.call_args.args
        self.assertEqual("deezer.pageProfile", method)
        self.assertEqual({"USER_ID": "101", "tab": "artists"}, {k: body[k] for k in ("USER_ID", "tab")})
        self.assertEqual("acc", gw.call_args.kwargs["account"])
        public.assert_not_called()

    def test_no_favorites_is_an_empty_list(self):
        with mock.patch.object(deezer_account, "_gw", return_value={"TAB": {"artists": {"data": [], "total": 0}}}), \
                mock.patch.object(deezer_account.requests, "get") as public:
            self.assertEqual([], deezer_account.favorite_artists("acc"))
        public.assert_not_called()

    def test_the_public_api_stands_in_when_the_gateway_changes(self):
        pages = [answer({"data": [{"id": 27, "name": "Daft Punk", "picture_medium": "https://p/27"}], "total": 1})]
        for failure in (deezer_account.DeezerAccountError("Deezer refused deezer.pageProfile: METHOD_NOT_FOUND"),
                        ValueError("not JSON"), requests.ConnectionError("reset")):
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch.object(deezer_account, "_gw", side_effect=failure), \
                    mock.patch.object(deezer_account.requests, "get", side_effect=list(pages)):
                artists = deezer_account.favorite_artists("acc")
            self.assertEqual([{"id": "27", "name": "Daft Punk", "picture": "https://p/27"}], artists)

    def test_an_answer_of_another_shape_is_not_an_empty_feed(self):
        pages = [answer({"data": [{"id": 27, "name": "Daft Punk", "picture_medium": ""}], "total": 1})]
        with mock.patch.object(deezer_account, "_gw", return_value={"DATA": {}}), \
                mock.patch.object(deezer_account.requests, "get", side_effect=pages):
            self.assertEqual(["27"], [a["id"] for a in deezer_account.favorite_artists("acc")])

    def test_both_refusing_says_why(self):
        with mock.patch.object(deezer_account, "_gw", return_value={"DATA": {}}), \
                mock.patch.object(deezer_account.requests, "get", return_value=answer(PRIVATE)):
            with self.assertRaises(deezer_account.DeezerAccountError) as caught:
                deezer_account.favorite_artists("acc")
        message = str(caught.exception)
        self.assertTrue(message.startswith("Deezer refused the favorite artists list"), message)
        self.assertIn("profile page holds no artists list", message)
        self.assertIn("profile is private", message)
        self.assertEqual(1, message.count("Deezer refused the favorite artists list"))


if __name__ == "__main__":
    unittest.main()
