"""The accounts of this app: who may do what to whom, passwords and recovery
codes, and what each account sees and may change."""
import os
import unittest
from pathlib import Path
from unittest import mock

from core import config, deezer_accounts, devices, nd_accounts, users
from core.deezer import save_playlists

PASSWORD = "long-test-password"
FILES = ("users.json", "devices.json", "navidrome_accounts.json", "deezer_accounts.json")


def clean():
    for name in FILES:
        (Path(config.DATA_DIR) / name).unlink(missing_ok=True)
    (Path(config.DATA_DIR) / users.RECOVERY_FILE).unlink(missing_ok=True)


class Base(unittest.TestCase):
    def setUp(self):
        for name in ("DISABLE_AUTH", "APP_USERNAME", "APP_PASSWORD", "API_TOKEN"):
            patcher = mock.patch.dict(os.environ, {}, clear=False)
            patcher.start()
            self.addCleanup(patcher.stop)
            os.environ.pop(name, None)
        clean()
        self.addCleanup(clean)
        save_playlists([])
        self.addCleanup(save_playlists, [])
        from core import auth

        auth.limiter._entries.clear()
        auth.user_limiter._entries.clear()
        self.root = users.create("root", PASSWORD, users.SUPERADMIN, must_change=False)
        self.admin = users.create("admin", PASSWORD, users.ADMIN, must_change=False)
        self.other_admin = users.create("admin2", PASSWORD, users.ADMIN, must_change=False)
        self.alice = users.create("alice", PASSWORD, users.STANDARD, must_change=False)
        self.bob = users.create("bob", PASSWORD, users.STANDARD, must_change=False)


class Rights(Base):
    def test_who_may_do_what(self):
        root, admin, admin2, alice = self.root, self.admin, self.other_admin, self.alice
        self.assertTrue(users.can(admin, "admin"))
        self.assertFalse(users.can(alice, "admin"))
        # Edit: the Super-Admin anyone, an Admin the Standards, everyone themselves.
        self.assertTrue(users.can(root, "edit", admin))
        self.assertTrue(users.can(admin, "edit", alice))
        self.assertFalse(users.can(admin, "edit", admin2))
        self.assertFalse(users.can(alice, "edit", self.bob))
        self.assertTrue(users.can(alice, "edit", alice))
        # Delete: never the Super-Admin, never yourself.
        self.assertFalse(users.can(root, "delete", root))
        self.assertFalse(users.can(admin, "delete", root))
        self.assertTrue(users.can(root, "delete", admin))
        self.assertFalse(users.can(admin, "delete", admin2))
        self.assertTrue(users.can(admin, "delete", alice))
        # Privileges: an Admin promotes, only the Super-Admin demotes.
        self.assertTrue(users.can(admin, "promote", alice))
        self.assertFalse(users.can(admin, "demote", admin2))
        self.assertTrue(users.can(root, "demote", admin))
        self.assertFalse(users.can(root, "demote", root))

    def test_the_super_admin_stays(self):
        with self.assertRaises(users.UserError):
            users.set_role(self.root["id"], users.STANDARD)
        with self.assertRaises(users.UserError):
            users.remove(self.root["id"])
        with self.assertRaises(users.UserError):
            users.create("another", PASSWORD, users.SUPERADMIN)

    def test_usernames_are_unique_whatever_the_case(self):
        with self.assertRaises(users.UserError):
            users.create("ALICE", PASSWORD)


class Passwords(Base):
    def test_a_recovery_code_works_once(self):
        code = users.new_recovery_code(self.alice["id"])
        new_code = users.recover("alice", code.lower(), "a-new-long-password")
        self.assertTrue(users.check("alice", "a-new-long-password"))
        with self.assertRaises(users.UserError):
            users.recover("alice", code, "yet-another-password")
        self.assertNotEqual(code, new_code)

    def test_a_wrong_code_is_refused(self):
        users.new_recovery_code(self.alice["id"])
        with self.assertRaises(users.UserError):
            users.recover("alice", "0000-0000-0000-0000", "a-new-long-password")

    def test_the_super_admin_file_is_one_time_and_short_lived(self):
        path = users.write_superadmin_code(now=1000)
        code = path.read_text(encoding="utf-8").split()[0]
        with self.assertRaises(users.UserError):
            users.recover_superadmin(code, "a-new-long-password", now=1000 + users.RECOVERY_SECONDS + 1)
        path = users.write_superadmin_code(now=2000)
        code = path.read_text(encoding="utf-8").split()[0]
        users.recover_superadmin(code, "a-new-long-password", now=2001)
        self.assertTrue(users.check("root", "a-new-long-password"))
        self.assertFalse(path.exists())

    def test_a_new_password_signs_the_devices_out(self):
        token, _ = devices.create("Pixel", "", self.alice["id"])
        self.assertTrue(devices.verify(f"Bearer {token}"))
        users.set_password(self.alice["id"], "a-new-long-password")
        self.assertIsNone(devices.verify(f"Bearer {token}"))


