import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, stats_db, stats_import
from tests.test_stats_db import reset


class Audio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        reset()
        self.root = Path(tempfile.mkdtemp(prefix="d2n-audio-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.music = self.root / "library"
        self.music.mkdir()
        stats_import._library_cache.clear()
        cache = Path(config.DATA_DIR) / "music_library_cache.json"
        if cache.exists():
            cache.unlink()
        for patcher in (
            mock.patch.object(config, "get_paths_from_config", return_value=([self.music], Path("/none"), cache, {self.music: Path("/music")})),
            mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = self.app.test_client()

    def track(self, path=None):
        conn = stats_db.connect("nd1")
        track = stats_db.upsert_track(conn, "Song", ["A"])
        conn.execute("UPDATE tracks SET file_path = ? WHERE id = ?", (str(path) if path else None, track))
        conn.commit()
        conn.close()
        return track

    def song(self, name="01.flac", base=None):
        path = (base or self.music) / name
        path.write_bytes(bytes(range(256)) * 10)
        return path

    def test_whole_file(self):
        response = self.client.get(f"/stats/audio/{self.track(self.song())}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "audio/flac")
        self.assertEqual(len(response.data), 2560)
        response.close()

    def test_range_requests_can_seek(self):
        response = self.client.get(f"/stats/audio/{self.track(self.song())}", headers={"Range": "bytes=256-511"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, bytes(range(256)))
        response.close()

    def test_no_file_is_404(self):
        self.assertEqual(self.client.get(f"/stats/audio/{self.track()}").status_code, 404)
        self.assertEqual(self.client.get(f"/stats/audio/{self.track(self.music / 'gone.flac')}").status_code, 404)

    def test_file_outside_the_music_folders_is_404(self):
        private = self.root / "private"
        private.mkdir()
        self.assertEqual(self.client.get(f"/stats/audio/{self.track(self.song('secret.flac', private))}").status_code, 404)

    def test_unknown_and_huge_ids(self):
        self.assertEqual(self.client.get("/stats/audio/99999").status_code, 404)
        self.assertEqual(self.client.get(f"/stats/audio/{10 ** 30}").status_code, 404)

    def test_sign_in_required(self):
        track = self.track(self.song())
        with mock.patch.dict(os.environ):
            del os.environ["DISABLE_AUTH"]
            self.assertEqual(self.client.get(f"/stats/audio/{track}").status_code, 401)


if __name__ == "__main__":
    unittest.main()
