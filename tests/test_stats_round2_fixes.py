"""Findings of the review of covers, audio and recaps, each pinned by its case."""
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from core import stats_covers, stats_db, stats_queries
from core.stats_import import run_import
from core.stats_queries import recap
from core.stats_story import personality
from tests.fixtures import make_navidrome
from tests.test_stats_covers import CoversCase, flac_file, image_bytes
from tests.test_stats_import import ImportCase

UTC = "UTC"


def at(month, day, hour=12, year=2026):
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp())


class CoverUrls(CoversCase):
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

    def test_row_url_changes_with_the_image(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes((200, 30, 60)))
        track, _ = self.track(path=song)
        stats_covers.cover_for("nd1", "track", track)
        first = stats_queries.overview("nd1", "all", "", UTC)["top"]["tracks"][0]["image"]
        self.assertIn("?v=", first)
        self.conn.execute("DELETE FROM covers")
        self.conn.commit()
        flac_file(song, image_bytes((10, 200, 10)))
        stats_covers.cover_for("nd1", "track", track)
        self.assertNotEqual(first, stats_queries.overview("nd1", "all", "", UTC)["top"]["tracks"][0]["image"])

    def test_versioned_url_may_be_kept_but_only_privately(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes())
        track, _ = self.track(path=song)
        stats_covers.cover_for("nd1", "track", track)
        url = stats_queries.overview("nd1", "all", "", UTC)["top"]["tracks"][0]["image"]
        response = self.client.get(url)
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertIn("max-age", response.headers["Cache-Control"])
        self.assertNotIn("public", response.headers["Cache-Control"])
        response.close()

    def test_plain_url_is_asked_again_each_time(self):
        song = flac_file(self.music / "A" / "Album" / "01.flac", image_bytes())
        track, _ = self.track(path=song)
        response = self.client.get(f"/stats/cover/track/{track}")
        self.assertIn("no-cache", response.headers["Cache-Control"])
        self.assertNotIn("public", response.headers["Cache-Control"])
        response.close()

    def test_only_audio_files_are_served(self):
        page = self.music / "page.html"
        page.write_text("<script>alert(1)</script>")
        track, _ = self.track(path=page)
        self.assertEqual(self.client.get(f"/stats/audio/{track}").status_code, 404)


class StuckCovers(CoversCase):
    def source(self, kind="album"):
        return self.conn.execute("SELECT source FROM covers WHERE kind = ?", (kind,)).fetchone()[0]

    def test_the_real_source_is_recorded(self):
        embedded = flac_file(self.music / "A" / "E" / "1.flac", image_bytes())
        track, _ = self.track("One", path=embedded)
        stats_covers.cover_for("nd1", "track", track)
        self.assertEqual(self.source("track"), "embedded")
        self.conn.execute("DELETE FROM covers")
        self.conn.commit()
        self.conn.execute("UPDATE tracks SET file_path = NULL, cover_url = 'http://d/x.jpg' WHERE id = ?", (track,))
        self.conn.commit()
        with mock.patch("core.stats_covers.requests.get", return_value=mock.Mock(status_code=200, content=image_bytes())):
            stats_covers.cover_for("nd1", "track", track)
        self.assertEqual(self.source("track"), "deezer")

    def test_album_gets_another_look_when_a_track_gains_a_cover(self):
        track, album = self.track(album="Alb")
        self.assertIsNone(stats_covers.cover_for("nd1", "album", album))
        result = {"id": 11, "title": "Song", "duration": 100, "artist": {"id": 3, "name": "A"},
                  "album": {"id": 22, "title": "Alb", "cover_big": "http://img/big.jpg"}}

        def api(path, params=None):
            return {"data": [result]} if path == "/search/track" else {"data": []}

        from core import stats_enrich
        with mock.patch("core.deezer._public_api", api):
            stats_enrich.enrich_batch("nd1", 5)
        with mock.patch("core.stats_covers.requests.get", return_value=mock.Mock(status_code=200, content=image_bytes())):
            self.assertIsNotNone(stats_covers.cover_for("nd1", "album", album))


