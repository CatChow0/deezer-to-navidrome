import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, crypto, deezer_account, deezer_accounts, deezer_dl, migrations, releases

ARL = "ARL-SENTINEL-premium-111"


def fake_login(self, arl):
    """A Deezer that knows three ARLs: premium, free, and an expired one."""
    arl = (arl or "").strip()
    users = {"ARL-SENTINEL-premium-111": ("101", "Anthony", "FR", {"lossless": True}),
             "ARL-free-222": ("202", "Bob", "BE", {}),
             "ARL-other-premium-333": ("303", "Carol", "US", {"high": True})}
    if arl not in users:
        raise deezer_account.DeezerAccountError("Deezer did not accept this ARL. It may have expired.")
    user_id, name, country, quality = users[arl]
    self.arl, self.http, self.token = arl, object(), "token"
    self.user, self.country, self.quality = {"id": user_id, "name": name}, country, quality


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        patches = [mock.patch.object(config, "DATA_DIR", self.data),
                   mock.patch.object(config, "SECRETS_FILE", self.data / "secrets.json"),
                   mock.patch.object(deezer_account.DeezerSession, "login", fake_login),
                   mock.patch.object(releases, "DATA_DIR", self.data),
                   mock.patch.object(releases, "RELEASES_FILE", self.data / "releases.json"),
                   mock.patch.object(releases, "PREFS_FILE", self.data / "release_prefs.json"),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        for name in (crypto.KEY_ENV, deezer_accounts.ENV_MAIN, deezer_accounts.ENV_DOWNLOAD):
            os.environ.pop(name, None)
        deezer_account.forget_session()
        deezer_dl.forget_sessions()

    def raw(self):
        return (self.data / "deezer_accounts.json").read_text(encoding="utf-8")


class Accounts(Base):
    def test_added_after_signing_in_and_kept_encrypted(self):
        account = deezer_accounts.create({"label": "Me", "arl": ARL})
        self.assertEqual((account["id"], account["name"], account["country"], account["premium"]), ("dz1", "Anthony", "FR", True))
        self.assertEqual(account["format"], "FLAC")
        self.assertNotIn(ARL, self.raw())
        self.assertEqual(deezer_accounts.arl("dz1"), ARL)
        view = deezer_accounts.public(account)
        self.assertNotIn("arl", view)
        self.assertNotIn(ARL, json.dumps(view))
        self.assertTrue(view["is_default"] and view["is_download"])

    def test_an_expired_arl_is_refused(self):
        with self.assertRaises(deezer_accounts.DeezerAccountsError) as caught:
            deezer_accounts.create({"arl": "ARL-expired"})
        self.assertIn("expired", str(caught.exception))
        self.assertEqual(deezer_accounts.list_accounts(), [])

    def test_one_deezer_user_one_account(self):
        deezer_accounts.create({"arl": ARL})
        with self.assertRaises(deezer_accounts.DeezerAccountsError):
            deezer_accounts.create({"arl": ARL})

    def test_the_label_defaults_to_the_deezer_name(self):
        self.assertEqual(deezer_accounts.create({"label": " ", "arl": "ARL-free-222"})["label"], "Bob")

    def test_default_and_download_roles(self):
        deezer_accounts.create({"arl": "ARL-free-222"})
        deezer_accounts.create({"arl": ARL})
        self.assertEqual((deezer_accounts.default_id(), deezer_accounts.download_id()), ("dz1", "dz1"))
        deezer_accounts.set_download("dz2")
        self.assertEqual(deezer_accounts.download_id(), "dz2")
        self.assertEqual(deezer_dl.download_arl(), ARL)
        deezer_accounts.set_default("dz2")
        deezer_accounts.delete("dz2")
        self.assertEqual((deezer_accounts.default_id(), deezer_accounts.download_id()), ("dz1", "dz1"))

    def test_the_last_account_stays(self):
        deezer_accounts.create({"arl": ARL})
        with self.assertRaises(deezer_accounts.DeezerAccountsError):
            deezer_accounts.delete("dz1")

    def test_a_new_arl_is_checked_and_an_empty_one_kept(self):
        deezer_accounts.create({"arl": "ARL-free-222"})
        deezer_accounts.update("dz1", {"label": "Renamed", "arl": ""})
        self.assertEqual(deezer_accounts.arl("dz1"), "ARL-free-222")
        with self.assertRaises(deezer_accounts.DeezerAccountsError):
            deezer_accounts.update("dz1", {"arl": "ARL-expired"})
        account = deezer_accounts.update("dz1", {"arl": "ARL-other-premium-333"})
        self.assertEqual((account["name"], account["label"], account["premium"]), ("Carol", "Renamed", True))

    def test_a_failed_check_keeps_who_the_account_is(self):
        deezer_accounts.create({"arl": ARL})
        with mock.patch.object(deezer_account, "account_status",
                               return_value={"connected": False, "error": "Could not reach Deezer: timeout"}):
            deezer_accounts.check("dz1")
        account = deezer_accounts.get("dz1")
        self.assertEqual((account["name"], account["user_id"], account["premium"]), ("Anthony", "101", True))
        self.assertIn("timeout", account["error"])
        with self.assertRaises(deezer_accounts.DeezerAccountsError):
            deezer_accounts.create({"arl": ARL})
        deezer_accounts.check("dz1")
        self.assertEqual(deezer_accounts.get("dz1")["error"], "")

    def test_removed_its_feed_goes_and_its_profiles_read_the_default_one(self):
        from core import account_context, nd_accounts

        deezer_accounts.create({"arl": ARL})
        deezer_accounts.create({"arl": "ARL-free-222"})
        with mock.patch.object(nd_accounts, "_path", return_value=self.data / "navidrome_accounts.json"):
            nd_accounts.ensure_initial()
            nd_accounts.update("nd1", {"deezer_account": "dz2"})
            self.assertEqual(account_context.deezer_account_of("nd1"), "dz2")
            (self.data / "releases-dz2.json").write_text("{}", encoding="utf-8")
            (self.data / "release_prefs-dz2.json").write_text("{}", encoding="utf-8")
            deezer_accounts.delete("dz2")
            self.assertEqual(nd_accounts.get("nd1")["deezer_account"], "")
            self.assertEqual(account_context.deezer_account_of("nd1"), "dz1")
        self.assertFalse((self.data / "releases-dz2.json").exists())
        self.assertFalse((self.data / "release_prefs-dz2.json").exists())
        with self.assertRaises(deezer_account.DeezerAccountError) as caught:
            deezer_account.mix_tracks("flow", "chill", account="dz2")
        self.assertIn("removed", str(caught.exception))

    def test_each_account_its_own_session(self):
        deezer_accounts.create({"arl": ARL})
        deezer_accounts.create({"arl": "ARL-free-222"})
        self.assertEqual(deezer_account.account_status("dz1")["name"], "Anthony")
        self.assertEqual(deezer_account.account_status("dz2")["name"], "Bob")
        self.assertEqual(deezer_account.account_status()["name"], "Anthony")
        self.assertIsNot(deezer_account._session_for("dz1"), deezer_account._session_for("dz2"))

    def test_no_account_means_no_downloads(self):
        self.assertEqual(deezer_dl.download_arl(), "")
        self.assertFalse(deezer_account.account_status()["connected"])


class FromAnOlderInstall(Base):
    def test_the_single_account_and_the_premium_one_become_two_accounts(self):
        config.save_secret("deezer_arl", "ARL-free-222")
        config.save_secret("deezer_arl_premium", ARL)
        config.save_secret("api_token", "TOKEN-9999")
        self.assertEqual(migrations.deezer_accounts_from_secrets(), 2)
        self.assertEqual(migrations.deezer_accounts_from_secrets(), 0)
        self.assertEqual((deezer_accounts.default_id(), deezer_accounts.download_id()), ("dz1", "dz2"))
        self.assertEqual((deezer_accounts.arl("dz1"), deezer_accounts.arl("dz2")), ("ARL-free-222", ARL))
        stored = json.loads(config.SECRETS_FILE.read_text())
        self.assertNotIn("deezer_arl", stored)
        self.assertNotIn("deezer_arl_premium", stored)
        self.assertEqual(config.load_secret("api_token"), "TOKEN-9999")
        backup = self.data / "backups" / migrations.BACKUP_FOLDER / "secrets.json"
        self.assertTrue(backup.exists())

    def test_the_environment_still_wins_and_is_never_saved(self):
        config.save_secret("deezer_arl", "ARL-free-222")
        with mock.patch.dict(os.environ, {deezer_accounts.ENV_MAIN: ARL}):
            migrations.deezer_accounts_from_secrets()
            self.assertEqual([a["env"] for a in deezer_accounts.list_accounts()], [deezer_accounts.ENV_MAIN])
            self.assertEqual(deezer_accounts.arl("dz1"), ARL)
            self.assertNotIn(ARL, self.raw())
            self.assertEqual(deezer_accounts.public(deezer_accounts.get("dz1"))["from_env"], deezer_accounts.ENV_MAIN)
            with self.assertRaises(deezer_accounts.DeezerAccountsError):
                deezer_accounts.update("dz1", {"arl": "ARL-free-222"})

    def test_a_variable_set_later_adds_its_account(self):
        deezer_accounts.create({"arl": "ARL-free-222"})
        migrations.deezer_accounts_from_secrets()
        with mock.patch.dict(os.environ, {deezer_accounts.ENV_DOWNLOAD: ARL}):
            migrations.deezer_accounts_from_secrets()
            self.assertEqual(deezer_accounts.download_id(), "dz2")
            self.assertEqual(deezer_dl.download_arl(), ARL)

    def test_the_same_arl_twice_stays_one_account(self):
        config.save_secret("deezer_arl", ARL)
        config.save_secret("deezer_arl_premium", ARL)
        self.assertEqual(migrations.deezer_accounts_from_secrets(), 1)
        self.assertEqual((deezer_accounts.default_id(), deezer_accounts.download_id()), ("dz1", "dz1"))

    def test_nothing_to_move(self):
        self.assertEqual(migrations.deezer_accounts_from_secrets(), 0)
        self.assertEqual(deezer_accounts.list_accounts(), [])


class Releases(Base):
    def test_each_account_its_own_feed_and_muted_artists(self):
        deezer_accounts.create({"arl": ARL})
        deezer_accounts.create({"arl": "ARL-free-222"})
        artists = {"dz1": [{"id": "1", "name": "Vald", "picture": ""}], "dz2": [{"id": "2", "name": "Oklou", "picture": ""}]}
        with mock.patch("core.releases.favorite_artists", side_effect=lambda account: artists[account]), \
                mock.patch("core.releases._artist_releases", return_value=[]), \
                mock.patch("core.releases.time.sleep"):
            releases.refresh_releases(account="dz1")
            releases.refresh_releases(account="dz2")
        self.assertEqual([a["name"] for a in releases.load_releases("dz1")["followed_artists"]], ["Vald"])
        self.assertEqual([a["name"] for a in releases.load_releases("dz2")["followed_artists"]], ["Oklou"])
        self.assertTrue((self.data / "releases.json").exists())
        self.assertTrue((self.data / "releases-dz2.json").exists())
        releases.set_muted("2", "Oklou", True, account="dz2")
        self.assertEqual(releases.load_prefs("dz2")["muted"], {"2": "Oklou"})
        self.assertEqual(releases.load_prefs("dz1")["muted"], {})
        self.assertIsNot(releases.lock_for("dz1"), releases.lock_for("dz2"))


class Mixes(unittest.TestCase):
    def test_the_first_account_keeps_its_ids_the_others_carry_theirs(self):
        from core.deezer import mix_deezer_account, mix_id, parse_mix_id, playlist_kind

        self.assertEqual(mix_id("flow", "Chill"), "mix-flow-chill")
        self.assertEqual(mix_id("flow", "chill", "dz1"), "mix-flow-chill")
        self.assertEqual(mix_id("flow", "chill", "dz2"), "mix-dz2-flow-chill")
        self.assertEqual(parse_mix_id("mix-dz2-flow-chill"), ("flow", "chill"))
        self.assertEqual(mix_deezer_account("mix-dz2-flow-chill"), "dz2")
        self.assertEqual(mix_deezer_account("mix-stl-inspired-by-1"), "dz1")
        self.assertEqual(playlist_kind("mix-dz12-stl-x"), "mix")
        self.assertIsNone(parse_mix_id("mix-dz0-flow-x"))

    def test_a_scan_reads_the_mix_with_its_account(self):
        from core import deezer

        with mock.patch("core.deezer_account.mix_tracks", return_value=[]) as tracks, \
                mock.patch("core.deezer.playlist_title", return_value="Flow"):
            deezer.fetch_deezer_playlist_tracks("mix-dz2-flow-chill")
        tracks.assert_called_once_with("flow", "chill", account="dz2")


if __name__ == "__main__":
    unittest.main()
