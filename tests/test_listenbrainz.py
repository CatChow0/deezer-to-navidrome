import json
import os
import sqlite3
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from core import config, stats_db, stats_import, stats_ingest
from tests.test_stats_db import reset

TOKEN = "scrobble-secret"
BASE_TIME = 1700000000


def listen(ts=1000, title="Song", artist="A", **extra):
    meta = {"track_name": title, "artist_name": artist, "release_name": "Album", **extra}
    return {"listened_at": BASE_TIME + ts, "track_metadata": meta}


class ListenBrainz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        reset()
        config.save_secret("scrobble_token", TOKEN)
        self.addCleanup(config.save_secret, "scrobble_token", "")
        self.client = self.app.test_client()
        stats_import._library_cache.clear()
        cache = Path(config.LIBRARY_CACHE_FILE)
        if cache.exists():
            cache.unlink()

    def post(self, body, token=TOKEN, raw=False):
        headers = {"Authorization": f"Token {token}"} if token else {}
        if raw:
            return self.client.post("/apis/listenbrainz/1/submit-listens", data=body, headers=headers, content_type="application/json")
        return self.client.post("/apis/listenbrainz/1/submit-listens", json=body, headers=headers)

    def single(self, *listens):
        return self.post({"listen_type": "single", "payload": list(listens)})

    def plays(self):
        conn = stats_db.connect()
        try:
            return stats_db.play_count(conn)
        finally:
            conn.close()

    def test_no_or_wrong_token_is_401(self):
        self.assertEqual(self.post({"listen_type": "single", "payload": [listen()]}, token=None).status_code, 401)
        self.assertEqual(self.post({"listen_type": "single", "payload": [listen()]}, token="nope").status_code, 401)
        self.assertEqual(self.plays(), 0)

    def test_disable_auth_does_not_open_the_route(self):
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            self.assertEqual(self.post({"listen_type": "single", "payload": [listen()]}, token="nope").status_code, 401)
        self.assertEqual(self.plays(), 0)

    def test_no_token_configured_rejects_everything(self):
        config.save_secret("scrobble_token", "")
        self.assertEqual(self.post({"listen_type": "single", "payload": [listen()]}, token="").status_code, 401)
        self.assertEqual(self.client.post(
            "/apis/listenbrainz/1/submit-listens", json={"payload": []}, headers={"Authorization": "Token "}
        ).status_code, 401)

    def test_validate_token(self):
        good = self.client.get("/apis/listenbrainz/1/validate-token", headers={"Authorization": f"Token {TOKEN}"})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.get_json()["code"], 200)
        self.assertIs(good.get_json()["valid"], True)
        self.assertTrue(good.get_json()["user_name"])
        bad = self.client.get("/apis/listenbrainz/1/validate-token", headers={"Authorization": "Token nope"})
        self.assertEqual(bad.status_code, 200)
        self.assertIs(bad.get_json()["valid"], False)

    def test_token_prefix_any_case(self):
        response = self.client.post(
            "/apis/listenbrainz/1/submit-listens",
            json={"listen_type": "single", "payload": [listen()]},
            headers={"Authorization": f"token {TOKEN}"},
        )
        self.assertEqual(response.status_code, 200)

    def test_single_listen_stored(self):
        response = self.single(listen(title="Song", artist="A • B", additional_info={"duration_ms": 200000}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")
        conn = stats_db.connect()
        self.assertEqual([r[0] for r in conn.execute("SELECT name FROM artists ORDER BY name")], ["A", "B"])
        play = conn.execute("SELECT duration_sec, source FROM plays").fetchone()
        self.assertEqual((play["duration_sec"], play["source"]), (200.0, "live"))
        conn.close()

    def test_playing_now_ignored(self):
        response = self.post({"listen_type": "playing_now", "payload": [{"track_metadata": {"track_name": "S", "artist_name": "A"}}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.plays(), 0)

    def test_duplicate_submission_counted_once(self):
        self.single(listen())
        self.single(listen())
        self.assertEqual(self.plays(), 1)

    def test_non_json_is_400(self):
        self.assertEqual(self.post("{not json", raw=True).status_code, 400)
        self.assertEqual(self.post([1, 2]).status_code, 400)
        self.assertEqual(self.post({"listen_type": "single", "payload": "nope"}).status_code, 400)

    def test_mixed_batch_keeps_valid(self):
        response = self.post({"listen_type": "import", "payload": [
            {"listened_at": 1, "track_metadata": {"artist_name": "A"}},
            {"listened_at": "abc", "track_metadata": {"track_name": "S", "artist_name": "A"}},
            {"track_metadata": {"track_name": "S", "artist_name": "A"}},
            {"listened_at": 2, "track_metadata": "nope"},
            "nope",
            {"listened_at": True, "track_metadata": {"track_name": "S", "artist_name": "A"}},
            {"listened_at": -5, "track_metadata": {"track_name": "S", "artist_name": "A"}},
            listen(5000),
        ]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.plays(), 1)

    def test_bad_duration_is_ignored(self):
        self.single(listen(additional_info={"duration_ms": "long"}))
        self.single(listen(2000, title="Other", additional_info="nope"))
        self.assertEqual(self.plays(), 2)

    def test_length_from_library_when_payload_has_none(self):
        Path(config.LIBRARY_CACHE_FILE).write_text(json.dumps(
            {"library": [{"tag_artist": "A", "tag_title": "Song", "duration": 123.0}]}), encoding="utf-8")
        self.single(listen())
        conn = stats_db.connect()
        row = conn.execute("SELECT duration_sec, duration_source FROM tracks").fetchone()
        self.assertEqual((row["duration_sec"], row["duration_source"]), (123.0, "library"))
        conn.close()

    def test_database_failure_is_503(self):
        with mock.patch.object(stats_ingest, "record_listens", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(self.single(listen()).status_code, 503)

    def test_listen_waits_during_import_transaction(self):
        stats_db.connect().close()
        holder = sqlite3.connect(stats_db.db_path(), check_same_thread=False)
        holder.execute("BEGIN IMMEDIATE")
        threading.Timer(1.0, holder.rollback).start()
        started = time.time()
        response = self.single(listen())
        holder.close()
        self.assertEqual(response.status_code, 200)
        self.assertGreater(time.time() - started, 0.5)
        self.assertEqual(self.plays(), 1)

    def test_login_not_required(self):
        response = self.single(listen())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Location"), None)

    def test_trailing_slash_routes(self):
        response = self.client.post(
            "/apis/listenbrainz/1/submit-listens/",
            json={"listen_type": "single", "payload": [listen()]},
            headers={"Authorization": f"Token {TOKEN}"},
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
