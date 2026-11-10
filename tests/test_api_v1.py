"""The API for the Android app: devices that sign in, its answers' format, and
following a task without a stream."""
import os
import re
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from core import auth, config, devices

REPO = Path(__file__).resolve().parent.parent
PASSWORD = "long-test-password"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"APP_USERNAME": "admin", "APP_PASSWORD": PASSWORD})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("DISABLE_AUTH", "API_TOKEN"):
            os.environ.pop(name, None)
        auth.limiter._entries.clear()
        self.addCleanup(auth.limiter._entries.clear)
        (Path(config.DATA_DIR) / "devices.json").unlink(missing_ok=True)
        self.client = self.app.test_client()

    def login(self, device="Pixel", password=PASSWORD, username="admin"):
        return self.client.post("/api/v1/auth/login", json={"username": username, "password": password, "device": device})

    def token(self, device="Pixel"):
        response = self.login(device)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["token"]

    def get(self, url, token=None, **headers):
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(url, headers=headers)


class SignIn(Base):
    def test_the_status_is_public_and_says_how_to_get_in(self):
        self.assertEqual(self.get("/api/v1/auth/status").get_json(), {"service": "deezer-to-navidrome", "api": 1, "auth": "required"})
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            self.assertEqual(self.get("/api/v1/auth/status").get_json()["auth"], "disabled")
        with mock.patch("core.auth.account_exists", return_value=False):
            self.assertEqual(self.get("/api/v1/auth/status").get_json()["auth"], "setup")

    def test_a_device_gets_a_token_that_opens_every_route(self):
        response = self.login("Anthony's Pixel")
        data = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["token"].startswith("d2n_"))
        self.assertEqual((data["device"]["name"], data["username"]), ("Anthony's Pixel", "admin"))
        info = self.get("/api/v1/info", data["token"])
        self.assertEqual(info.status_code, 200)
        self.assertEqual((info.get_json()["username"], info.get_json()["device"]["id"]), ("admin", data["device"]["id"]))
        # The web interface's own JSON routes too.
        self.assertEqual(self.get("/api/mixes", data["token"]).status_code, 200)
        # Only a digest is kept.
        self.assertNotIn(data["token"], (Path(config.DATA_DIR) / "devices.json").read_text(encoding="utf-8"))

    def test_a_wrong_password_and_too_many_of_them(self):
        response = self.login(password="nope")
        self.assertEqual((response.status_code, response.get_json()["error"]["code"]), (401, "wrong_credentials"))
        for _ in range(4):
            self.login(password="nope")
        blocked = self.login()
        self.assertEqual((blocked.status_code, blocked.get_json()["error"]["code"]), (429, "too_many_attempts"))
        self.assertTrue(int(blocked.headers["Retry-After"]) > 0)

    def test_signing_out_and_signing_a_device_out(self):
        mine, lost = self.token("Mine"), self.token("Lost")
        listed = self.get("/api/v1/devices", mine).get_json()["devices"]
        self.assertEqual(sorted(d["name"] for d in listed), ["Lost", "Mine"])
        self.assertEqual([d["current"] for d in listed if d["name"] == "Mine"], [True])
        lost_id = next(d["id"] for d in listed if d["name"] == "Lost")
        self.assertEqual(self.client.delete(f"/api/v1/devices/{lost_id}", headers={"Authorization": f"Bearer {mine}"}).status_code, 200)
        self.assertEqual(self.get("/api/v1/info", lost).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {mine}"}).get_json(), {"signed_out": True})
        self.assertEqual(self.get("/api/v1/info", mine).status_code, 401)
        self.assertEqual(self.client.delete("/api/v1/devices/nope", headers={"Authorization": f"Bearer {self.token()}"}).status_code, 404)

    def test_a_new_password_signs_every_device_out(self):
        token = self.token()
        with mock.patch.dict(os.environ, {"APP_PASSWORD": "another-long-password"}):
            self.assertEqual(self.get("/api/v1/info", token).status_code, 401)
        self.assertEqual(self.get("/api/v1/info", token).status_code, 200)

    def test_changing_the_password_in_settings_signs_the_devices_out(self):
        os.environ.pop("APP_USERNAME")
        os.environ.pop("APP_PASSWORD")
        auth.set_account("admin", PASSWORD)
        self.addCleanup(lambda: [config.save_secret(n, "") for n in ("app_username", "app_password_hash")])
        token = self.token()
        changed = self.client.post("/api/auth/password", json={"current": PASSWORD, "new": "a-brand-new-password"},
                                   headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.get("/api/v1/info", token).status_code, 401)
        self.assertEqual(devices.list_devices(), [])

    def test_the_catboard_token_stays_read_only(self):
        with mock.patch.dict(os.environ, {"API_TOKEN": "catboard-token-123"}):
            self.assertEqual(self.get("/api/releases", "catboard-token-123").status_code, 200)
            self.assertEqual(self.get("/api/v1/info", "catboard-token-123").status_code, 401)

    def test_creating_the_account_from_the_app(self):
        os.environ.pop("APP_USERNAME")
        os.environ.pop("APP_PASSWORD")
        self.addCleanup(lambda: [config.save_secret(n, "") for n in ("app_username", "app_password_hash")])
        short = self.client.post("/api/v1/auth/setup", json={"username": "me", "password": "short"})
        self.assertEqual(short.status_code, 400)
        made = self.client.post("/api/v1/auth/setup", json={"username": "me", "password": PASSWORD, "device": "Phone"})
        self.assertEqual(made.status_code, 201)
        self.assertEqual(self.get("/api/v1/info", made.get_json()["token"]).get_json()["username"], "me")
        again = self.client.post("/api/v1/auth/setup", json={"username": "other", "password": PASSWORD})
        self.assertEqual((again.status_code, again.get_json()["error"]["code"]), (409, "account_exists"))

    def test_with_sign_in_turned_off(self):
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            response = self.login()
            self.assertEqual((response.status_code, response.get_json()["error"]["code"]), (409, "auth_disabled"))
            self.assertEqual(self.get("/api/v1/info").status_code, 200)


class Format(Base):
    def test_failures_answer_in_the_apis_format(self):
        missing = self.get("/api/v1/info")
        self.assertEqual((missing.status_code, missing.get_json()["error"]["code"]), (401, "unauthorized"))
        token = self.token()
        unknown = self.get("/api/v1/nothing-here", token)
        self.assertEqual((unknown.status_code, unknown.get_json()["error"]["code"]), (404, "not_found"))
        wrong = self.client.delete("/api/v1/info", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual((wrong.status_code, wrong.get_json()["error"]["code"]), (405, "method_not_allowed"))

    def test_a_read_says_when_nothing_changed(self):
        token = self.token()
        first = self.get("/api/v1/info", token)
        self.assertTrue(first.headers.get("ETag"))
        again = self.get("/api/v1/info", token, **{"If-None-Match": first.headers["ETag"]})
        self.assertEqual((again.status_code, again.data), (304, b""))

    def test_a_read_is_kept_per_profile(self):
        token = self.token()
        read = self.get("/api/v1/info", token)
        # The app's offline cache matches on it: one profile never gets
        # another's saved answer.
        self.assertIn("X-Navidrome-Account", read.headers.get("Vary", ""))
        # Asked again each time, yet kept for when the server is unreachable.
        self.assertEqual(read.headers["Cache-Control"], "private, max-age=0")
        failed = self.get("/api/v1/nothing-here", token)
        self.assertEqual(failed.headers["Cache-Control"], "no-store")

    def test_the_profile_comes_from_the_header(self):
        from core import nd_accounts

        (Path(config.DATA_DIR) / "navidrome_accounts.json").unlink(missing_ok=True)
        nd_accounts.ensure_initial()
        bob = nd_accounts.create({"label": "Bob", "url": "http://navidrome:4533", "username": "bob", "secret": "b"})["id"]
        token = self.token()
        self.assertEqual(self.get("/api/v1/info", token).get_json()["profile"], "nd1")
        self.assertEqual(self.get("/api/v1/info", token, **{"X-Navidrome-Account": bob}).get_json()["profile"], bob)

    def test_every_route_is_in_the_contract(self):
        text = (REPO / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
        documented, path = set(), None
        for line in text.splitlines():
            found = re.match(r"^  (/api/v1/\S*):\s*$", line)
            if found:
                path = found.group(1)
                continue
            method = re.match(r"^    (get|post|put|patch|delete):\s*$", line)
            if path and method:
                documented.add((method.group(1).upper(), path))
        served = set()
        for rule in self.app.url_map.iter_rules():
            if rule.rule.startswith("/api/v1/"):
                for method in rule.methods - {"HEAD", "OPTIONS"}:
                    # <int:x>, <path:x> and <any(a, b):x> are all {x}.
                    served.add((method, re.sub(r"<(?:[a-z]+(?:\([^)]*\))?:)?([a-z_]+)>", r"{\1}", rule.rule)))
        self.assertEqual(served - documented, set(), "routes missing from docs/api/openapi.yaml")
        self.assertEqual(documented - served, set(), "documented routes the app does not serve")


class Tasks(Base):
    def setUp(self):
        super().setUp()
        self.auth = {"Authorization": f"Bearer {self.token()}"}

    def events(self, task_id, **args):
        query = "&".join(f"{k}={v}" for k, v in args.items())
        return self.client.get(f"/api/v1/tasks/{task_id}/events?{query}", headers=self.auth).get_json()

    def test_the_events_after_the_last_one_seen(self):
        task_id = config.create_task("Test", kind="test")
        config.push_task_event(task_id, "one", progress=10)
        config.push_task_event(task_id, "two", progress=20)
        first = self.events(task_id)
        self.assertEqual([(e["index"], e["message"]) for e in first["events"]], [(0, "one"), (1, "two")])
        self.assertEqual(first["after"], 1)
        self.assertEqual(self.events(task_id, after=1)["events"], [])
        self.assertEqual(self.events(task_id, after=1)["after"], 1)

    def test_waiting_for_the_next_event(self):
        task_id = config.create_task("Test", kind="test")
        config.push_task_event(task_id, "one")
        threading.Timer(0.3, lambda: config.push_task_event(task_id, "two")).start()
        started = time.monotonic()
        data = self.events(task_id, after=0, wait=5)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual([e["message"] for e in data["events"]], ["two"])
        started = time.monotonic()
        self.assertEqual(self.events(task_id, after=1, wait=1)["events"], [])
        self.assertGreaterEqual(time.monotonic() - started, 0.9)
        config.push_task_event(task_id, "done", done=True)
        started = time.monotonic()
        self.events(task_id, after=2, wait=5)
        self.assertLess(time.monotonic() - started, 1)

    def test_the_list_since_a_moment_and_the_rest(self):
        old = config.create_task("Old", kind="test")
        moment = time.time()
        time.sleep(0.01)
        new = config.create_task("New", kind="test")
        config.push_task_event(new, "moving")
        since = [t["id"] for t in self.client.get(f"/api/v1/tasks?changed_since={moment}", headers=self.auth).get_json()["tasks"]]
        self.assertIn(new, since)
        self.assertNotIn(old, since)
        self.assertEqual(self.client.get(f"/api/v1/tasks/{new}", headers=self.auth).get_json()["task"]["events"], 1)
        self.assertEqual(self.client.get("/api/v1/tasks/nope", headers=self.auth).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/tasks/nope/cancel", headers=self.auth).status_code, 404)
        refused = self.client.post(f"/api/v1/tasks/{new}/cancel", headers=self.auth)
        self.assertEqual((refused.status_code, refused.get_json()["error"]["code"]), (409, "not_cancellable"))
        stream = self.client.get(f"/api/v1/tasks/{new}/stream", headers=self.auth)
        self.assertEqual(stream.mimetype, "text/event-stream")
        stream.close()


if __name__ == "__main__":
    unittest.main()
