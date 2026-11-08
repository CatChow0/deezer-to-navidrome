"""Every route the app serves, and the guarantee that each one asks for a sign-in
unless it is meant to be public. New routes (Navidrome accounts, then the
mobile API) are covered without having to remember to add a test."""
import os
import unittest
from unittest import mock

PUBLIC = {"auth.login", "auth.setup", "static", "system.favicon", "system.health",
          "listenbrainz.submit", "listenbrainz.submit_slash", "listenbrainz.validate", "listenbrainz.validate_slash"}


def sample_url(rule):
    values = {}
    for name, converter in rule._converters.items():
        kind = type(converter).__name__
        if kind == "IntegerConverter":
            values[name] = 1
        elif kind == "AnyConverter":
            values[name] = sorted(converter.items)[0] if hasattr(converter, "items") else "track"
        else:
            values[name] = "x"
    return rule.build(values)[1]


class Inventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("DISABLE_AUTH", None)
        account = mock.patch("core.auth.account_exists", return_value=True)
        account.start()
        self.addCleanup(account.stop)

    def routes(self):
        for rule in self.app.url_map.iter_rules():
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                yield rule, method

    def test_the_public_list_matches_the_app(self):
        from app import PUBLIC_ENDPOINTS
        self.assertEqual(PUBLIC_ENDPOINTS, PUBLIC)

    def test_every_other_route_needs_a_sign_in(self):
        client = self.app.test_client()
        checked = 0
        for rule, method in self.routes():
            if rule.endpoint in PUBLIC:
                continue
            url = sample_url(rule)
            response = client.open(url, method=method, headers={"Accept": "application/json"})
            self.assertEqual(response.status_code, 401, f"{method} {rule.rule} answered {response.status_code}")
            checked += 1
        self.assertGreater(checked, 90)

    def test_a_page_redirects_to_the_sign_in(self):
        response = self.app.test_client().get("/", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