class Migration(unittest.TestCase):
    def setUp(self):
        clean()
        self.addCleanup(clean)
        self.addCleanup(lambda: [config.save_secret(n, "") for n in ("app_username", "app_password_hash", "api_token")])

    def test_the_old_account_becomes_the_super_admin_and_keeps_everything(self):
        from werkzeug.security import generate_password_hash

        from core import migrations

        config.save_secret("app_username", "me")
        config.save_secret("app_password_hash", generate_password_hash(PASSWORD))
        config.save_secret("api_token", "catboard-token-123")
        nd_accounts.ensure_initial()
        devices_file = Path(config.DATA_DIR) / "devices.json"
        devices_file.write_text('{"version": 1, "devices": [{"id": "d1", "name": "Pixel", "token_sha256": "x"}]}',
                                encoding="utf-8")
        self.assertTrue(migrations.app_accounts())
        root = users.check("me", PASSWORD)
        self.assertEqual(users.SUPERADMIN, root["role"])
        self.assertEqual("catboard-token-123", users.field(root, "api_token"))
        self.assertEqual(["nd1"], [a["id"] for a in nd_accounts.accounts_of(root["id"])])
        self.assertEqual(root["id"], devices._read()["devices"][0]["user"])
        self.assertFalse(migrations.app_accounts())