class MergeRefreshesCovers(ImportCase):
    def test_merge_gives_gaps_and_deezer_covers_another_look(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One", "album": "Alb"}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        track_key = conn.execute("SELECT key FROM tracks").fetchone()[0]
        album_key = conn.execute("SELECT key FROM albums").fetchone()[0]
        conn.executemany("INSERT INTO covers(kind, item_key, file, source, checked_at, retry_at) VALUES (?, ?, ?, ?, 1, ?)", [
            ("album", album_key, None, None, 9999999999),
            ("track", track_key, "x.jpg", "deezer", None),
        ])
        conn.commit()
        conn.close()
        with mock.patch("core.stats_files.PurePosixPath", wraps=__import__("pathlib").PurePosixPath):
            with mock.patch("core.config.get_paths_from_config", return_value=([Path("/m")], Path("/n"), Path("/none.json"), {Path("/m"): Path("/music")})):
                run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM covers").fetchone()[0], 0)
        conn.close()

    def test_merge_keeps_art_from_your_files(self):
        make_navidrome(self.nav, [{"ts": 1000, "title": "One", "album": "Alb"}])
        run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        key = conn.execute("SELECT key FROM tracks").fetchone()[0]
        conn.execute("INSERT INTO covers(kind, item_key, file, source, checked_at) VALUES ('track', ?, 'x.jpg', 'embedded', 1)", (key,))
        conn.commit()
        conn.close()
        with mock.patch("core.config.get_paths_from_config", return_value=([Path("/m")], Path("/n"), Path("/none.json"), {Path("/m"): Path("/music")})):
            run_import("nd1", "merge")
        conn = stats_db.connect("nd1")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM covers").fetchone()[0], 1)
        conn.close()


class TrueLines(unittest.TestCase):
    def setUp(self):
        from tests.test_stats_db import reset
        reset()
        self.conn = stats_db.connect("nd1")
        self.addCleanup(self.conn.close)

    def play(self, ts, title="Song", artists=("A",), album="Album", duration=200):
        track = stats_db.upsert_track(self.conn, title, list(artists))
        stats_db.add_play(self.conn, track, stats_db.upsert_album(self.conn, album, artists[0]) if album else None, duration, ts, "live")

    def story(self, key="2026-10", kind="month"):
        self.conn.commit()
        return recap("nd1", kind, key, UTC)["story"]

    def test_mostly_needs_a_real_majority(self):
        for i in range(12):
            self.play(at(10, 5, 20) + i * 700, title=f"T{i}", artists=(f"Artist {i % 6}",), duration=180)
        binge = self.story()["binge"]
        self.assertTrue(binge)
        self.assertEqual(binge["top_artist"], "")

    def test_comeback_needs_a_real_past(self):
        self.play(at(8, 1), title="Once", artists=("Barely Known",))
        for i in range(9):
            self.play(at(9, 2) + i * 300, title=f"F{i}", artists=("Other",))
        for i in range(7):
            self.play(at(10, 3) + i * 300, title="Once", artists=("Barely Known",))
        self.assertIsNone(self.story()["comeback"])

    def test_comeback_with_a_real_past(self):
        for i in range(5):
            self.play(at(8, 1) + i * 300, title="Old", artists=("Favorite",))
        self.play(at(9, 2), title="F", artists=("Other",))
        for i in range(7):
            self.play(at(10, 3) + i * 300, title="Old", artists=("Favorite",))
        self.assertEqual(self.story()["comeback"]["name"], "Favorite")

    def test_short_history_makes_nobody_new_or_an_explorer(self):
        for i in range(30):
            self.play(at(9, 2) + i * 300, title=f"F{i}", artists=("First",))
        for i in range(30):
            self.play(at(10, 2) + i * 300, title=f"N{i}", artists=(f"Newcomer {i}",))
        story = self.story()
        self.assertFalse(story["established"])
        self.assertNotIn("new_artists", [s["type"] for s in story["slides"]])
        self.assertNotEqual(story["personality"]["name"], "Explorer")

    def test_long_history_can_say_new(self):
        for i in range(30):
            self.play(at(5, 2) + i * 300, title=f"F{i}", artists=("First",))
        for i in range(30):
            self.play(at(10, 2) + i * 300, title=f"N{i}", artists=(f"Newcomer {i}",))
        story = self.story()
        self.assertTrue(story["established"])
        self.assertIn("new_artists", [s["type"] for s in story["slides"]])

    def test_partial_previous_period_is_not_compared(self):
        for i in range(10):
            self.play(at(9, 20) + i * 300, title="R", artists=("Riser",))
        for i in range(30):
            self.play(at(10, 2) + i * 300, title="R", artists=("Riser",))
        story = self.story()
        self.assertFalse(story["comparable"])
        self.assertIsNone(story["movers"])

    def test_whole_previous_period_is_compared(self):
        self.play(at(8, 31), title="Before")
        for i in range(10):
            self.play(at(9, 20) + i * 300, title="R", artists=("Riser",))
        for i in range(30):
            self.play(at(10, 2) + i * 300, title="R", artists=("Riser",))
        story = self.story()
        self.assertTrue(story["comparable"])
        self.assertEqual(story["movers"]["rise"]["name"], "Riser")

    def test_units_match_their_number(self):
        self.play(at(10, 1), duration=15 * 3600)
        items = {i["unit"]: i["value"] for i in self.story()["comparisons"]}
        self.assertEqual(items, {"films": 7, "flight from Paris to Tokyo": 1})
        self.play(at(10, 2), title="L", duration=10 * 3600)
        self.assertEqual({i["unit"]: i["value"] for i in self.story()["comparisons"]}["day of non-stop music"], 1)

    def test_track_countdown_needs_real_repeats(self):
        for i in range(4):
            self.play(at(10, 2) + i * 300, title=f"T{i}", artists=(f"X{i}",))
        self.assertNotIn("track_countdown", [s["type"] for s in self.story()["slides"]])

    def test_placeholder_artist_is_never_new_or_a_superfan_subject(self):
        for i in range(25):
            self.play(at(5, 1) + i * 300, title=f"F{i}", artists=("First",))
        for i in range(96):
            self.play(at(10, 2) + i * 300, title=f"U{i}", artists=("[Unknown Artist]",))
        self.play(at(10, 20), title="R", artists=("Real",))
        data = (self.conn.commit(), recap("nd1", "month", "2026-10", UTC))[1]
        self.assertNotIn("[Unknown Artist]", [a["name"] for a in data["new_artists"]])
        self.assertNotEqual((data["discovery"] or {}).get("name"), "[Unknown Artist]")
        self.assertNotEqual(data["story"]["personality"]["name"], "Superfan")

    def test_few_plays_read_properly(self):
        base = dict(top_track_share=0, top_artist_share=0, night_share=0, morning_share=0, weekend_share=0, new_artist_share=0,
                    has_previous=False, genre_count=0, top_genre_share=1, genre_pct=100, top_albums_share=0)
        self.assertEqual(personality({**base, "plays": 1})["reason"], "Only 1 play. Barely enough to judge.")
        self.assertEqual(personality({**base, "plays": 12})["reason"], "Only 12 plays. Barely enough to judge.")


class WeakerSlidesGetAChance(unittest.TestCase):
    def test_rotation_is_stable_and_reaches_them(self):
        from core.stats_story import rotation_bonus
        self.assertEqual(rotation_bonus("2026-10", "clock"), rotation_bonus("2026-10", "clock"))
        values = {rotation_bonus(f"2026-{m:02d}", "clock") for m in range(1, 13)}
        self.assertGreater(len(values), 3)
        self.assertTrue(all(0 <= value <= 1 for value in values))


if __name__ == "__main__":
    unittest.main()
