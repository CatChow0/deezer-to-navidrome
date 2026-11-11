import io
import json
import logging
import os
import unittest
from pathlib import Path
from unittest import mock

from core import config, navidrome_db, nd_accounts
from tests.fake_subsonic import FakeSubsonic
from tests.fixtures import add_navidrome_users, make_navidrome

SECRET = "pw-SENTINEL-31337"


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        Path(config.DATA_DIR, "navidrome_accounts.json").unlink(missing_ok=True)
        nd_accounts.ensure_initial()
        self.nav = Path(config.DATA_DIR) / "test-navidrome.db"
        self.nav.unlink(missing_ok=True)
        patches = [mock.patch.dict(os.environ, {"DISABLE_AUTH": "true", "STATS_NAVIDROME_DB": str(self.nav)})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        navidrome_db.forget()
        self.addCleanup(navidrome_db.forget)
        self.server = FakeSubsonic().start()
        self.addCleanup(self.server.stop)
        self.server.add_user("alice", SECRET, admin=True)
        self.client = self.app.test_client()
        # Every log line of the test, to look for the secret in it.
        self.log = io.StringIO()
        handler = logging.StreamHandler(self.log)
        handler.setLevel(logging.DEBUG)
        root = logging.getLogger()
        previous = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)
        self.addCleanup(lambda: (root.removeHandler(handler), root.setLevel(previous)))

    def add(self, **fields):
        body = {"label": "Alice", "url": self.server.url, "username": "alice", "secret": SECRET, **fields}
        return self.client.post("/api/navidrome/accounts", json=body)

    def assert_no_secret(self, *responses):
        for response in responses:
            self.assertNotIn(SECRET, response.get_data(as_text=True))
        self.assertNotIn(SECRET, self.log.getvalue())
        self.assertNotIn(SECRET, Path(config.DATA_DIR, "navidrome_accounts.json").read_text(encoding="utf-8"))
        config_file = Path(config.DATA_DIR, "config.json")
        if config_file.exists():
            self.assertNotIn(SECRET, config_file.read_text(encoding="utf-8"))

    def test_the_install_starts_with_nd1(self):
        data = self.client.get("/api/navidrome/accounts").get_json()
        self.assertEqual([a["id"] for a in data["accounts"]], ["nd1"])
        self.assertEqual(data["active"], "nd1")
        self.assertIn(data["encryption"]["source"], ("env", "file"))

    def test_add_test_edit_and_remove_without_leaking_the_secret(self):
        created = self.add()
        self.assertEqual(created.status_code, 200, created.get_json())
        account_id = created.get_json()["created"]
        tested = self.client.post(f"/api/navidrome/accounts/{account_id}/test")
        result = tested.get_json()["test"]
        self.assertTrue(result["ok"], result)
        self.assertIs(result["admin"], True)
        edited = self.client.patch(f"/api/navidrome/accounts/{account_id}", json={"label": "Alice B", "secret": ""})
        self.assertEqual(next(a for a in edited.get_json()["accounts"] if a["id"] == account_id)["label"], "Alice B")
        listed = self.client.get("/api/navidrome/accounts")
        removed = self.client.delete(f"/api/navidrome/accounts/{account_id}")
        self.assertEqual([a["id"] for a in removed.get_json()["accounts"]], ["nd1"])
        self.assert_no_secret(created, tested, edited, listed, removed)

    def test_a_failed_test_is_said_and_kept(self):
        account_id = self.add(secret="wrong-password").get_json()["created"]
        data = self.client.post(f"/api/navidrome/accounts/{account_id}/test").get_json()
        self.assertFalse(data["test"]["ok"])
        self.assertEqual(data["test"]["error"], "Wrong user name or password.")
        saved = next(a for a in data["accounts"] if a["id"] == account_id)
        self.assertFalse(saved["last_test"]["ok"])

    def test_testing_before_saving_and_with_the_saved_password(self):
        response = self.client.post("/api/navidrome/accounts/test",
                                    json={"url": self.server.url, "username": "alice", "secret": SECRET})
        self.assertTrue(response.get_json()["test"]["ok"])
        account_id = self.add().get_json()["created"]
        again = self.client.post("/api/navidrome/accounts/test",
                                 json={"id": account_id, "url": self.server.url, "username": "alice", "secret": ""})
        self.assertTrue(again.get_json()["test"]["ok"])
        self.assert_no_secret(response, again)

    def test_the_saved_password_never_goes_to_another_address(self):
        account_id = self.add().get_json()["created"]
        other = FakeSubsonic().start()
        self.addCleanup(other.stop)
        response = self.client.post("/api/navidrome/accounts/test",
                                    json={"id": account_id, "url": other.url, "username": "alice", "secret": ""})
        self.assertEqual(400, response.status_code)
        self.assertEqual([], other.requests)

    def test_another_server_needs_the_password_again(self):
        account_id = self.add().get_json()["created"]
        moved = self.client.patch(f"/api/navidrome/accounts/{account_id}", json={"url": "https://elsewhere.example"})
        self.assertEqual(400, moved.status_code)
        self.assertIn("password again", moved.get_json()["error"])

    def test_the_same_server_over_https_keeps_its_password(self):
        self.assertTrue(nd_accounts.same_server("http://nas.lan", "https://nas.lan/navidrome"))
        self.assertTrue(nd_accounts.same_server("http://nas.lan:4533", "http://NAS.lan:4533/"))
        self.assertFalse(nd_accounts.same_server("http://nas.lan:4533", "http://nas.lan:4534"))
        self.assertFalse(nd_accounts.same_server("https://nas.lan", "https://attacker.example"))

    def test_two_removals_at_once_never_remove_the_last_account(self):
        import threading

        second = self.add().get_json()["created"]
        inside, release = threading.Event(), threading.Event()

        def slow(account_id):
            inside.set()
            release.wait(5)

        errors = []

        def remove(account_id):
            try:
                nd_accounts.delete(account_id)
            except nd_accounts.AccountError as e:
                errors.append(str(e))

        with mock.patch.object(nd_accounts, "_before_removal", side_effect=slow), \
                mock.patch.object(nd_accounts, "_after_removal"):
            first = threading.Thread(target=remove, args=(second,))
            first.start()
            inside.wait(5)
            remove("nd1")
            release.set()
            first.join(5)
        self.assertEqual(["The last Navidrome account cannot be removed."], errors)
        self.assertEqual(["nd1"], [a["id"] for a in nd_accounts.list_accounts()])

    def test_the_navidrome_user_is_found_in_its_database(self):
        make_navidrome(self.nav, [])
        add_navidrome_users(self.nav, [("uid-alice", "alice", True)])
        account_id = self.add().get_json()["created"]
        data = self.client.post(f"/api/navidrome/accounts/{account_id}/test").get_json()
        self.assertEqual(data["test"]["navidrome_user"], "alice")
        self.assertEqual(nd_accounts.get(account_id)["navidrome_user_id"], "uid-alice")

    def test_a_user_missing_from_the_database_is_pointed_out(self):
        make_navidrome(self.nav, [])
        add_navidrome_users(self.nav, [("uid-bob", "bob", False)])
        account_id = self.add().get_json()["created"]
        data = self.client.post(f"/api/navidrome/accounts/{account_id}/test").get_json()
        self.assertIn("not in the mounted Navidrome database", data["test"]["warning"])

    def test_errors(self):
        self.assertEqual(self.add(url="not-an-address").status_code, 400)
        self.assertEqual(self.client.post("/api/navidrome/accounts", data="x").status_code, 400)
        self.assertEqual(self.client.patch("/api/navidrome/accounts/nd9", json={"label": "x"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/navidrome/accounts/nd9").status_code, 404)
        self.assertEqual(self.client.delete("/api/navidrome/accounts/nd1").status_code, 409)
        self.assertEqual(self.client.post("/api/navidrome/accounts/nd1/test").status_code, 400)

    def test_each_browser_chooses_its_account(self):
        account_id = self.add().get_json()["created"]
        other = self.app.test_client()
        chosen = self.client.post("/api/navidrome/active", json={"id": account_id}).get_json()
        self.assertEqual(chosen["active"], account_id)
        self.assertEqual(self.client.get("/api/navidrome/accounts").get_json()["active"], account_id)
        self.assertEqual(other.get("/api/navidrome/accounts").get_json()["active"], "nd1")
        self.assertEqual(self.client.post("/api/navidrome/active", json={"id": "nd9"}).status_code, 404)

    def test_the_header_wins_for_apps_without_a_session(self):
        account_id = self.add().get_json()["created"]
        data = self.client.get("/api/navidrome/accounts", headers={"X-Navidrome-Account": account_id}).get_json()
        self.assertEqual(data["active"], account_id)
        unknown = self.client.get("/api/navidrome/accounts", headers={"X-Navidrome-Account": "nd9"}).get_json()
        self.assertEqual(unknown["active"], "nd1")

    def test_removing_the_chosen_account_falls_back(self):
        account_id = self.add().get_json()["created"]
        self.client.post("/api/navidrome/active", json={"id": account_id})
        data = self.client.delete(f"/api/navidrome/accounts/{account_id}").get_json()
        self.assertEqual(data["active"], "nd1")

    def test_the_page_shows_the_picker(self):
        self.add()
        page = self.client.get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        self.assertIn('data-nd-account', page)
        self.assertIn('Manage accounts', page)
        self.assertIn('id="navidrome-accounts"', page)
        self.assertNotIn(SECRET, page)


if __name__ == "__main__":
    unittest.main()