class Pages(Base):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        self.alice_nd = nd_accounts.create({"url": "http://nd.example", "username": "alice", "secret": "x",
                                            "owner": self.alice["id"]})["id"]
        self.bob_nd = nd_accounts.create({"url": "http://nd.example", "username": "bob", "secret": "x",
                                          "owner": self.bob["id"]})["id"]

    def sign_in(self, name):
        self.client = self.app.test_client()
        response = self.client.post("/login", data={"username": name, "password": PASSWORD})
        self.assertEqual(302, response.status_code)

    def test_a_standard_cannot_touch_the_server(self):
        self.sign_in("alice")
        for path in ("/admin/clear/all", "/cache/full/start", "/dedup/apply"):
            with self.subTest(path=path):
                self.assertEqual(403, self.client.post(path, json={"decisions": [1]}).status_code)
        self.assertEqual(403, self.client.post("/config", data={"scan_dirs": "/x"}).status_code)
        self.assertEqual(403, self.client.put("/api/v1/settings", json={}).status_code)
        self.assertEqual(403, self.client.post("/api/mixes/settings", json={"max_trial_gb": 99}).status_code)
        self.assertEqual(403, self.client.get("/api/users").status_code)

    def test_settings_show_a_standard_only_its_spaces(self):
        self.sign_in("alice")
        page = self.client.get("/config").get_data(as_text=True)
        self.assertNotIn('data-space-tab="users"', page)
        self.assertIn('class="set-fieldset" disabled', page)
        self.assertNotIn("danger-title", page)
        self.sign_in("admin")
        page = self.client.get("/config").get_data(as_text=True)
        self.assertIn('data-space-tab="users"', page)
        self.assertIn('title="Signed in as admin">Sign out', page)
        self.assertNotIn('class="set-fieldset" disabled', page)

    def test_each_one_sees_and_picks_only_their_profiles(self):
        self.sign_in("alice")
        listed = self.client.get("/api/navidrome/accounts").get_json()["accounts"]
        self.assertEqual([self.alice_nd], [a["id"] for a in listed])
        info = self.client.get("/api/v1/info", headers={"X-Navidrome-Account": self.bob_nd}).get_json()
        self.assertEqual(self.alice_nd, info["profile"])
        self.assertEqual(403, self.client.patch(f"/api/navidrome/accounts/{self.bob_nd}", json={"label": "x"}).status_code)
        self.assertEqual(404, self.client.post("/api/navidrome/active", json={"id": self.bob_nd}).status_code)

    def test_an_admin_manages_a_standards_accounts_not_another_admins(self):
        admin_nd = nd_accounts.create({"url": "http://nd.example", "username": "admin2", "secret": "x",
                                       "owner": self.other_admin["id"]})["id"]
        self.sign_in("admin")
        listed = self.client.get(f"/api/navidrome/accounts?user={self.alice['id']}").get_json()["accounts"]
        self.assertEqual([self.alice_nd], [a["id"] for a in listed])
        self.assertEqual(200, self.client.patch(f"/api/navidrome/accounts/{self.alice_nd}", json={"label": "A"}).status_code)
        self.assertEqual(403, self.client.patch(f"/api/navidrome/accounts/{admin_nd}", json={"label": "B"}).status_code)
        self.assertEqual(403, self.client.get(f"/api/navidrome/accounts?user={self.other_admin['id']}").status_code)

    def test_a_shared_deezer_account_is_used_not_changed(self):
        with mock.patch.object(deezer_accounts, "_forget"):
            dz = deezer_accounts.create({"arl": "a" * 40, "owner": self.alice["id"]}, check=False)["id"]
        deezer_accounts.set_shared(dz, [self.bob["id"]])
        self.sign_in("bob")
        listed = self.client.get("/api/deezer/accounts").get_json()["accounts"]
        self.assertEqual([(dz, False)], [(a["id"], a["mine"]) for a in listed])
        self.assertEqual(200, self.client.post(f"/api/deezer/accounts/{dz}/download").status_code)
        self.assertEqual(dz, users.field(users.get(self.bob["id"]), "download_deezer"))
        self.assertEqual(403, self.client.patch(f"/api/deezer/accounts/{dz}", json={"label": "x"}).status_code)
        self.assertEqual(403, self.client.delete(f"/api/deezer/accounts/{dz}").status_code)

    def test_catboard_reads_the_chosen_profiles_as_one_feed(self):
        from core import releases

        with mock.patch.object(deezer_accounts, "_forget"):
            first = deezer_accounts.create({"arl": "a" * 40, "owner": self.alice["id"]}, check=False)["id"]
            second = deezer_accounts.create({"arl": "b" * 40, "owner": self.alice["id"]}, check=False)["id"]
        other_nd = nd_accounts.create({"url": "http://nd.example", "username": "alice2", "secret": "x",
                                       "owner": self.alice["id"], "deezer_account": second})["id"]
        nd_accounts.update(self.alice_nd, {"deezer_account": first})
        users.set_field(self.alice["id"], "api_token", "alice-token-1234")
        feeds = {first: [{"id": "1", "release_date": "2026-11-01", "artist": "A"}],
                 second: [{"id": "1", "release_date": "2026-11-01", "artist": "A"},
                          {"id": "2", "release_date": "2026-11-02", "artist": "B"}]}
        with mock.patch.object(releases, "_files", side_effect=lambda account: (Path("none"), Path("none"))), \
                mock.patch("routes.account.load_releases",
                           side_effect=lambda account: {"releases": feeds.get(account, []), "artists": 1}):
            answer = self.app.test_client().get("/api/releases", headers={"Authorization": "Bearer alice-token-1234"})
            self.assertEqual(["2", "1"], [r["id"] for r in answer.get_json()["releases"]])
            users.set_field(self.alice["id"], "catboard_profiles", [self.alice_nd])
            answer = self.app.test_client().get("/api/releases", headers={"Authorization": "Bearer alice-token-1234"})
            self.assertEqual(["1"], [r["id"] for r in answer.get_json()["releases"]])
        self.assertTrue(other_nd)

    def test_clears_of_your_profiles_leave_the_others(self):
        save_playlists([{"id": "111", "title": "Mine", "picture": "", "accounts": [self.alice_nd]},
                        {"id": "222", "title": "Bob's", "picture": "", "accounts": [self.bob_nd]}])
        config.update_preview_state("111", {"rows": []})
        config.update_preview_state("222", {"rows": []})
        self.sign_in("alice")
        self.assertEqual(1, self.client.post("/api/profiles/clear/matches").get_json()["cleared"])
        self.assertIsNone(config.get_preview_state("111"))
        self.assertIsNotNone(config.get_preview_state("222"))

    def test_a_new_account_chooses_its_password_first(self):
        self.sign_in("admin")
        created = self.client.post("/api/users", json={"username": "carol", "password": "temporary-pass"}).get_json()
        self.assertEqual("standard", next(u for u in created["users"] if u["username"] == "carol")["role"])
        self.client = self.app.test_client()
        self.client.post("/login", data={"username": "carol", "password": "temporary-pass"})
        self.assertEqual(302, self.client.get("/api/navidrome/accounts").status_code)
        page = self.client.post("/first-password", data={"password": "carols-own-password",
                                                          "confirm": "carols-own-password"})
        self.assertIn("recovery code", page.get_data(as_text=True).lower())
        self.assertEqual(200, self.client.get("/api/navidrome/accounts").status_code)

    def test_deleting_an_account_hands_its_accounts_over_or_removes_them(self):
        self.sign_in("admin")
        self.assertEqual(200, self.client.delete(f"/api/users/{self.alice['id']}",
                                                 json={"heir": self.bob["id"]}).status_code)
        self.assertEqual({self.alice_nd, self.bob_nd}, {a["id"] for a in nd_accounts.accounts_of(self.bob["id"])})
        self.assertIsNone(users.get(self.alice["id"]))
        self.assertEqual(403, self.client.delete(f"/api/users/{self.root['id']}").status_code)

    def test_the_forgot_page_takes_a_recovery_code(self):
        code = users.new_recovery_code(self.bob["id"])
        page = self.app.test_client().post("/forgot", data={"username": "bob", "code": code,
                                                            "password": "bobs-new-password"})
        self.assertEqual(200, page.status_code)
        self.assertTrue(users.check("bob", "bobs-new-password"))


if __name__ == "__main__":
    unittest.main()
