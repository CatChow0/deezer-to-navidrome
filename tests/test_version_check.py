"""The check for a newer version asks GitHub at most once an hour, also when
there is nothing newer."""
import unittest
from unittest import mock

from core import version


class Cache(unittest.TestCase):
    def setUp(self):
        saved = dict(version.VERSION_CHECK_CACHE)
        self.addCleanup(version.VERSION_CHECK_CACHE.update, saved)
        version.VERSION_CHECK_CACHE.update({"cached_at": 0, "latest_version": None, "latest_url": None})

    def test_up_to_date_is_remembered(self):
        with mock.patch.object(version, "fetch_latest_github_release", return_value=(None, None)) as github, \
                mock.patch.object(version, "fetch_latest_docker_tag", return_value=(None, None)):
            version.get_latest_available_version()
            version.get_latest_available_version()
        self.assertEqual(1, github.call_count)


if __name__ == "__main__":
    unittest.main()
