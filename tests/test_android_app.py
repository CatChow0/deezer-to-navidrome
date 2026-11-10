"""The Android app inside the server image: what /api/v1/app says about it,
its download, and the Settings block that offers it."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core.android_app
from tests.test_api_v1 import Base

META = {"version": "1.18.0", "version_code": 11800, "commit": "abc1234", "built_at": "2026-11-09T12:00:00Z"}


class AndroidApp(Base):
    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(core.android_app, "DIST_DIR", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        core.android_app._hashes.clear()

    def put_apk(self, data=b"PK\x03\x04fake apk", meta=META):
        (core.android_app.DIST_DIR / "deezer-to-navidrome.apk").write_bytes(data)
        (core.android_app.DIST_DIR / "app.json").write_text(json.dumps(meta), encoding="utf-8")
        return data

    def test_without_an_apk_the_app_is_not_available(self):
        auth = {"Authorization": f"Bearer {self.token()}"}
        self.assertEqual(self.client.get("/api/v1/app", headers=auth).get_json(),
                         {"available": False, "reason": "This image was built without the Android app."})
        missing = self.client.get("/api/v1/app/apk", headers=auth)
        self.assertEqual((missing.status_code, missing.get_json()["error"]["code"]), (404, "not_found"))

    def test_the_apk_and_what_it_is(self):
        data = self.put_apk()
        auth = {"Authorization": f"Bearer {self.token()}"}
        self.assertEqual(self.client.get("/api/v1/app", headers=auth).get_json(), {
            "available": True, "version": "1.18.0", "version_code": 11800,
            "build": {"commit": "abc1234", "built_at": "2026-11-09T12:00:00Z"},
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        apk = self.client.get("/api/v1/app/apk", headers=auth)
        self.assertEqual((apk.status_code, apk.mimetype, apk.data), (200, "application/vnd.android.package-archive", data))
        self.assertIn("deezer-to-navidrome-1.18.0.apk", apk.headers["Content-Disposition"])
        again = self.client.get("/api/v1/app/apk", headers={**auth, "If-None-Match": apk.headers["ETag"]})
        self.assertEqual(again.status_code, 304)
        apk.close()

    def test_the_size_and_hash_come_from_the_file(self):
        # A stale app.json, or a hash kept from before, cannot lie about the file.
        self.put_apk(data=b"first")
        self.assertEqual(core.android_app.info()["size"], 5)
        (core.android_app.DIST_DIR / "deezer-to-navidrome.apk").write_bytes(b"second, longer")
        info = core.android_app.info()
        self.assertEqual((info["size"], info["sha256"]), (14, hashlib.sha256(b"second, longer").hexdigest()))

    def test_a_damaged_app_json_means_no_app(self):
        self.put_apk()
        (core.android_app.DIST_DIR / "app.json").write_text("{not json", encoding="utf-8")
        self.assertFalse(core.android_app.info()["available"])
        self.put_apk(meta={"version": "1.18.0"})
        self.assertFalse(core.android_app.info()["available"])

    def test_the_download_needs_a_sign_in(self):
        self.put_apk()
        self.assertEqual(self.client.get("/api/v1/app").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/app/apk").status_code, 401)
        self.assertEqual(self.client.get("/app/android.apk").status_code, 401)
        with mock.patch.dict(os.environ, {"API_TOKEN": "catboard-token-123"}):
            catboard = self.client.get("/app/android.apk", headers={"Authorization": "Bearer catboard-token-123"})
            self.assertEqual(catboard.status_code, 401)

    def test_settings_offers_the_download(self):
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            empty = self.client.get("/config", headers={"Accept": "text/html"}).get_data(as_text=True)
            self.put_apk()
            page = self.client.get("/config", headers={"Accept": "text/html"}).get_data(as_text=True)
            web = self.client.get("/app/android.apk")
        self.assertIn("This image was built without the Android app.", empty)
        self.assertNotIn('href="/app/android.apk"', empty)
        self.assertIn("Android app", page)
        self.assertIn('href="/app/android.apk"', page)
        self.assertIn("build abc1234", page)
        self.assertEqual((web.status_code, web.mimetype), (200, "application/vnd.android.package-archive"))
        web.close()


if __name__ == "__main__":
    unittest.main()
