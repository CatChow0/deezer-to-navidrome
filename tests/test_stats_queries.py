import time
import unittest
from datetime import datetime, timezone

from core import stats_db, stats_queries as q
from core.stats_genres import genre_group
from core.stats_queries import BadPeriod, entity, overview, period_bounds, previous_key, recap, recap_index, search_plays
from tests.test_stats_db import reset

UTC = "UTC"


def stamp(year, month, day, hour=12, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp())


class Genres(unittest.TestCase):
    def test_genre_groups(self):
        for raw in ("Rap", "Hip Hop", "Rap/Hip Hop", "French Rap"):
            self.assertEqual(genre_group(raw), "Rap & Hip-Hop")
        for raw in ("Films/Games", "Film Scores", "Games"):
            self.assertEqual(genre_group(raw), "Film & Game Music")
        self.assertEqual(genre_group("Antilles"), "Antilles")   # unknown names stay as tagged
        for junk in ("125", "<unknown>", "", None):
            self.assertIsNone(genre_group(junk))


class Periods(unittest.TestCase):
    def test_month_bounds_in_timezone(self):
        self.assertEqual(period_bounds("month", "2026-10", "Europe/Paris"), (1790805600, 1793487600))  # includes DST end: 31 days + 1 h

    def test_all_has_no_bounds(self):
        self.assertEqual(period_bounds("all", "", UTC), (None, None))

    def test_year_and_week_bounds(self):
        self.assertEqual(period_bounds("year", "2026", UTC), (stamp(2026, 1, 1, 0), stamp(2027, 1, 1, 0)))
        self.assertEqual(period_bounds("week", "2026-W01", UTC), (stamp(2025, 12, 29, 0), stamp(2026, 1, 5, 0)))

    def test_bad_input_raises(self):
        for period, key, tz in (
            ("month", "Mars/Olympus", UTC), ("month", "2026-13", UTC), ("week", "2026-W60", UTC),
            ("week", "2025-W53", UTC), ("day", "2026-10", UTC), ("year", "abcd", UTC), ("month", "2026-10", "Mars/Olympus"),
            ("month", "2026-10", "../../etc/passwd"), ("month", "2026-10", ""), ("all", "x", UTC),
        ):
            with self.assertRaises(BadPeriod, msg=(period, key, tz)):
                period_bounds(period, key, tz)

    def test_iso_week_at_year_edge(self):
        self.assertEqual(previous_key("week", "2027-W01"), "2026-W53")

    def test_previous_key_january(self):
        self.assertEqual(previous_key("month", "2026-01"), "2025-12")
        self.assertEqual(previous_key("year", "2026"), "2025")
        self.assertIsNone(previous_key("all", ""))


