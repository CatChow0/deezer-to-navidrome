import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, stats_db, stats_import
from tests.fixtures import make_navidrome
from tests.test_stats_db import reset


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        reset()
        shutil.rmtree(Path(config.DATA_DIR) / "stats_sources", True)
        self.src = Path(tempfile.mkdtemp(prefix="d2n-api-"))
        self.addCleanup(shutil.rmtree, self.src, True)
        env = {"DISABLE_AUTH": "true", "STATS_NAVIDROME_DB": str(self.src / "nd.db"), "STATS_MALOJA_DB": str(self.src / "ml.db")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(config.save_secret, "scrobble_token", "")
        self.client = self.app.test_client()

    def test_sign_in_required(self):
        with mock.patch.dict(os.environ):
            del os.environ["DISABLE_AUTH"]
            for path in ("/api/stats/status", "/api/stats/recaps?tz=UTC", "/api/stats/plays"):
                self.assertEqual(self.client.get(path).status_code, 401, path)
            self.assertEqual(self.client.post("/api/stats/import", json={"mode": "merge"}).status_code, 401)
            page = self.client.get("/stats", headers={"Accept": "text/html"})
            self.assertEqual(page.status_code, 302)

    def test_bad_period_is_400(self):
        for path in (
            "/api/stats/overview?period=month&key=2026-13&tz=UTC",
            "/api/stats/overview?period=month&key=2026-10&tz=Mars/Olympus",
            "/api/stats/overview?period=month&key=2026-10",
            "/api/stats/overview?period=day&key=2026-10&tz=UTC",
            "/api/stats/recap?type=week&key=2026-W01&tz=UTC",
            "/api/stats/recaps",
            "/api/stats/artist/1",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 400, path)
            self.assertFalse(response.get_json()["ok"])

    def test_good_period_returns_data(self):
        response = self.client.get("/api/stats/overview?period=all&tz=UTC")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["totals"]["plays"], 0)

    def test_unknown_entity_is_404(self):
        self.assertEqual(self.client.get("/api/stats/artist/99999?tz=UTC").status_code, 404)

    def test_import_refused_message_is_409(self):
        response = self.client.post("/api/stats/import", json={"mode": "clean"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("Navidrome", response.get_json()["error"])

    def test_second_import_while_running_is_409(self):
        make_navidrome(self.src / "nd.db", [{"ts": 1000, "title": "One"}])
        self.assertTrue(stats_import._running.acquire(blocking=False))
        self.addCleanup(stats_import._running.release)
        response = self.client.post("/api/stats/import", json={"mode": "merge"})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.client.get("/api/stats/status").get_json()["import_running"])

    def test_invalid_import_mode_is_400(self):
        self.assertEqual(self.client.post("/api/stats/import", json={"mode": "all"}).status_code, 400)
        self.assertEqual(self.client.post("/api/stats/import", data="x").status_code, 400)

    def test_import_task_runs_and_is_tracked(self):
        make_navidrome(self.src / "nd.db", [{"ts": 1000, "title": "One"}])
        response = self.client.post("/api/stats/import", json={"mode": "merge"})
        self.assertEqual(response.status_code, 202)
        task_id = response.get_json()["task_id"]
        for _ in config.follow_task(task_id, keepalive=5):
            if config.TASKS[task_id]["done"]:
                break
        self.assertFalse(config.TASKS[task_id]["error"])
        status = self.client.get("/api/stats/status").get_json()
        self.assertEqual(status["plays"], 1)
        self.assertEqual(status["last_import"]["after"], 1)

    def test_token_paste_generate_and_env_lock(self):
        made = self.client.post("/api/stats/token", json={}).get_json()["token"]
        self.assertGreater(len(made), 20)
        self.assertEqual(self.client.get("/api/stats/status").get_json()["token"], made)
        pasted = self.client.post("/api/stats/token", json={"token": "my-existing-token"})
        self.assertEqual(pasted.get_json()["token"], "my-existing-token")
        self.assertEqual(self.client.post("/api/stats/token", json={"token": "short"}).status_code, 400)
        self.assertEqual(self.client.delete("/api/stats/token").status_code, 200)
        self.assertEqual(self.client.get("/api/stats/status").get_json()["token"], "")
        with mock.patch.dict(os.environ, {"SCROBBLE_TOKEN": "from-the-env-123"}):
            status = self.client.get("/api/stats/status").get_json()
            self.assertTrue(status["token_from_env"])
            self.assertEqual(status["token"], "from-the-env-123")
            self.assertEqual(self.client.post("/api/stats/token", json={}).status_code, 409)
            self.assertEqual(self.client.delete("/api/stats/token").status_code, 409)

    def test_status_never_breaks_on_empty_db(self):
        status = self.client.get("/api/stats/status").get_json()
        self.assertEqual(status["plays"], 0)
        self.assertIsNone(status["last_play_at"])
        self.assertIsNone(status["last_import"])
        self.assertFalse(status["sources"]["can_merge"])
        self.assertEqual(status["enrich"], {"pending": 0, "done": 0})
        self.assertIn("/apis/listenbrainz/1/", status["base_url_hint"])

    def test_plays_route_pages(self):
        conn = stats_db.connect()
        stats_db.add_play(conn, stats_db.upsert_track(conn, "Song", ["A"]), None, 100, 1000, "live")
        conn.commit()
        conn.close()
        data = self.client.get("/api/stats/plays?q=song&page=1").get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(self.client.get("/api/stats/plays?page=abc").status_code, 200)

    def test_stats_page_renders(self):
        response = self.client.get("/stats", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-view-name="stats"', response.data)

    def test_history_lives_in_the_stats_view_and_the_token_in_settings(self):
        page = self.client.get("/stats", headers={"Accept": "text/html"}).data.decode()
        stats = page[page.index('data-view-name="stats"'):page.index('data-view-name="releases"')]
        settings = page[page.index('data-view-name="settings"'):]
        self.assertIn("data-stats-history", stats)
        self.assertNotIn("data-stats-history", settings)
        self.assertIn("data-stats-settings", settings)

    def test_settings_keeps_every_section_inside_one_form_or_group(self):
        page = self.client.get("/config", headers={"Accept": "text/html"}).data.decode()
        for marker in ("sources-title", "mapping-title", "dl-title", "perf-title", "feed-settings-title", "files-title",
                       "account-title", "listening-title", "security-title", "index-title", "settings-activity-title", "danger-title"):
            self.assertEqual(page.count(f'aria-labelledby="{marker}"'), 1, marker)
        form = page[page.index('id="settings-form"'):page.index("</form>", page.index('id="settings-form"'))]
        for field in ("scan_dirs", "mapping_host[]", "deezer_dl_dir", "library_workers_per_dir", "release_refresh_hours", "playlists_base_dir"):
            self.assertIn(f'name="{field}"', form)
        settings = page[page.index('data-view-name="settings"'):page.index("</main>")]
        self.assertNotIn("<aside", settings)

    def test_reset_buttons_leave_history_alone(self):
        conn = stats_db.connect()
        stats_db.add_play(conn, stats_db.upsert_track(conn, "Song", ["A"]), None, 100, 1000, "live")
        conn.commit()
        conn.close()
        response = self.client.post("/admin/clear/all")
        self.assertIn(response.status_code, (200, 302))
        conn = stats_db.connect()
        self.assertEqual(stats_db.play_count(conn), 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
