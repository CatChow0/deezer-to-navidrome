import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, mixes_db, stats_db, trial
from core.deezer import save_playlists

NOW = 1_800_000_000


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for db in (mixes_db.db_path(), stats_db.db_path()):
            for suffix in ("", "-wal", "-shm"):
                Path(f"{db}{suffix}").unlink(missing_ok=True)
        save_playlists([])
        config.save_preview_state({})
        patches = [
            mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}),
            mock.patch("core.deezer_dl.download_dir", return_value=self.root / "dl"),
            mock.patch("core.deezer_dl.download_arl", return_value="arl"),
            mock.patch("core.deezer_dl.download_dir_status", return_value={"writable": True}),
            mock.patch("core.mix_builder.library_entries", return_value=[]),
            mock.patch("core.metadata_fix.start_background"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.client = self.app.test_client()

    def add(self, deezer_id="1", state=None):
        conn = mixes_db.connect()
        path = trial.trial_dir() / f"{deezer_id}.flac"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        trial.add_download(conn, deezer_id, "Artist", f"Song {deezer_id}", "Album", path, "auto-discover", NOW)
        if state:
            conn.execute("UPDATE trial_tracks SET state=? WHERE deezer_id=?", (state, deezer_id))
            conn.commit()
        conn.close()
        return path

    def get(self):
        return self.client.get("/api/mixes").get_json()

    def post(self, url, body=None):
        return self.client.post(url, json=body if body is not None else {})

    def test_everything_is_off_at_first(self):
        data = self.get()
        self.assertFalse(data["settings"]["daily"])
        self.assertEqual(data["on_trial"], [])

    def test_turning_on_starts_the_tempo_analysis(self):
        from core import metadata_fix
        response = self.post("/api/mixes/settings", {"daily": True})
        self.assertTrue(response.get_json()["settings"]["daily"])
        metadata_fix.start_background.assert_called_once()

    def test_download_versions_refuse_without_an_account(self):
        with mock.patch("core.deezer_dl.download_arl", return_value=""):
            response = self.post("/api/mixes/settings", {"discover": True})
            self.assertEqual(response.status_code, 400)
            self.assertFalse(self.get()["settings"]["discover"])
            self.assertEqual(self.post("/api/mixes/settings", {"daily": True}).status_code, 200)

    def test_fix_metadata_button_starts_a_task_and_stays_on(self):
        from core import metadata_fix
        data = self.post("/api/metadata/fix").get_json()
        self.assertTrue(data["task_id"])
        metadata_fix.start_background.assert_called_once()
        conn = mixes_db.connect()
        self.addCleanup(conn.close)
        self.assertTrue(mixes_db.get_meta(conn, "metadata_fix_on"))

    def test_the_button_turns_writing_back_on_after_an_undo(self):
        conn = mixes_db.connect()
        self.addCleanup(conn.close)
        mixes_db.set_meta(conn, "metadata_write_off", True)
        self.post("/api/metadata/fix")
        self.assertFalse(mixes_db.get_meta(conn, "metadata_write_off"))

    def test_undo_starts_a_task(self):
        with mock.patch("core.metadata_fix.start_undo") as start:
            data = self.post("/api/metadata/undo").get_json()
        start.assert_called_once_with(data["task_id"])

    def test_status_is_in_the_state(self):
        analysis = self.get()["analysis"]
        for key in ("tagged", "only_in_app", "write_errors", "can_undo", "write_off"):
            self.assertIn(key, analysis)

    def test_settings_offer_the_threads_and_save_them(self):
        page = self.client.get("/config", headers={"Accept": "text/html"}).data.decode()
        self.assertIn('name="metadata_workers"', page)
        self.client.post("/config", data={"scan_dirs": "/music/library", "playlists_base_dir": "/music/playlists",
                                          "metadata_workers": "8"})
        self.assertEqual(config.load_config()["metadata_workers"], 8)

    def test_nothing_is_tagged_until_asked(self):
        from core import metadata_fix
        self.client.get("/api/mixes")
        metadata_fix.start_background.assert_not_called()

    def test_bad_limit_is_refused(self):
        self.assertEqual(self.post("/api/mixes/settings", {"max_unheard": "lots"}).status_code, 400)

    def test_generate_needs_a_version_on(self):
        self.assertEqual(self.post("/api/mixes/generate").status_code, 400)

    def test_generate_starts_a_task(self):
        self.post("/api/mixes/settings", {"daily": True})
        with mock.patch("core.mix_builder.start_task", return_value="t1") as start:
            response = self.post("/api/mixes/generate")
        self.assertEqual(response.get_json()["task_id"], "t1")
        start.assert_called_once_with(["daily"])

    def test_keep_and_remove_and_restore(self):
        path = self.add("1")
        self.assertEqual(self.get()["on_trial"][0]["id"], "1")
        data = self.post("/api/mixes/trial/1/remove").get_json()
        self.assertEqual(data["trash"][0]["id"], "1")
        self.assertFalse(path.exists())
        data = self.post("/api/mixes/trial/1/restore").get_json()
        self.assertEqual(data["trash"], [])
        self.add("2")
        data = self.post("/api/mixes/trial/2/keep").get_json()
        self.assertEqual(data["on_trial"], [])

    def test_an_unmapped_folder_does_not_fail_a_decision_already_made(self):
        path = self.add("1")
        with mock.patch("core.mix_builder.publish_trial_playlist", side_effect=ValueError("Unmapped path")):
            response = self.post("/api/mixes/trial/1/remove")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(path.exists())

    def test_unknown_track_is_an_error(self):
        self.assertEqual(self.post("/api/mixes/trial/404/remove").status_code, 400)

    def test_remove_all_only_takes_what_waits(self):
        self.add("1", state="pending")
        self.add("2")
        data = self.post("/api/mixes/trial/remove-pending").get_json()
        self.assertEqual(data["removed"], 1)
        self.assertEqual([t["id"] for t in data["on_trial"]], ["2"])

    def test_counts_for_the_page(self):
        self.add("1", state="pending")
        self.assertEqual(self.get()["pending"][0]["id"], "1")

    def test_dashboard_has_the_section_and_generated_tiles_stay_apart(self):
        save_playlists([{"id": "auto-daily-1", "title": "Daily Mix 1", "picture": "", "subtitle": "Around X"},
                        {"id": "123", "title": "Mine", "picture": "x"}])
        with mock.patch("core.deezer.cache_cover", return_value=None):
            page = self.client.get("/", headers={"Accept": "text/html"}).data.decode()
        made = page[page.index('id="mfy-section-title"'):page.index('id="mixes-title"')]
        self.assertIn('data-playlist-id="auto-daily-1"', made)
        self.assertIn("Around X", made)
        self.assertNotIn('data-playlist-id="123"', made)
        self.assertIn('id="mfy-modal"', page)


if __name__ == "__main__":
    unittest.main()