class WithPlays(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = stats_db.connect()

    def tearDown(self):
        self.conn.close()

    def play(self, ts, title="Song", artists=("A",), album="Album", duration=200, track_duration=None, genre=None):
        track = stats_db.upsert_track(self.conn, title, list(artists), duration=track_duration, duration_source="test",
                                      genre=genre, genre_source="test")
        album_id = stats_db.upsert_album(self.conn, album, artists[0])
        stats_db.add_play(self.conn, track, album_id, duration, ts, "live")
        self.conn.commit()
        return track

    def test_play_at_month_boundary_in_one_period_only(self):
        self.play(stamp(2026, 11, 1, 0, 0))
        self.assertEqual(overview("month", "2026-10", UTC)["totals"]["plays"], 0)
        self.assertEqual(overview("month", "2026-11", UTC)["totals"]["plays"], 1)
        # 1 Nov 00:00 UTC is still 31 Oct in New York.
        self.assertEqual(overview("month", "2026-10", "America/New_York")["totals"]["plays"], 1)

    def test_seconds_use_play_then_track_length(self):
        self.play(stamp(2026, 10, 1), title="Known", duration=200)
        self.play(stamp(2026, 10, 2), title="Fallback", duration=None, track_duration=100)
        self.play(stamp(2026, 10, 3), title="Unknown", duration=None)
        data = overview("month", "2026-10", UTC)
        self.assertEqual(data["totals"]["seconds"], 300)
        self.assertEqual(data["coverage"]["length_pct"], 67)

    def test_track_on_two_albums_counts_per_album(self):
        self.play(stamp(2026, 10, 1), album="First")
        self.play(stamp(2026, 10, 2), album="Second")
        self.play(stamp(2026, 10, 3), album="Second")
        data = overview("month", "2026-10", UTC)
        self.assertEqual([(a["title"], a["plays"]) for a in data["top"]["albums"]], [("Second", 2), ("First", 1)])
        self.assertEqual(data["top"]["tracks"][0]["plays"], 3)

    def test_featured_artist_counted_for_both_play_once_in_total(self):
        self.play(stamp(2026, 10, 1), artists=("A", "B"))
        data = overview("month", "2026-10", UTC)
        self.assertEqual(data["totals"]["plays"], 1)
        self.assertEqual({a["name"]: a["plays"] for a in data["top"]["artists"]}, {"A": 1, "B": 1})

    def test_unique_artists_not_capped(self):
        for i in range(15):
            self.play(stamp(2026, 10, 1) + i * 300, title=f"S{i}", artists=(f"Artist {i}",))
        data = overview("month", "2026-10", UTC)
        self.assertEqual(data["totals"]["artists"], 15)
        self.assertEqual(len(data["top"]["artists"]), 10)

    def test_new_artist_means_first_ever_play(self):
        self.play(stamp(2026, 1, 5), title="Old", artists=("Old Friend",))
        for i in range(12):
            self.play(stamp(2026, 9, 1) + i * 300, title=f"Fill {i}", artists=(f"Filler {i}",))
        self.play(stamp(2026, 10, 1), title="Again", artists=("Old Friend",))
        self.play(stamp(2026, 10, 2), title="Fresh", artists=("Newcomer",))
        names = [a["name"] for a in recap("month", "2026-10", UTC)["new_artists"]]
        self.assertEqual(names, ["Newcomer"])
        self.assertEqual(recap("month", "2026-10", UTC)["discovery"]["name"], "Newcomer")

    def test_comparison_uses_whole_previous_period(self):
        for i in range(60):
            for n in range(60 - i):
                self.play(stamp(2026, 9, 1 + (n % 28), 1 + (i % 22)) + n, title=f"S{i}", artists=(f"Artist {i}",))
        self.play(stamp(2026, 10, 1), title="S55", artists=("Artist 55",))
        data = recap("month", "2026-10", UTC)
        self.assertTrue(data["has_previous"])
        self.assertEqual(data["top"]["artists"][0]["previous_plays"], 5)
        self.assertEqual(data["top"]["tracks"][0]["previous_plays"], 5)
        self.assertEqual(data["previous"]["key"], "2026-09")

    def test_entity_absent_from_previous_is_null(self):
        self.play(stamp(2026, 9, 1), title="Old", artists=("B",))
        self.play(stamp(2026, 10, 1), title="New", artists=("A",))
        self.assertIsNone(recap("month", "2026-10", UTC)["top"]["artists"][0]["previous_plays"])

    def test_first_period_has_no_previous(self):
        self.play(stamp(2026, 2, 16))
        data = recap("month", "2026-02", UTC)
        self.assertFalse(data["has_previous"])
        self.assertEqual(data["new_artists"], [])
        self.assertIsNone(data["discovery"])
        self.assertTrue(data["partial"])

    def test_first_period_starting_on_the_first_is_not_partial(self):
        self.play(stamp(2026, 2, 1))
        self.assertFalse(recap("month", "2026-02", UTC)["partial"])

    def test_gap_in_history_does_not_hide_comparison(self):
        self.play(stamp(2026, 1, 5))
        self.play(stamp(2026, 3, 5))
        data = recap("month", "2026-03", UTC)
        self.assertTrue(data["has_previous"])
        self.assertEqual(data["previous"]["totals"]["plays"], 0)

    def test_current_month_is_so_far_not_latest_complete(self):
        now = datetime.fromtimestamp(time.time(), timezone.utc)
        current = f"{now.year}-{now.month:02d}"
        self.play(int(now.timestamp()) - 1)
        self.play(stamp(2020, 3, 10))
        index = recap_index(UTC)
        self.assertEqual(index["months"][0]["key"], current)
        self.assertTrue(index["months"][0]["so_far"])
        self.assertEqual(index["latest_complete"], "2020-03")
        self.assertTrue(recap("month", current, UTC)["so_far"])
        self.assertEqual([y["key"] for y in index["years"]][-1], "2020")

    def test_recap_index_empty(self):
        self.assertEqual(recap_index(UTC), {"months": [], "years": [], "latest_complete": None})

    def test_genres_group_and_share_sums_to_one(self):
        self.play(stamp(2026, 10, 1), title="R1", genre="Rap", duration=100)
        self.play(stamp(2026, 10, 2), title="R2", genre="Hip Hop", duration=100)
        self.play(stamp(2026, 10, 3), title="P1", genre="Pop", duration=200)
        self.play(stamp(2026, 10, 4), title="None", duration=100)
        data = overview("month", "2026-10", UTC)
        self.assertEqual([(g["name"], g["plays"], g["seconds"]) for g in data["genres"]], [("Rap & Hip-Hop", 2, 200), ("Pop", 1, 200)])
        self.assertAlmostEqual(sum(g["share"] for g in data["genres"]), 1.0)
        self.assertEqual(data["coverage"]["genre_pct"], 75)

    def test_heatmap_uses_timezone(self):
        self.play(stamp(2026, 10, 5, 22))  # Monday 22:00 UTC, Tuesday 07:00 in Tokyo
        utc = overview("month", "2026-10", UTC)["habits"]["heatmap"]
        tokyo = overview("month", "2026-10", "Asia/Tokyo")["habits"]["heatmap"]
        self.assertEqual(utc[0][22], 1)
        self.assertEqual(tokyo[1][7], 1)

    def test_longest_streak_across_month_end(self):
        for day in (30, 31):
            self.play(stamp(2026, 10, day), title=f"O{day}")
        for day in (1, 2):
            self.play(stamp(2026, 11, day), title=f"N{day}")
        self.play(stamp(2026, 11, 20), title="Later")
        habits = overview("all", "", UTC)["habits"]
        self.assertEqual(habits["longest_streak"], {"days": 4, "start": "2026-10-30", "end": "2026-11-02"})

    def test_busiest_day(self):
        self.play(stamp(2026, 10, 1))
        self.play(stamp(2026, 10, 2, 10))
        self.play(stamp(2026, 10, 2, 11))
        self.assertEqual(overview("all", "", UTC)["habits"]["busiest_day"], {"date": "2026-10-02", "plays": 2})

    def test_overview_empty_period(self):
        data = overview("month", "2026-10", UTC)
        self.assertEqual(data["totals"], {"plays": 0, "seconds": 0, "artists": 0, "albums": 0, "tracks": 0})
        self.assertEqual(data["top"], {"artists": [], "albums": [], "tracks": []})
        self.assertEqual(data["genres"], [])
        self.assertEqual(data["habits"]["longest_streak"]["days"], 0)
        self.assertEqual(len(data["habits"]["heatmap"]), 7)
        self.assertEqual(data["coverage"], {"length_pct": 100, "genre_pct": 100})

    def test_recap_and_overview_agree(self):
        self.play(stamp(2026, 10, 1), title="A1", artists=("X", "Y"), genre="Rap")
        self.play(stamp(2026, 10, 2), title="A2", artists=("X",), duration=None)
        base, story = overview("month", "2026-10", UTC), recap("month", "2026-10", UTC)
        self.assertEqual(base["totals"], story["totals"])
        strip = lambda rows: [{k: v for k, v in row.items() if k != "previous_plays"} for row in rows]
        for kind in ("artists", "albums", "tracks"):
            self.assertEqual(base["top"][kind], strip(story["top"][kind]))
        self.assertEqual(base["genres"], story["genres"])

    def test_label(self):
        self.play(stamp(2026, 10, 1))
        self.assertEqual(overview("month", "2026-10", UTC)["label"], "October 2026")
        self.assertEqual(overview("year", "2026", UTC)["label"], "2026")
        self.assertEqual(overview("all", "", UTC)["label"], "All time")
        self.assertEqual(overview("week", "2026-W43", UTC)["label"], "Week 43, 2026")

    def test_search_plays_filters_and_pages(self):
        self.play(stamp(2026, 10, 1), title="Déjà Vu", artists=("Beyoncé",), album="B'Day")
        for i in range(60):
            self.play(stamp(2026, 10, 2) + i, title="Other", artists=("Someone",), album="Filler")
        self.assertEqual(search_plays("deja", 1)["total"], 1)
        self.assertEqual(search_plays("BEYONCE", 1)["plays"][0]["title"], "Déjà Vu")
        self.assertEqual(search_plays("b'day", 1)["total"], 1)
        first = search_plays("", 1)
        self.assertEqual((first["total"], len(first["plays"]), first["page"], first["pages"]), (61, 50, 1, 2))
        self.assertGreater(first["plays"][0]["listened_at"], first["plays"][1]["listened_at"])
        self.assertEqual(len(search_plays("", 2)["plays"]), 11)
        self.assertEqual(len(search_plays("", 99)["plays"]), 0)
        self.assertEqual(search_plays("100%_'\"", 1)["total"], 0)

    def test_entity_detail(self):
        track = self.play(stamp(2026, 9, 1), title="One", artists=("A", "B"))
        self.play(stamp(2026, 10, 1), title="One", artists=("A", "B"))
        self.play(stamp(2026, 10, 2), title="Two", artists=("A",))
        artist_id = self.conn.execute("SELECT id FROM artists WHERE name='A'").fetchone()[0]
        artist = entity("artist", artist_id, UTC)
        self.assertEqual(artist["name"], "A")
        self.assertEqual(artist["plays"], 3)
        self.assertEqual(artist["first_play"], stamp(2026, 9, 1))
        self.assertEqual(artist["last_play"], stamp(2026, 10, 2))
        self.assertEqual(artist["by_month"], [{"key": "2026-09", "plays": 1}, {"key": "2026-10", "plays": 2}])
        self.assertEqual([t["title"] for t in artist["top_tracks"]], ["One", "Two"])
        self.assertEqual(entity("track", track, UTC)["plays"], 2)
        album_id = self.conn.execute("SELECT id FROM albums").fetchone()[0]
        self.assertEqual(entity("album", album_id, UTC)["plays"], 3)
        self.assertIsNone(entity("artist", 99999, UTC))
        with self.assertRaises(BadPeriod):
            entity("label", 1, UTC)


if __name__ == "__main__":
    unittest.main()
