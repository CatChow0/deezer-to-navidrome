"""Imported playlists: a Deezer outage leaves tracks to be found, it does not
mark them "not on Deezer" for good."""
import unittest
from unittest import mock

import requests

from core import crossplatform


class Outage(unittest.TestCase):
    def test_no_answer_at_all_is_not_a_verdict(self):
        with mock.patch("core.deezer._public_api", side_effect=requests.ConnectionError("down")):
            self.assertIsNone(crossplatform.match_track({"title": "Song", "artists": ["Artist"], "isrc": "FR1234567890", "album": "", "duration": 200}))

    def test_an_answer_with_nothing_found_is_a_verdict(self):
        with mock.patch("core.deezer._public_api", return_value={"data": []}):
            pick = crossplatform.match_track({"title": "Song", "artists": ["Artist"], "album": "", "duration": 200})
        self.assertEqual("none", pick["status"])


if __name__ == "__main__":
    unittest.main()
