import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, stats_db, stats_files, stats_import
from core.stats_import import run_import
from tests.fixtures import make_navidrome
from tests.test_stats_db import reset
from tests.test_stats_import import ImportCase

OLD_SCHEMA = """
CREATE TABLE artists (id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, deezer_id TEXT, picture_url TEXT);
CREATE TABLE albums (id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, title TEXT NOT NULL, album_artist TEXT NOT NULL DEFAULT '', cover_url TEXT);
CREATE TABLE tracks (id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, title TEXT NOT NULL, artist_display TEXT NOT NULL DEFAULT '',
    duration_sec REAL, duration_source TEXT, genre TEXT, genre_source TEXT, deezer_track_id TEXT, deezer_album_id TEXT, cover_url TEXT, lookup_at INTEGER);
CREATE TABLE track_artists (track_id INTEGER NOT NULL, artist_id INTEGER NOT NULL, position INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (track_id, artist_id));
CREATE TABLE plays (id INTEGER PRIMARY KEY, track_id INTEGER NOT NULL, album_id INTEGER, duration_sec REAL, listened_at INTEGER NOT NULL, source TEXT NOT NULL, UNIQUE (track_id, listened_at));
CREATE TABLE maloja_pairs (maloja_ts INTEGER PRIMARY KEY, partner_ts INTEGER NOT NULL);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO tracks(id, key, title) VALUES (1, 'a|song', 'Song');
INSERT INTO plays(track_id, listened_at, source) VALUES (1, 1000, 'navidrome');
"""


class Migration(unittest.TestCase):
    def setUp(self):
        reset()

    def columns(self, conn, table):
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def test_current_live_schema_is_upgraded_and_keeps_plays(self):
        old = sqlite3.connect(stats_db.db_path())
        old.executescript(OLD_SCHEMA)
        old.close()
        for _ in range(2):  # safe to run again
            conn = stats_db.connect()
            self.assertEqual(stats_db.play_count(conn), 1)
            self.assertIn("file_path", self.columns(conn, "tracks"))
            self.assertIn("file_path", self.columns(conn, "albums"))
            self.assertIn("lookup_at", self.columns(conn, "artists"))
            self.assertIn("item_key", self.columns(conn, "covers"))
            conn.close()

    def test_new_database_has_the_columns(self):
        conn = stats_db.connect()
        self.assertIn("file_path", self.columns(conn, "tracks"))
        conn.close()


