import time
import unittest
from unittest import mock

from core import stats_db, stats_enrich
from core.stats_enrich import deezer_match, enrich_batch
from tests.test_stats_db import reset


def item(title="Song", artist="A", track_id=11, album_id=22, duration=210):
    return {
        "id": track_id, "title": title, "duration": duration,
        "artist": {"id": 33, "name": artist, "picture_medium": "http://img/artist.jpg"},
        "album": {"id": album_id, "title": "Album", "cover_medium": "http://img/cover.jpg"},
    }


def fake_api(tracks=None, genres=("Rap/Hip Hop",)):
    def call(path, params=None):
        if path == "/search/track":
            return {"data": tracks if tracks is not None else [item()]}
        if path.startswith("/album/"):
            return {"genres": {"data": [{"name": g} for g in genres]}}
        raise AssertionError(path)
    return call


class MatchRule(unittest.TestCase):
    def test_match_rule(self):
        self.assertTrue(deezer_match("Money Trees", ["Kendrick Lamar"], {"title": "Money Trees", "artist": {"name": "Kendrick Lamar"}}))
        self.assertFalse(deezer_match("Money Trees", ["Someone"], {"title": "Money Trees", "artist": {"name": "Kendrick Lamar"}}))
        self.assertFalse(deezer_match("Song", ["A"], {"title": "Song (Remix)", "artist": {"name": "A"}}))  # version guard

    def test_accents_case_and_features(self):
        self.assertTrue(deezer_match("Déjà Vu", ["Beyoncé"], {"title": "DEJA VU (feat. Jay-Z)", "artist": {"name": "beyonce"}}))

    def test_containment_counts(self):
        self.assertTrue(deezer_match("Song", ["A Band"], {"title": "Song Part", "artist": {"name": "A Band"}}))

    def test_title_alone_is_not_enough(self):
        self.assertFalse(deezer_match("Song", ["A"], {"title": "Unrelated", "artist": {"name": "A"}}))

    def test_any_credited_artist_counts(self):
        self.assertTrue(deezer_match("Song", ["A", "B"], {"title": "Song", "artist": {"name": "B"}}))

    def test_same_marker_on_both_sides_matches(self):
        self.assertTrue(deezer_match("Song (Live)", ["A"], {"title": "Song - Live", "artist": {"name": "A"}}))

    def test_malformed_item_does_not_match(self):
        self.assertFalse(deezer_match("Song", ["A"], {"title": None, "artist": None}))


class Batches(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = stats_db.connect()

    def tearDown(self):
        self.conn.close()

    def track(self, title="Song", artists=("A",), plays=1, **fields):
        track = stats_db.upsert_track(self.conn, title, list(artists), **fields)
        for n in range(plays):
            stats_db.add_play(self.conn, track, None, None, 1000 + track * 1000 + n, "live")
        self.conn.commit()
        return track

    def row(self, track):
        self.conn.rollback()
        return self.conn.execute("SELECT * FROM tracks WHERE id=?", (track,)).fetchone()

    def run_batch(self, api=None, limit=10):
        with mock.patch("core.deezer._public_api", api or fake_api()):
            return enrich_batch(limit)

    def test_fills_missing_fields(self):
        track = self.track()
        self.assertEqual(self.run_batch(), 1)
        row = self.row(track)
        self.assertEqual((row["deezer_track_id"], row["deezer_album_id"]), ("11", "22"))
        self.assertEqual((row["duration_sec"], row["duration_source"]), (210, "deezer"))
        self.assertEqual((row["genre"], row["genre_source"]), ("Rap/Hip Hop", "deezer"))
        self.assertEqual(row["cover_url"], "http://img/cover.jpg")

    def test_search_uses_plain_words(self):
        # Deezer's API returned nothing at all for artist:"…" track:"…" queries.
        self.track("Song (feat. B)", ("A", "B"))
        asked = []
        api = fake_api()
        self.run_batch(lambda path, params=None: (asked.append(params), api(path, params))[1])
        self.assertEqual(asked[0]["q"], "A Song")

    def test_known_values_stay(self):
        track = self.track(duration=99, duration_source="navidrome", genre="Pop", genre_source="navidrome")
        self.run_batch()
        row = self.row(track)
        self.assertEqual((row["duration_sec"], row["genre"]), (99, "Pop"))
        self.assertEqual(row["deezer_track_id"], "11")

    def test_known_genre_needs_no_album_lookup(self):
        self.track(genre="Pop", genre_source="navidrome")
        calls = []
        api = fake_api()
        self.run_batch(lambda path, params=None: (calls.append(path), api(path, params))[1])
        self.assertEqual(calls, ["/search/track"])

    def test_most_played_first(self):
        self.track("Rare", plays=1)
        popular = self.track("Song", plays=5)
        self.assertEqual(self.run_batch(limit=1), 1)
        self.assertEqual(self.row(popular)["deezer_track_id"], "11")

    def test_no_match_retries_after_delay(self):
        track = self.track("Nothing like it")
        self.run_batch()
        row = self.row(track)
        self.assertIsNone(row["deezer_track_id"])
        self.assertGreater(row["lookup_at"], time.time() + 6 * 86400)
        self.assertEqual(self.run_batch(), 0)

    def test_network_error_retries_sooner(self):
        track = self.track()
        def fail(path, params=None):
            raise OSError("no network")
        self.assertEqual(self.run_batch(fail), 1)
        wait = self.row(track)["lookup_at"] - time.time()
        self.assertGreater(wait, 1800)
        self.assertLess(wait, 2 * 3600)
        self.assertEqual(self.run_batch(), 0)

    def test_due_retry_runs_again(self):
        track = self.track()
        self.conn.execute("UPDATE tracks SET lookup_at=? WHERE id=?", (int(time.time()) - 5, track))
        self.conn.commit()
        self.assertEqual(self.run_batch(), 1)

    def test_complete_track_is_left_alone(self):
        self.track()
        self.run_batch()
        self.assertEqual(self.run_batch(), 0)

    def test_album_without_genre_is_not_retried_at_once(self):
        track = self.track()
        self.run_batch(fake_api(genres=()))
        self.assertEqual(self.row(track)["deezer_track_id"], "11")
        self.assertEqual(self.run_batch(fake_api(genres=())), 0)

    def test_artist_picture_filled(self):
        self.track()
        self.run_batch()
        self.conn.rollback()
        artist = self.conn.execute("SELECT deezer_id, picture_url FROM artists WHERE name='A'").fetchone()
        self.assertEqual((artist["deezer_id"], artist["picture_url"]), ("33", "http://img/artist.jpg"))

    def test_background_batch_runs_one_at_a_time(self):
        self.assertTrue(stats_enrich._busy.acquire(blocking=False))
        try:
            with mock.patch.object(stats_enrich, "enrich_batch") as batch:
                self.assertFalse(stats_enrich.start_background_batch())
                batch.assert_not_called()
        finally:
            stats_enrich._busy.release()

    def test_background_batch_skips_during_import(self):
        from core import stats_import
        self.assertTrue(stats_import._running.acquire(blocking=False))
        try:
            self.assertFalse(stats_enrich.start_background_batch())
        finally:
            stats_import._running.release()


if __name__ == "__main__":
    unittest.main()
