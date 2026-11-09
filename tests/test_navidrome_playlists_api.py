import os
import unittest
from pathlib import Path
from unittest import mock

from core import config, mixes_db, navidrome_db, nd_accounts, publish
from core.deezer import save_playlists
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
        conn.execute("DELETE FROM navidrome_playlists")
        conn.execute("DELETE FROM meta WHERE key LIKE 'sync:%'")
        conn.commit()
        conn.close()
        patches = [mock.patch.dict(os.environ, {"DISABLE_AUTH": "true",
                                                "STATS_NAVIDROME_DB": str(Path(config.DATA_DIR) / "absent.db")}),
                   mock.patch("core.deezer.cache_cover", return_value=None)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        navidrome_db.forget_songs()
        self.server = FakeSubsonic().start()
        self.addCleanup(self.server.stop)
        self.server.add_user("alice", "alice-pass", admin=True)
        self.server.add_user("bob", "bob-pass")
        self.server.add_song("s1", "Song 1", "A", album="Album A", duration=185)
        for pid, owner, name in (("hand-1", "alice", "Made by hand"), ("bob-1", "bob", "Bob's own")):
            self.server.playlists[pid] = {"id": pid, "name": name, "owner": owner, "comment": "", "public": False,
                                          "songs": ["s1"], "created": "", "changed": ""}
        nd_accounts.ensure_initial()
        self.alice = nd_accounts.create({"label": "Alice", "url": self.server.url, "username": "alice",
                                         "secret": "alice-pass"})["id"]
        self.client = self.app.test_client()
        self.client.post("/api/navidrome/active", json={"id": self.alice})

    def test_the_dashboard_shows_what_this_profile_made_by_hand(self):
        publish.sync_account(self.alice)
        page = self.client.get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        self.assertIn("Also in Navidrome", page)
        self.assertIn('data-navidrome-playlist="hand-1"', page)
        self.assertNotIn('data-navidrome-playlist="bob-1"', page)
        self.assertIn(f"/navidrome/cover/{self.alice}/pl-hand-1", page)

    def test_a_renamed_playlist_shows_its_navidrome_name_to_this_profile_only(self):
        save_playlists([{"id": "555", "title": "Deezer name", "picture": "", "accounts": ["nd1", self.alice]}])
        config.update_preview_state("555", {"playlist_title": "Deezer name", "rows": []})
        publish.publish("555", "Deezer name", [], wait=True)
        renamed = next(p for p in self.server.playlists.values() if p["name"] == "Deezer name")
        renamed["name"] = "Alice's name"
        publish.sync_account(self.alice)
        page = self.client.get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        self.assertIn('data-title="Alice&#39;s name"', page)
        self.assertIn('data-deezer-title="Deezer name"', page)
        other = self.app.test_client()
        other.post("/api/navidrome/active", json={"id": "nd1"})
        self.assertIn('data-title="Deezer name"', other.get("/", headers={"Accept": "text/html"}).get_data(as_text=True))

    def test_cover_through_the_app(self):
        response = self.client.get(f"/navidrome/cover/{self.alice}/pl-hand-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertIn("max-age", response.headers["Cache-Control"])
        self.assertEqual(self.client.get(f"/navidrome/cover/{self.alice}/pl-nope").status_code, 404)
        self.assertEqual(self.client.get("/navidrome/cover/nd1/pl-hand-1").status_code, 404)

    def test_the_tracks_of_its_own_playlist_only(self):
        data = self.client.get(f"/api/navidrome/playlists/{self.alice}/hand-1").get_json()
        self.assertEqual(data["playlist"]["tracks"], [{"title": "Song 1", "artist": "A", "album": "Album A", "duration": 185}])
        # An admin in Navidrome sees Bob's private playlist there; not here.
        self.assertEqual(self.client.get(f"/api/navidrome/playlists/{self.alice}/bob-1").status_code, 404)
        self.assertEqual(self.client.get("/api/navidrome/playlists/nd1/hand-1").status_code, 404)

    def test_settings_show_the_last_sync(self):
        publish.sync_account(self.alice)
        state = self.client.get("/api/navidrome/accounts").get_json()
        sync = next(a for a in state["accounts"] if a["id"] == self.alice)["sync"]
        self.assertEqual(sync["handmade"], 1)
        self.assertIsNone(next(a for a in state["accounts"] if a["id"] == "nd1")["sync"])

    def test_the_profile_picker_is_always_there(self):
        nd_accounts.delete(self.alice)
        page = self.client.get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        self.assertIn("data-nd-account", page)
        self.assertIn(">Profile<", page)


if __name__ == "__main__":
    unittest.main()