class FilesCase(unittest.TestCase):
    def setUp(self):
        reset()
        self.root = Path(tempfile.mkdtemp(prefix="d2n-music-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.music = self.root / "library"
        self.music.mkdir()
        self.outside = self.root / "private"
        self.outside.mkdir()
        cache = Path(config.DATA_DIR) / "music_library_cache.json"
        if cache.exists():
            cache.unlink()
        stats_import._library_cache.clear()
        paths = mock.patch.object(config, "get_paths_from_config",
                                  return_value=([self.music], Path("/none"), cache, {self.music: Path("/music")}))
        paths.start()
        self.addCleanup(paths.stop)

    def song(self, relative="Artist/Album/01.flac", base=None):
        path = (base or self.music) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return path


class LocalFile(FilesCase):
    def test_stored_path_inside_music_folder(self):
        path = self.song()
        self.assertEqual(stats_files.local_file({"key": "a|b", "file_path": str(path)}), path)

    def test_outside_the_music_folders_is_refused(self):
        secret = self.song("secret.flac", self.outside)
        self.assertIsNone(stats_files.local_file({"key": "a|b", "file_path": str(secret)}))

    def test_path_traversal_is_refused(self):
        self.song("secret.flac", self.outside)
        sneaky = self.music / ".." / "private" / "secret.flac"
        self.assertIsNone(stats_files.local_file({"key": "a|b", "file_path": str(sneaky)}))

    def test_symlink_leaving_the_music_folder_is_refused(self):
        secret = self.song("secret.flac", self.outside)
        link = self.music / "link.flac"
        try:
            os.symlink(secret, link)
        except OSError:
            self.skipTest("Symlinks need more rights here")
        self.assertIsNone(stats_files.local_file({"key": "a|b", "file_path": str(link)}))

    def test_missing_file_and_no_path_are_absent(self):
        self.assertIsNone(stats_files.local_file({"key": "a|b", "file_path": str(self.music / "gone.flac")}))
        self.assertIsNone(stats_files.local_file({"key": "a|b", "file_path": None}))

    def test_library_index_is_the_fallback(self):
        import json
        path = self.song()
        cache = Path(config.DATA_DIR) / "music_library_cache.json"
        cache.write_text(json.dumps({"library": [{"tag_artist": "A", "tag_title": "Song", "duration": 100.0, "path": str(path)}]}), encoding="utf-8")
        key = stats_db.track_key(["A"], "Song")
        self.assertEqual(stats_files.local_file({"key": key, "file_path": None}), path)
        self.assertEqual(stats_files.local_file({"key": key, "file_path": str(self.music / "moved.flac")}), path)

    def test_a_folder_named_like_a_music_folder_is_not_inside_it(self):
        twin = self.root / "library-private"
        twin.mkdir()
        secret = self.song("x.flac", twin)
        self.assertIsNone(stats_files.local_file({"key": "a|b", "file_path": str(secret)}))

    def test_navidrome_path_maps_to_this_container(self):
        self.assertEqual(stats_files.container_path("/music", "Artist/Album/01.flac"), str(self.music / "Artist" / "Album" / "01.flac"))
        self.assertIsNone(stats_files.container_path("/elsewhere", "Artist/01.flac"))
        self.assertIsNone(stats_files.container_path("/music", ""))
        self.assertIsNone(stats_files.container_path("/music", "../../etc/passwd"))


class MergeStoresPaths(ImportCase):
    def setUp(self):
        super().setUp()
        cache = Path(config.LIBRARY_CACHE_FILE)
        patcher = mock.patch.object(config, "get_paths_from_config",
                                    return_value=([Path("/m/lib")], Path("/none"), cache, {Path("/m/lib"): Path("/music")}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_merge_fills_track_and_album_files(self):
        make_navidrome(self.nav, [
            {"ts": 1000, "title": "Song", "artist": "A", "album": "Single", "file": "A/Single/01.flac"},
            {"ts": 2000, "title": "Song", "artist": "A", "album": "Big Album", "file": "A/Big Album/05.flac"},
        ])
        run_import("merge")
        conn = stats_db.connect()
        track = conn.execute("SELECT file_path FROM tracks").fetchone()[0]
        albums = {r["title"]: r["file_path"] for r in conn.execute("SELECT title, file_path FROM albums")}
        conn.close()
        self.assertEqual(Path(track), Path("/m/lib/A/Big Album/05.flac"))  # the newest file
        self.assertEqual(Path(albums["Single"]), Path("/m/lib/A/Single/01.flac"))
        self.assertEqual(Path(albums["Big Album"]), Path("/m/lib/A/Big Album/05.flac"))

    def test_older_navidrome_without_library_table_still_imports(self):
        conn = sqlite3.connect(self.nav)
        conn.executescript("""
            CREATE TABLE media_file (id TEXT PRIMARY KEY, title TEXT, artist TEXT, album TEXT, album_artist TEXT, duration REAL, tags TEXT, participants TEXT);
            CREATE TABLE scrobbles (id INTEGER PRIMARY KEY, media_file_id TEXT, user_id TEXT, submission_time INTEGER);
            INSERT INTO media_file VALUES ('f', 'Song', 'A', 'Alb', 'A', 100, '{}', '{}');
            INSERT INTO scrobbles(media_file_id, user_id, submission_time) VALUES ('f', 'u', 1000);
        """)
        conn.commit()
        conn.close()
        self.assertEqual(run_import("merge")["after"], 1)


if __name__ == "__main__":
    unittest.main()
