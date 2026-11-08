import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, crypto, navidrome_db, nd_accounts
from tests.fixtures import add_navidrome_users, make_navidrome

SECRET = "pw-SENTINEL-9001"


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        self.nav = self.data / "navidrome.db"
        patches = [mock.patch.object(config, "DATA_DIR", self.data),
                   mock.patch.object(config, "SECRETS_FILE", self.data / "secrets.json"),
                   mock.patch.dict(os.environ, {"STATS_NAVIDROME_DB": str(self.nav)})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop(crypto.KEY_ENV, None)
        navidrome_db.forget()
        self.addCleanup(navidrome_db.forget)

    def make(self, **fields):
        values = {"label": "Alice", "url": "http://navidrome:4533", "username": "alice", "secret": SECRET, **fields}
        return nd_accounts.create(values)

    def raw(self):
        return (self.data / "navidrome_accounts.json").read_text(encoding="utf-8")


class Creating(Base):
    def test_a_new_account_publishes_through_the_api_and_its_secret_is_encrypted(self):
        account = self.make()
        self.assertEqual(account["id"], "nd1")
        self.assertEqual(account["publish_mode"], "api")
        self.assertNotIn(SECRET, self.raw())
        self.assertEqual(nd_accounts.credentials("nd1")["secret"], SECRET)

    def test_ids_are_never_reused(self):
        self.make()
        second = self.make(username="bob")
        nd_accounts.delete(second["id"])
        self.assertEqual(self.make(username="carol")["id"], "nd3")

    def test_the_first_one_is_the_default(self):
        self.make()
        self.make(username="bob")
        self.assertEqual(nd_accounts.default_id(), "nd1")
        nd_accounts.set_default("nd2")
        self.assertEqual(nd_accounts.default_id(), "nd2")

    def test_public_view_never_has_the_secret(self):
        account = self.make()
        view = nd_accounts.public(account)
        self.assertNotIn("secret", view)
        self.assertTrue(view["has_secret"])
        self.assertNotIn(SECRET, json.dumps(view))
        self.assertTrue(view["complete"])

    def test_one_navidrome_user_one_account(self):
        self.make()
        with self.assertRaises(nd_accounts.AccountError):
            self.make(label="Alice again", username="ALICE")

    def test_what_is_required(self):
        for fields in ({"url": ""}, {"username": ""}, {"secret": ""}, {"auth_type": "cookie"}):
            with self.assertRaises(nd_accounts.AccountError, msg=fields):
                self.make(**fields)

    def test_addresses_are_cleaned_and_checked(self):
        clean = nd_accounts.clean_url
        self.assertEqual(clean(" http://nd:4533/ "), "http://nd:4533")
        self.assertEqual(clean("https://music.example.org/navidrome/rest/"), "https://music.example.org/navidrome")
        for bad in ("navidrome:4533", "ftp://nd", "http://user:pw@nd", "http://nd/?x=1", "http://"):
            with self.assertRaises(nd_accounts.AccountError, msg=bad):
                clean(bad)

    def test_label_defaults_to_the_user_and_is_bounded(self):
        self.assertEqual(self.make(label="  ")["label"], "alice")
        with self.assertRaises(nd_accounts.AccountError):
            self.make(username="bob", label="x" * 41)


class Changing(Base):
    def test_an_empty_secret_keeps_the_saved_one(self):
        self.make()
        nd_accounts.update("nd1", {"label": "Al", "secret": ""})
        self.assertEqual(nd_accounts.credentials("nd1")["secret"], SECRET)
        self.assertEqual(nd_accounts.get("nd1")["label"], "Al")

    def test_another_user_forgets_what_was_learnt(self):
        self.make()
        nd_accounts.record_test("nd1", {"ok": True}, {"id": "u1", "user_name": "alice"})
        self.assertEqual(nd_accounts.get("nd1")["navidrome_user_id"], "u1")
        nd_accounts.update("nd1", {"username": "bob"})
        account = nd_accounts.get("nd1")
        self.assertEqual(account["navidrome_user_id"], "")
        self.assertIsNone(account["last_test"])

    def test_switching_to_an_api_key_needs_the_key(self):
        self.make()
        with self.assertRaises(nd_accounts.AccountError):
            nd_accounts.update("nd1", {"auth_type": "apikey"})
        nd_accounts.update("nd1", {"auth_type": "apikey", "secret": "KEY-1"})
        self.assertEqual(nd_accounts.credentials("nd1"), {"url": "http://navidrome:4533", "username": "alice",
                                                          "auth_type": "apikey", "secret": "KEY-1"})

    def test_the_last_account_stays(self):
        self.make()
        with self.assertRaises(nd_accounts.AccountError):
            nd_accounts.delete("nd1")

    def test_removing_the_default_picks_another(self):
        self.make()
        self.make(username="bob")
        nd_accounts.delete("nd1")
        self.assertEqual(nd_accounts.default_id(), "nd2")

    def test_unknown_account(self):
        for action in (lambda: nd_accounts.update("nd9", {}), lambda: nd_accounts.delete("nd9"),
                       lambda: nd_accounts.set_default("nd9"), lambda: nd_accounts.credentials("nd9")):
            with self.assertRaises(nd_accounts.AccountError):
                action()

    def test_the_test_result_is_kept_without_secrets(self):
        self.make()
        nd_accounts.record_test("nd1", {"ok": False, "error": "Wrong user name or password.", "junk": SECRET})
        self.assertEqual(nd_accounts.public(nd_accounts.get("nd1"))["last_test"]["error"], "Wrong user name or password.")
        self.assertNotIn(SECRET, self.raw())


class FirstAccount(Base):
    """An install from before 1.16: one account is made from it, at start-up."""

    def test_made_once_and_keeps_the_m3u8_files(self):
        made = nd_accounts.ensure_initial()
        self.assertEqual(made["id"], "nd1")
        self.assertEqual(made["publish_mode"], "m3u8")
        self.assertTrue(made["legacy"])
        self.assertIsNone(nd_accounts.ensure_initial())
        self.assertEqual(len(nd_accounts.list_accounts()), 1)
        self.assertFalse(nd_accounts.public(nd_accounts.get("nd1"))["complete"])

    def test_the_only_navidrome_user_is_recognised(self):
        make_navidrome(self.nav, [])
        add_navidrome_users(self.nav, [("uid-1", "anthony", True)])
        made = nd_accounts.ensure_initial()
        self.assertEqual((made["username"], made["navidrome_user_id"]), ("anthony", "uid-1"))

    def test_several_users_are_left_for_you_to_choose(self):
        make_navidrome(self.nav, [])
        add_navidrome_users(self.nav, [("u1", "alice", True), ("u2", "bob", False)])
        made = nd_accounts.ensure_initial()
        self.assertEqual((made["username"], made["navidrome_user_id"]), ("", ""))

    def test_the_next_account_is_nd2(self):
        nd_accounts.ensure_initial()
        self.assertEqual(self.make()["id"], "nd2")
        self.assertEqual(nd_accounts.default_id(), "nd1")

    def test_a_damaged_file_is_not_overwritten(self):
        (self.data / "navidrome_accounts.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(nd_accounts.AccountError):
            nd_accounts.ensure_initial()
        self.assertEqual(self.raw(), "{not json")


class NavidromeUsers(Base):
    def test_users_from_a_copy_and_found_whatever_the_case(self):
        make_navidrome(self.nav, [])
        add_navidrome_users(self.nav, [("u1", "Alice", True), ("u2", "bob", False)])
        self.assertEqual([u["user_name"] for u in navidrome_db.users()], ["Alice", "bob"])
        self.assertEqual(navidrome_db.find_user("alice")["id"], "u1")
        self.assertIsNone(navidrome_db.find_user("carol"))

    def test_not_mounted(self):
        self.assertIsNone(navidrome_db.users())
        self.assertFalse(navidrome_db.mounted())


class Migrations(Base):
    def test_start_up_encrypts_old_secrets_and_makes_nd1(self):
        from core import migrations

        config.SECRETS_FILE.write_text(json.dumps({"deezer_arl": "PLAIN-ARL-SENTINEL"}), encoding="utf-8")
        migrations.run()
        migrations.run()
        self.assertNotIn("PLAIN-ARL-SENTINEL", config.SECRETS_FILE.read_text())
        self.assertEqual(config.load_secret("deezer_arl"), "PLAIN-ARL-SENTINEL")
        self.assertEqual([a["id"] for a in nd_accounts.list_accounts()], ["nd1"])


if __name__ == "__main__":
    unittest.main()
