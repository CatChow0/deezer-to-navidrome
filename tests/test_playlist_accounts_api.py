import os
import unittest
from pathlib import Path
from unittest import mock

from core import config, mixes_db, navidrome_db, nd_accounts, publish
from core.deezer import accounts_for, load_playlists, save_playlists
from tests.fake_subsonic import FakeSubsonic


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        Path(config.DATA_DIR, "navidrome_accounts.json").unlink(missing_ok=True)
        save_playlists([])
        config.save_preview_state({})
        conn = mixes_db.connect()
        conn.execute("DELETE FROM publications")
        conn.commit()
        conn.close()
        patches = [mock.patch.dict(os.environ, {"DISABLE_AUTH": "true",
                                                "STATS_NAVIDROME_DB": str(Path(config.DATA_DIR) / "absent.db")}),
                   mock.patch("routes.playlists.fetch_deezer_playlist_info",
                              side_effect=lambda pid, profiles=None: {"id": pid, "title": f"Deezer {pid}", "picture": ""}),
                   mock.patch("core.deezer.cache_cover", return_value=None)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        navidrome_db.forget_songs()
        self.server = FakeSubsonic().start()
        self.addCleanup(self.server.stop)
        self.server.add_user("alice", "alice-pass")
        nd_accounts.ensure_initial()
        self.alice = nd_accounts.create({"label": "Alice", "url": self.server.url, "username": "alice",
                                         "secret": "alice-pass"})["id"]
        self.client = self.app.test_client()

    def use(self, account_id, client=None):
        (client or self.client).post("/api/navidrome/active", json={"id": account_id})

    def add(self, value, client=None):
        return (client or self.client).post("/playlist/add", data={"playlist_input": value})

    def dashboard_ids(self, client=None):
        page = (client or self.client).get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        return {p["id"] for p in load_playlists() if f'data-playlist-id="{p["id"]}"' in page}

    def test_a_new_playlist_goes_to_the_account_of_this_browser(self):
        self.use(self.alice)
        self.add("https://www.deezer.com/playlist/9001")
        self.assertEqual(accounts_for("9001"), [self.alice])
        other = self.app.test_client()
        self.assertEqual(self.dashboard_ids(), {"9001"})
        self.assertEqual(self.dashboard_ids(other), set())

    def test_a_new_playlist_is_read_with_this_browsers_profile(self):
        # Its Deezer account may own the playlist and keep it private.
        self.use(self.alice)
        with mock.patch("routes.playlists.fetch_deezer_playlist_info",
                        side_effect=lambda pid, profiles=None: {"id": pid, "title": "Mine", "picture": ""}) as fetch:
            self.add("9003")
        self.assertEqual([self.alice], fetch.call_args.kwargs["profiles"])

    def test_adding_a_saved_playlist_shares_it(self):
        self.add("9002")
        self.use(self.alice)
        response = self.add("9002")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(accounts_for("9002"), ["nd1", self.alice])
        self.assertEqual(self.dashboard_ids(), {"9002"})

    def test_delete_takes_it_from_this_account_only_while_others_have_it(self):
        save_playlists([{"id": "9003", "title": "Both", "picture": "", "accounts": ["nd1", self.alice]}])
        self.use(self.alice)
        self.client.post("/playlist/9003/delete")
        self.assertEqual(accounts_for("9003"), ["nd1"])
        self.assertEqual({p["id"] for p in load_playlists()}, {"9003"})
        self.use("nd1")
        self.client.post("/playlist/9003/delete")
        self.assertEqual(load_playlists(), [])

    def test_choosing_the_accounts_publishes_and_unpublishes(self):
        save_playlists([{"id": "9004", "title": "Picked", "picture": "", "accounts": ["nd1"]}])
        config.update_preview_state("9004", {"playlist_title": "Picked", "rows": []})
        data = self.client.post("/playlist/9004/accounts", json={"accounts": ["nd1", self.alice]}).get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(publish.flush(30))
        self.assertEqual([p["name"] for p in self.server.playlists.values()], ["Picked"])
        self.client.post("/playlist/9004/accounts", json={"accounts": ["nd1"]})
        self.assertEqual(self.server.playlists, {})
        self.assertEqual(self.client.post("/playlist/9004/accounts", json={"accounts": []}).status_code, 400)
        self.assertEqual(self.client.post("/playlist/9004/accounts", json={"accounts": ["nd9"]}).status_code, 400)
        self.assertEqual(self.client.post("/playlist/0000/accounts", json={"accounts": ["nd1"]}).status_code, 404)

    def test_the_drawer_shows_where_the_playlist_is(self):
        save_playlists([{"id": "9005", "title": "Seen", "picture": "", "accounts": [self.alice]}])
        config.update_preview_state("9005", {"playlist_title": "Seen", "rows": []})
        self.client.post("/playlist/9005/publish")
        self.assertTrue(publish.flush(30))
        data = self.client.get("/playlist/9005/navidrome").get_json()["navidrome"]
        alice = next(a for a in data["accounts"] if a["id"] == self.alice)
        nd1 = next(a for a in data["accounts"] if a["id"] == "nd1")
        self.assertTrue(alice["member"])
        self.assertTrue(alice["publication"]["in_navidrome"])
        self.assertFalse(nd1["member"])
        with mock.patch("routes.playlists.build_playlist_preview", return_value={"rows": []}):
            preview = self.client.get("/playlist/9005/preview").get_json()
        self.assertIn("navidrome", preview)

    def test_publish_now_needs_a_scan(self):
        save_playlists([{"id": "9006", "title": "Not scanned", "picture": "", "accounts": [self.alice]}])
        self.assertEqual(self.client.post("/playlist/9006/publish").status_code, 400)

    def test_the_automation_list_follows_the_account(self):
        save_playlists([{"id": "9007", "title": "Mine", "picture": "", "accounts": [self.alice]},
                        {"id": "9008", "title": "Theirs", "picture": "", "accounts": ["nd1"]}])
        self.use(self.alice)
        ids = [p["id"] for p in self.client.get("/api/scheduler/status").get_json()["playlists"]]
        self.assertEqual(ids, ["9007"])


if __name__ == "__main__":
    unittest.main()
