import base64
import io
import os
import shutil
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3
from PIL import Image

from core import config, stats_covers, stats_db, stats_enrich, stats_import, stats_queries
from tests.test_stats_db import reset


def image_bytes(color=(200, 30, 60), size=(50, 50), fmt="JPEG"):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt)
    return out.getvalue()


def flac_file(path, art=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    info = struct.pack(">HH", 4096, 4096) + b"\x00" * 6 + (44100 << 12 | 1 << 9 | 15 << 4).to_bytes(4, "big") + b"\x00" * 24
    path.write_bytes(b"fLaC\x80\x00\x00\x22" + info)
    if art:
        audio = FLAC(path)
        picture = Picture()
        picture.type = 3
        picture.mime = "image/jpeg"
        picture.data = art
        audio.add_picture(picture)
        audio.save()
    return path


class CoversCase(unittest.TestCase):
    def setUp(self):
        reset()
        shutil.rmtree(Path(config.DATA_DIR) / "stats_covers", True)
        self.root = Path(tempfile.mkdtemp(prefix="d2n-covers-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.music = self.root / "library"
        self.music.mkdir()
        stats_import._library_cache.clear()
        cache = Path(config.DATA_DIR) / "music_library_cache.json"
        if cache.exists():
            cache.unlink()
        paths = mock.patch.object(config, "get_paths_from_config",
                                  return_value=([self.music], Path("/none"), cache, {self.music: Path("/music")}))
        paths.start()
        self.addCleanup(paths.stop)
        self.conn = stats_db.connect()
        self.addCleanup(self.conn.close)

    def track(self, title="Song", artist="A", path=None, cover_url=None, album=None, album_path=None, album_cover=None, ts=1000):
        track = stats_db.upsert_track(self.conn, title, [artist])
        self.conn.execute("UPDATE tracks SET file_path=?, cover_url=? WHERE id=?", (str(path) if path else None, cover_url, track))
        album_id = stats_db.upsert_album(self.conn, album, artist) if album else None
        if album_id:
            self.conn.execute("UPDATE albums SET file_path=?, cover_url=? WHERE id=?", (str(album_path) if album_path else None, album_cover, album_id))
        stats_db.add_play(self.conn, track, album_id, 100, ts, "live")
        self.conn.commit()
        return track, album_id

    def resolved(self, kind, item):
        found = stats_covers.cover_for(kind, item)
        return Image.open(found).convert("RGB").getpixel((5, 5)) if found else None


class Sources(CoversCase):
    def test_embedded_art_comes_first(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        (song.parent / "cover.jpg").write_bytes(image_bytes((10, 200, 10)))
        track, _ = self.track(path=song, cover_url="http://deezer/x.jpg")
        with mock.patch("core.stats_covers.requests.get") as get:
            pixel = self.resolved("track", track)
        get.assert_not_called()
        self.assertGreater(pixel[0], 150)

    def test_id3_art_is_read(self):
        song = self.music / "A" / "Album" / "01.mp3"
        song.parent.mkdir(parents=True)
        song.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 2000)
        tags = ID3()
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=image_bytes((10, 10, 220))))
        tags.save(song)
        track, _ = self.track(path=song)
        self.assertGreater(self.resolved("track", track)[2], 150)

    def test_other_tag_formats(self):
        art = image_bytes()
        self.assertEqual(stats_covers._embedded({"covr": [art]}), art)
        picture = Picture()
        picture.data = art
        encoded = base64.b64encode(picture.write()).decode()
        self.assertEqual(stats_covers._embedded({"metadata_block_picture": [encoded]}), art)
        self.assertIsNone(stats_covers._embedded({"metadata_block_picture": ["not base64!"]}))
        self.assertIsNone(stats_covers._embedded({}))

    def test_folder_image_in_an_album_folder(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac")
        (song.parent / "Folder.JPG").write_bytes(image_bytes((10, 200, 10)))
        track, _ = self.track(path=song)
        self.assertGreater(self.resolved("track", track)[1], 150)

    def test_folder_image_beside_loose_files_is_not_trusted(self):
        song = flac_file(self.music / "A" / "01.flac")
        (song.parent / "cover.jpg").write_bytes(image_bytes((10, 200, 10)))
        track, _ = self.track(path=song)
        self.assertIsNone(self.resolved("track", track))

    def test_deezer_when_nothing_local(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac")
        track, _ = self.track(path=song, cover_url="http://deezer/x.jpg")
        response = mock.Mock(status_code=200, content=image_bytes((220, 220, 10)))
        with mock.patch("core.stats_covers.requests.get", return_value=response) as get:
            self.assertGreater(self.resolved("track", track)[0], 150)
        self.assertEqual(get.call_args.kwargs["timeout"], 5)

    def test_album_uses_its_own_file_not_a_singles(self):
        single = flac_file(self.music / "A" / "Single" / "01.flac", image_bytes((10, 200, 10)))
        album_file = flac_file(self.music / "A" / "Big" / "05.flac", image_bytes((200, 30, 60)))
        _, album = self.track(path=single, album="Big", album_path=album_file)
        self.assertGreater(self.resolved("album", album)[0], 150)

    def test_album_only_known_from_maloja_goes_to_deezer(self):
        _, album = self.track(album="Old", album_cover="http://deezer/a.jpg")
        response = mock.Mock(status_code=200, content=image_bytes((10, 10, 220)))
        with mock.patch("core.stats_covers.requests.get", return_value=response):
            self.assertGreater(self.resolved("album", album)[2], 150)

    def test_artist_photo_from_their_folder(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        (self.music / "A" / "artist.jpg").write_bytes(image_bytes((10, 200, 10)))
        self.track(path=song, album="Album", album_path=song)
        artist = self.conn.execute("SELECT id FROM artists WHERE name='A'").fetchone()[0]
        self.assertGreater(self.resolved("artist", artist)[1], 150)

    def test_artist_folder_only_counts_when_it_is_named_for_them(self):
        song = flac_file(self.music / "albums" / "A - Album" / "01.flac", image_bytes((200, 30, 60)))
        (self.music / "albums" / "artist.jpg").write_bytes(image_bytes((10, 200, 10)))
        self.track(path=song, album="Album", album_path=song)
        artist = self.conn.execute("SELECT id FROM artists WHERE name='A'").fetchone()[0]
        self.assertGreater(self.resolved("artist", artist)[0], 150)  # their album, not the stray image

    def test_artist_deezer_photo_then_top_album(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        self.track(path=song, album="Album", album_path=song)
        artist = self.conn.execute("SELECT id FROM artists WHERE name='A'").fetchone()[0]
        self.conn.execute("UPDATE artists SET picture_url='http://deezer/p.jpg' WHERE id=?", (artist,))
        self.conn.commit()
        response = mock.Mock(status_code=200, content=image_bytes((10, 10, 220)))
        with mock.patch("core.stats_covers.requests.get", return_value=response):
            self.assertGreater(self.resolved("artist", artist)[2], 150)

    def test_deezer_blank_artist_picture_is_ignored(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        self.track(path=song, album="Album", album_path=song)
        artist = self.conn.execute("SELECT id FROM artists WHERE name='A'").fetchone()[0]
        self.conn.execute("UPDATE artists SET picture_url='https://cdn/images/artist//500x500-0.jpg' WHERE id=?", (artist,))
        self.conn.commit()
        with mock.patch("core.stats_covers.requests.get") as get:
            self.assertGreater(self.resolved("artist", artist)[0], 150)
        get.assert_not_called()


class CacheBehaviour(CoversCase):
    def test_small_and_deduplicated_with_a_color(self):
        art = image_bytes((200, 30, 60), (2000, 1500))
        one = flac_file(self.music / "A" / "Album" / "01.flac", art)
        two = flac_file(self.music / "A" / "Album" / "02.flac", art)
        first, _ = self.track("One", path=one)
        second, _ = self.track("Two", path=two, ts=2000)
        a, b = stats_covers.cover_for("track", first), stats_covers.cover_for("track", second)
        self.assertEqual(a, b)
        self.assertLessEqual(max(Image.open(a).size), 600)
        color = self.conn.execute("SELECT color FROM covers WHERE kind='track'").fetchone()[0]
        self.assertRegex(color, "^#[0-9a-f]{6}$")
        self.assertGreater(int(color[1:3], 16), 150)

    def test_corrupt_art_falls_through(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", b"this is not an image")
        (song.parent / "cover.png").write_bytes(image_bytes((10, 200, 10), fmt="PNG"))
        track, _ = self.track(path=song)
        self.assertGreater(self.resolved("track", track)[1], 150)

    def test_unreadable_audio_file_is_no_art(self):
        song = self.music / "A" / "Album" / "01.flac"
        song.parent.mkdir(parents=True)
        song.write_bytes(b"garbage")
        track, _ = self.track(path=song)
        self.assertIsNone(self.resolved("track", track))

    def test_no_art_waits_a_week(self):
        track, _ = self.track()
        self.assertIsNone(stats_covers.cover_for("track", track))
        row = self.conn.execute("SELECT retry_at FROM covers").fetchone()
        self.assertGreater(row[0], time.time() + 6 * 86400)

    def test_network_error_waits_an_hour(self):
        track, _ = self.track(cover_url="http://deezer/x.jpg")
        with mock.patch("core.stats_covers.requests.get", side_effect=OSError("down")):
            self.assertIsNone(stats_covers.cover_for("track", track))
        wait = self.conn.execute("SELECT retry_at FROM covers").fetchone()[0] - time.time()
        self.assertLess(wait, 2 * 3600)
        self.assertGreater(wait, 1800)

    def test_deleted_cache_file_is_found_again(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes())
        track, _ = self.track(path=song)
        stats_covers.cover_for("track", track).unlink()
        self.assertIsNotNone(stats_covers.cover_for("track", track))

    def test_unknown_item_and_kind(self):
        self.assertIsNone(stats_covers.cover_for("track", 99999))
        self.assertIsNone(stats_covers.cover_for("label", 1))

    def test_cache_survives_start_clean_renumbering(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes())
        track, _ = self.track(path=song)
        stats_covers.cover_for("track", track)
        key = self.conn.execute("SELECT key FROM tracks WHERE id=?", (track,)).fetchone()[0]
        self.conn.execute("DELETE FROM plays")
        self.conn.execute("DELETE FROM track_artists")
        self.conn.execute("DELETE FROM tracks")
        self.conn.execute("INSERT INTO tracks(id, key, title) VALUES (77, ?, 'Song')", (key,))
        self.conn.commit()
        with mock.patch.object(stats_covers, "_embedded_art") as read:
            self.assertIsNotNone(stats_covers.cover_for("track", 77))
        read.assert_not_called()

    def test_batch_most_played_first(self):
        self.track("Rare", path=flac_file(self.music / "A" / "R" / "1.flac", image_bytes()))
        popular = flac_file(self.music / "A" / "P" / "1.flac", image_bytes())
        for ts in (5000, 6000, 7000):
            self.track("Popular", path=popular, ts=ts)
        self.assertEqual(stats_covers.resolve_batch(1), 1 + 1)  # one track, one artist
        keys = [r[0] for r in self.conn.execute("SELECT item_key FROM covers WHERE kind='track'")]
        self.assertEqual(keys, [stats_db.track_key(["A"], "Popular")])

    def test_batch_leaves_finished_items(self):
        self.track(path=flac_file(self.music / "A" / "R" / "1.flac", image_bytes()))
        self.assertGreater(stats_covers.resolve_batch(10), 0)
        self.assertEqual(stats_covers.resolve_batch(10), 0)


class ApiRows(CoversCase):
    def test_rows_point_at_the_cover_route_with_a_color(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        track, album = self.track(path=song, album="Album", album_path=song)
        stats_covers.cover_for("track", track)
        data = stats_queries.overview("all", "", "UTC")
        self.assertTrue(data["top"]["tracks"][0]["image"].startswith(f"/stats/cover/track/{track}"))
        self.assertRegex(data["top"]["tracks"][0]["color"], "^#")
        self.assertEqual(data["top"]["albums"][0]["image"], f"/stats/cover/album/{album}")

    def test_known_missing_art_gives_no_image(self):
        track, _ = self.track()
        stats_covers.cover_for("track", track)
        self.assertEqual(stats_queries.overview("all", "", "UTC")["top"]["tracks"][0]["image"], "")


class ArtistLookups(CoversCase):
    def api(self, artists):
        def call(path, params=None):
            if path == "/search/artist":
                return {"data": artists}
            return {"data": []}
        return call

    def test_exact_name_gets_the_big_photo(self):
        self.track()
        data = [{"id": 9, "name": "A", "picture_big": "http://img/a.jpg"}]
        with mock.patch("core.deezer._public_api", self.api(data)):
            stats_enrich.enrich_batch(5)
        row = self.conn.execute("SELECT deezer_id, picture_url FROM artists WHERE name='A'").fetchone()
        self.assertEqual(tuple(row), ("9", "http://img/a.jpg"))

    def test_a_similar_name_is_not_taken(self):
        self.track(artist="Ye")
        data = [{"id": 9, "name": "Yeat", "picture_big": "http://img/a.jpg"}]
        with mock.patch("core.deezer._public_api", self.api(data)):
            stats_enrich.enrich_batch(5)
        self.assertIsNone(self.conn.execute("SELECT picture_url FROM artists").fetchone()[0])

    def test_looked_up_once(self):
        self.track()
        calls = []
        api = self.api([])
        with mock.patch("core.deezer._public_api", lambda p, params=None: (calls.append(p), api(p, params))[1]):
            stats_enrich.enrich_batch(5)
            before = calls.count("/search/artist")
            stats_enrich.enrich_batch(5)
        self.assertEqual(before, 1)
        self.assertEqual(calls.count("/search/artist"), 1)

    def test_new_photo_replaces_album_stand_in(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        self.track(path=song, album="Album", album_path=song)
        artist = self.conn.execute("SELECT id FROM artists WHERE name='A'").fetchone()[0]
        self.assertIsNotNone(stats_covers.cover_for("artist", artist))
        data = [{"id": 9, "name": "A", "picture_big": "http://img/a.jpg"}]
        with mock.patch("core.deezer._public_api", self.api(data)):
            stats_enrich.enrich_batch(5)
        response = mock.Mock(status_code=200, content=image_bytes((10, 10, 220)))
        with mock.patch("core.stats_covers.requests.get", return_value=response):
            self.assertGreater(self.resolved("artist", artist)[2], 150)

    def test_deezer_cover_retries_a_track_that_had_none(self):
        track, _ = self.track()
        self.assertIsNone(stats_covers.cover_for("track", track))
        result = {"id": 11, "title": "Song", "duration": 100, "artist": {"id": 3, "name": "A"},
                  "album": {"id": 22, "title": "Album", "cover_big": "http://img/big.jpg", "cover_medium": "http://img/m.jpg"}}

        def api(path, params=None):
            return {"data": [result]} if path == "/search/track" else {"data": [], "genres": {"data": []}}

        with mock.patch("core.deezer._public_api", api):
            stats_enrich.enrich_batch(5)
        self.assertEqual(self.conn.execute("SELECT cover_url FROM tracks").fetchone()[0], "http://img/big.jpg")
        response = mock.Mock(status_code=200, content=image_bytes((10, 10, 220)))
        with mock.patch("core.stats_covers.requests.get", return_value=response):
            self.assertIsNotNone(stats_covers.cover_for("track", track))


class Route(CoversCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.app.test_client()

    def test_serves_a_cached_jpeg(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes())
        track, _ = self.track(path=song)
        response = self.client.get(f"/stats/cover/track/{track}")
        self.assertEqual((response.status_code, response.mimetype), (200, "image/jpeg"))
        self.assertIn("no-cache", response.headers["Cache-Control"])
        response.close()

    def test_missing_art_404_not_stored_by_the_browser(self):
        track, _ = self.track()
        response = self.client.get(f"/stats/cover/track/{track}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_bad_requests(self):
        self.assertEqual(self.client.get("/stats/cover/label/1").status_code, 404)
        self.assertEqual(self.client.get(f"/stats/cover/track/{10 ** 30}").status_code, 404)

    def test_sign_in_required(self):
        with mock.patch.dict(os.environ):
            del os.environ["DISABLE_AUTH"]
            self.assertEqual(self.client.get("/stats/cover/track/1").status_code, 401)


if __name__ == "__main__":
    unittest.main()
