"""What an account of this app must not reach of another's: the cases a security
audit of 1.21.0 found, each as its fix keeps it from happening."""
import os
import unittest
from unittest import mock

from core import crypto, deezer_accounts, deezer_dl, devices, migrations, nd_accounts, users
from core.deezer import load_playlists, save_playlists
from tests.test_users import PASSWORD, Base

ND = "http://nd.example"


class Audit(Base):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        super().setUp()
        self.alice_nd = nd_accounts.create({"url": ND, "username": "alice", "secret": "x", "owner": self.alice["id"]})["id"]
        self.bob_nd = nd_accounts.create({"url": ND, "username": "bob", "secret": "x", "owner": self.bob["id"]})["id"]
        self.root_dz = deezer_accounts.create({"arl": "r" * 40, "owner": self.root["id"]}, check=False)["id"]
        self.sign_in("alice")

    def sign_in(self, name):
        self.client = self.app.test_client()
        self.assertEqual(302, self.client.post("/login", data={"username": name, "password": PASSWORD}).status_code)

    def test_a_playlist_saved_by_nobody_is_not_reached_by_its_id(self):
        for path in ("/playlist/4242/convert", "/playlist/mix-flow-default/preview", "/playlist/4242/navidrome"):
            with self.subTest(path=path):
                self.assertEqual(404, self.client.post(path).status_code if "convert" in path else self.client.get(path).status_code)

    def test_joining_a_saved_playlist_needs_to_be_able_to_read_it(self):
        from routes.playlists import PlaylistError, add_playlist_for

        save_playlists([{"id": "777", "title": "Private", "accounts": [self.bob_nd]}])
        with mock.patch("routes.playlists.fetch_deezer_playlist_info", side_effect=RuntimeError("no")):
            with self.assertRaises(PlaylistError):
                add_playlist_for("777", self.alice_nd)
        self.assertEqual([self.bob_nd], load_playlists()[0]["accounts"])

    def test_without_a_deezer_account_of_its_own_no_other_ones_is_used(self):
        self.assertEqual(400, self.client.get("/api/deezer/mixes").status_code)
        self.assertEqual(400, self.client.post("/api/deezer/mixes/follow", json={"kind": "flow", "source_id": "x"}).status_code)
        self.assertEqual(400, self.client.post("/api/releases/mute", json={"artist_id": "42", "muted": True}).status_code)
        self.assertEqual([], self.client.get("/api/releases").get_json()["releases"])
        deezer_accounts.set_download(self.root_dz)
        self.assertEqual("", deezer_dl.download_arl(None))
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "1"}):  # no accounts in this app: the server's one
            self.assertEqual("r" * 40, deezer_dl.download_arl(None))

    def test_a_password_that_is_not_temporary_is_not_replaced_without_the_current_one(self):
        self.assertEqual(302, self.client.post("/first-password", data={"password": "x" * 12, "confirm": "x" * 12}).status_code)
        self.assertEqual(302, self.app.test_client().post("/login", data={"username": "alice", "password": PASSWORD}).status_code)
        token = self.app.test_client().post("/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}).get_json()
        token = token.get("token") or token["data"]["token"]
        answer = self.app.test_client().post("/api/v1/auth/first-password", json={"password": "y" * 12},
                                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(409, answer.status_code)
        self.assertTrue(devices.verify(f"Bearer {token}"))

    def test_a_temporary_password_may_still_be_replaced(self):
        users.set_password(self.alice["id"], PASSWORD, must_change=True)
        self.sign_in("alice")
        self.assertEqual(200, self.client.post("/first-password", data={"password": "x" * 12, "confirm": "x" * 12}).status_code)

    def test_an_account_without_a_profile_sees_no_playlists_in_the_scheduler(self):
        users.create("carol", PASSWORD, users.STANDARD, must_change=False)
        save_playlists([{"id": "777", "title": "Bob's", "accounts": [self.bob_nd]}])
        self.sign_in("carol")
        self.assertEqual([], self.client.get("/api/scheduler/status").get_json()["playlists"])

    def test_the_api_does_not_open_another_accounts_navidrome_playlist(self):
        self.assertEqual(403, self.client.get(f"/api/v1/navidrome/playlists/{self.bob_nd}/abc").status_code)

    def test_the_navidrome_status_lists_only_your_profiles(self):
        save_playlists([{"id": "777", "title": "Mine", "accounts": [self.alice_nd]}])
        listed = self.client.get("/playlist/777/navidrome").get_json()["navidrome"]["accounts"]
        self.assertEqual([self.alice_nd], [a["id"] for a in listed])

    def test_a_download_does_not_mark_the_rows_of_another_accounts_playlist(self):
        deezer_accounts.create({"arl": "a" * 40, "owner": self.alice["id"]}, check=False)
        save_playlists([{"id": "777", "title": "Bob's", "accounts": [self.bob_nd]}])
        with mock.patch("routes.system.download_queue.enqueue_download") as queued:
            answer = self.client.post("/deezer-dl/track/5", json={"playlist_id": "777"})
        self.assertEqual(403, answer.status_code)
        queued.assert_not_called()

    def test_only_the_owner_of_the_first_profile_sets_the_automatic_downloads(self):
        save_playlists([{"id": "777", "title": "Shared", "accounts": [self.bob_nd, self.alice_nd]}])
        body = {"auto_scan_enabled": True, "auto_scan_interval_minutes": 60, "auto_download_after_scan": True}
        self.assertEqual(200, self.client.post("/playlist/777/automation", json=body).status_code)
        entry = load_playlists()[0]
        self.assertTrue(entry["auto_scan_enabled"])
        self.assertFalse(entry.get("auto_download_after_scan"))
        self.sign_in("bob")
        self.client.post("/playlist/777/automation", json=body)
        self.assertTrue(load_playlists()[0]["auto_download_after_scan"])

    def test_a_task_the_app_started_about_a_playlist_is_that_playlists(self):
        from core import config

        save_playlists([{"id": "777", "title": "Bob's", "accounts": [self.bob_nd]}])
        task = config.create_task("Auto scan: Bob's", kind="scan", playlist_id="777")  # no request: the app's own
        self.assertNotIn(task, [t["id"] for t in self.client.get("/api/tasks").get_json()["tasks"]])
        self.sign_in("bob")
        self.assertIn(task, [t["id"] for t in self.client.get("/api/tasks").get_json()["tasks"]])

    def test_listing_tasks_does_not_wait_on_deezer_nor_hold_the_tasks_lock(self):
        import threading
        import time

        from core import config

        save_playlists([{"id": "777", "accounts": [self.alice_nd]}])  # no title: load_playlists(refresh=True) would ask Deezer
        task = config.create_task("Auto scan", kind="scan", playlist_id="777")
        with mock.patch("core.deezer.fetch_deezer_playlist_info", side_effect=AssertionError("Deezer was asked")):
            self.assertIn(task, [t["id"] for t in self.client.get("/api/tasks").get_json()["tasks"]])
        release = threading.Event()
        started = threading.Event()

        def slow(task):
            started.set()
            release.wait(5)
            return True

        lister = threading.Thread(target=config.list_tasks, kwargs={"allow": slow})
        lister.start()
        started.wait(5)
        began = time.monotonic()
        config.create_task("Another")  # takes the lock: must not wait for the listing
        self.assertLess(time.monotonic() - began, 1)
        release.set()
        lister.join()

    def test_load_playlists_asks_deezer_only_when_told_to_and_a_dead_cover_is_not_retried(self):
        from core import deezer

        save_playlists([{"id": "777", "title": "T", "picture": "http://cover.example/x.jpg", "accounts": [self.alice_nd]}])
        with mock.patch("core.deezer.requests.get", side_effect=OSError("down")) as get:
            load_playlists()
            self.assertEqual(0, get.call_count)
            load_playlists(refresh=True)
            load_playlists(refresh=True)
            self.assertEqual(1, get.call_count)
        deezer._refresh_failed_at.clear()

    def test_deleting_a_playlist_twice_is_not_an_error_the_second_time(self):
        save_playlists([{"id": "777", "title": "Mine", "accounts": [self.alice_nd]}])
        with mock.patch("routes.playlists.publish.remove_from", return_value=True):
            self.assertEqual(302, self.client.post("/playlist/777/delete").status_code)
            self.assertEqual(302, self.client.post("/playlist/777/delete").status_code)
        self.assertEqual(404, self.client.get("/playlist/777/preview").status_code)

    def test_the_stream_of_your_own_task_works_and_not_that_of_another(self):
        from core import config

        mine = config.create_task("Mine")
        config.TASKS[mine]["owner"] = self.alice["id"]
        config.push_task_event(mine, "hello", stage="done", done=True)
        body = self.client.get(f"/tasks/{mine}/stream").get_data(as_text=True)
        self.assertIn("hello", body)
        self.sign_in("bob")
        self.assertIn("Task not found", self.client.get(f"/tasks/{mine}/stream").get_data(as_text=True))

    def test_the_first_profile_to_name_a_navidrome_user_keeps_it(self):
        earlier = nd_accounts.create({"url": ND, "username": "Shared", "secret": "x", "owner": self.bob["id"]})["id"]
        later = nd_accounts.create({"url": "http://other.example", "username": "shared", "secret": "x",
                                    "owner": self.alice["id"]})["id"]
        self.assertTrue(nd_accounts.claimed_earlier(later, "u1", "Shared"))
        self.assertFalse(nd_accounts.claimed_earlier(earlier, "u1", "Shared"))
        second = nd_accounts.create({"url": "http://third.example", "username": "SHARED", "secret": "x",
                                     "owner": self.bob["id"]})["id"]
        self.assertFalse(nd_accounts.claimed_earlier(second, "u1", "Shared"))  # the same account of this app

    def test_a_key_set_later_re_encrypts_the_account_stores_too(self):
        nd = nd_accounts.create({"url": ND, "username": "dave", "secret": "ND-SECRET", "owner": self.alice["id"]})["id"]
        users.set_field(self.alice["id"], "api_token", "TOKEN-VALUE-FOR-ALICE")
        stored = lambda: (nd_accounts.get(nd)["secret"], deezer_accounts.get(self.root_dz)["arl"])  # noqa: E731
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "a key set later on, long enough"}):
            self.assertTrue(all(crypto.needs_rewrap(v) for v in stored()))  # still the key file's
            self.assertGreaterEqual(migrations.rewrap_account_secrets(), 3)  # nd secret, ARL, token
            self.assertFalse(any(crypto.needs_rewrap(v) for v in stored()))
            self.assertEqual("ND-SECRET", nd_accounts.credentials(nd)["secret"])
            self.assertEqual("r" * 40, deezer_accounts.arl(self.root_dz))
            self.assertEqual("TOKEN-VALUE-FOR-ALICE", users.field(users.get(self.alice["id"]), "api_token"))
            self.assertEqual(0, migrations.rewrap_account_secrets())


if __name__ == "__main__":
    unittest.main()
