import io
import json
import logging
import os
import unittest
from pathlib import Path
from unittest import mock

from core import config, deezer_account, deezer_accounts, deezer_dl, nd_accounts, releases
from core.deezer_account import DeezerAccountError
from core.deezer import load_playlists, save_playlists
from tests.test_deezer_accounts import ARL, fake_login


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        data = Path(config.DATA_DIR)
        for name in ("navidrome_accounts.json", "deezer_accounts.json", "releases.json", "release_prefs.json",
                     "releases-dz2.json", "release_prefs-dz2.json"):
            (data / name).unlink(missing_ok=True)
        save_playlists([])
        patches = [mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}),
                   mock.patch.object(deezer_account.DeezerSession, "login", fake_login),
                   mock.patch("core.deezer.cache_cover", return_value=None)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        for name in (deezer_accounts.ENV_MAIN, deezer_accounts.ENV_DOWNLOAD):
            os.environ.pop(name, None)
        deezer_account.forget_session()
        deezer_dl.forget_sessions()
        nd_accounts.ensure_initial()
        self.client = self.app.test_client()
        self.log = io.StringIO()
        handler = logging.StreamHandler(self.log)
        root = logging.getLogger()
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)

    def add(self, arl, label=""):
        return self.client.post("/api/deezer/accounts", json={"label": label, "arl": arl})

    def assert_no_arl(self, *responses):
        for response in responses:
            self.assertNotIn(ARL, response.get_data(as_text=True))
        self.assertNotIn(ARL, self.log.getvalue())
        self.assertNotIn(ARL, (Path(config.DATA_DIR) / "deezer_accounts.json").read_text(encoding="utf-8"))

    def test_add_edit_roles_check_and_remove_without_leaking_the_arl(self):
        first = self.add(ARL, "Mine")
        self.assertEqual(first.status_code, 200, first.get_json())
        second = self.add("ARL-free-222")
        listed = self.client.get("/api/deezer/accounts")
        state = listed.get_json()
        self.assertEqual([a["id"] for a in state["accounts"]], ["dz1", "dz2"])
        self.assertEqual((state["default"], state["download"]), ("dz1", "dz1"))
        self.assertEqual(state["downloads"]["format"], "FLAC")
        download = self.client.post("/api/deezer/accounts/dz2/download")
        self.assertEqual(download.get_json()["downloads"]["format"], "MP3_128")
        default = self.client.post("/api/deezer/accounts/dz2/default")
        edited = self.client.patch("/api/deezer/accounts/dz1", json={"label": "Renamed"})
        checked = self.client.post("/api/deezer/accounts/dz1/check")
        removed = self.client.delete("/api/deezer/accounts/dz1")
        self.assertEqual([a["id"] for a in removed.get_json()["accounts"]], ["dz2"])
        self.assert_no_arl(first, second, listed, download, default, edited, checked, removed)

    def test_accounts_moved_from_an_older_install_are_checked_once_listed(self):
        from core import config as cfg, migrations

        cfg.save_secret("deezer_arl_premium", ARL)
        migrations.deezer_accounts_from_secrets()
        self.assertFalse(deezer_accounts.get("dz1").get("checked_at"))
        account = self.client.get("/api/deezer/accounts").get_json()["accounts"][0]
        self.assertEqual((account["name"], account["premium"]), ("Anthony", True))
        self.assertGreater(account["checked_at"], 0)

    def test_errors(self):
        self.assertEqual(self.add("ARL-expired").status_code, 400)
        self.assertEqual(self.add("").status_code, 400)
        self.add(ARL)
        self.assertEqual(self.client.delete("/api/deezer/accounts/dz1").status_code, 409)
        self.assertEqual(self.client.delete("/api/deezer/accounts/dz9").status_code, 404)
        self.assertEqual(self.client.patch("/api/deezer/accounts/dz9", json={"label": "x"}).status_code, 404)
        self.assertEqual(self.client.post("/api/deezer/accounts/dz9/default").status_code, 404)

    def profile_with(self, deezer_account_id):
        response = self.client.patch("/api/navidrome/accounts/nd1", json={"deezer_account": deezer_account_id})
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_a_profile_reads_its_deezer_account_or_the_default_one(self):
        self.add(ARL)
        self.add("ARL-free-222")
        self.assertEqual(self.client.get("/api/deezer/account").get_json()["name"], "Anthony")
        self.profile_with("dz2")
        self.assertEqual(self.client.get("/api/deezer/account").get_json()["name"], "Bob")
        self.assertEqual(self.client.patch("/api/navidrome/accounts/nd1", json={"deezer_account": "dz9"}).status_code, 400)
        self.profile_with("")
        self.assertEqual(self.client.get("/api/deezer/account").get_json()["name"], "Anthony")
        public = next(a for a in self.client.get("/api/navidrome/accounts").get_json()["accounts"] if a["id"] == "nd1")
        self.assertEqual(public["deezer_account"], "")

    def test_releases_follow_the_profile(self):
        self.add(ARL)
        self.add("ARL-free-222")
        (Path(config.DATA_DIR) / "releases.json").write_text(json.dumps({"releases": [{"id": "a1"}]}), encoding="utf-8")
        (Path(config.DATA_DIR) / "releases-dz2.json").write_text(json.dumps({"releases": [{"id": "b2"}]}), encoding="utf-8")
        data = self.client.get("/api/releases").get_json()
        self.assertEqual(([r["id"] for r in data["releases"]], data["deezer_account"]["id"]), (["a1"], "dz1"))
        self.profile_with("dz2")
        data = self.client.get("/api/releases").get_json()
        self.assertEqual(([r["id"] for r in data["releases"]], data["deezer_account"]["id"]), (["b2"], "dz2"))
        self.client.post("/api/releases/mute", json={"artist_id": "7", "name": "X", "muted": True})
        self.assertEqual(releases.load_prefs("dz2")["muted"], {"7": "X"})
        self.assertEqual(releases.load_prefs("dz1")["muted"], {})

    def test_refresh_runs_for_the_profile_account(self):
        self.add(ARL)
        self.add("ARL-free-222")
        self.profile_with("dz2")
        with mock.patch("routes.account.start_release_refresh", return_value="t1") as start:
            self.assertEqual(self.client.post("/api/releases/refresh").get_json()["task_id"], "t1")
        self.assertEqual(start.call_args.kwargs["account"], "dz2")

    def test_no_deezer_account(self):
        data = self.client.get("/api/releases").get_json()
        self.assertFalse(data["connected"])
        self.assertEqual(self.client.post("/api/releases/refresh").status_code, 400)
        self.assertFalse(self.client.get("/api/deezer/account").get_json()["connected"])

    def test_mixes_come_from_the_profile_account_and_carry_it(self):
        self.add(ARL)
        self.add("ARL-free-222")
        self.profile_with("dz2")
        found = {"mixes": [{"kind": "flow", "source_id": "chill", "title": "Chill", "subtitle": "", "group": "Flow"}],
                 "playlists": []}
        yours = [{"id": "123", "title": "Road trip", "subtitle": "", "picture": "", "tracks": 58, "group": "Created by you"}]
        with mock.patch("routes.account.available_mixes", return_value=found) as listed, \
                mock.patch("routes.account.account_playlists", return_value=yours) as own:
            data = self.client.get("/api/deezer/mixes").get_json()
        listed.assert_called_once_with("dz2")
        own.assert_called_once_with("dz2")
        self.assertEqual(data["mixes"][0]["id"], "mix-dz2-flow-chill")
        self.assertEqual([("123", False)], [(p["id"], p["followed"]) for p in data["yours"]])
        # The profile page cannot be read: the mixes still show, and say why.
        with mock.patch("routes.account.available_mixes", return_value=found), \
                mock.patch("routes.account.account_playlists", side_effect=DeezerAccountError("no list")):
            data = self.client.get("/api/deezer/mixes").get_json()
        self.assertEqual(([], "no list"), (data["yours"], data["yours_error"]))
        self.assertEqual(1, len(data["mixes"]))
        with mock.patch("core.deezer_account.mix_tracks", return_value=[]) as tracks:
            response = self.client.post("/api/deezer/mixes/follow", json={"kind": "flow", "source_id": "chill", "title": "Chill"})
        self.assertEqual(response.get_json()["id"], "mix-dz2-flow-chill")
        tracks.assert_called_once_with("flow", "chill", account="dz2")
        self.assertEqual([p["id"] for p in load_playlists()], ["mix-dz2-flow-chill"])

    def test_stale_feeds_of_the_accounts_in_use(self):
        from routes.account import accounts_with_stale_feeds

        self.add(ARL)
        self.add("ARL-free-222")
        self.add("ARL-other-premium-333")
        self.profile_with("dz2")
        self.assertEqual(sorted(accounts_with_stale_feeds()), ["dz1", "dz2"])


if __name__ == "__main__":
    unittest.main()
