import time
import unittest
from datetime import datetime, timezone

from core import stats_db
from core.stats_queries import recap
from core.stats_story import PERSONALITY_RULES, personality
from tests.test_stats_db import reset

UTC = "UTC"
HOUR = 3600


def at(month, day, hour=12, minute=0, year=2026):
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp())


class StoryCase(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = stats_db.connect()
        self.addCleanup(self.conn.close)
        self.seconds = 0

    def play(self, ts, title="Song", artists=("A",), album="Album", duration=200, genre=None):
        track = stats_db.upsert_track(self.conn, title, list(artists), genre=genre, genre_source="test")
        album_id = stats_db.upsert_album(self.conn, album, artists[0]) if album else None
        stats_db.add_play(self.conn, track, album_id, duration, ts, "live")
        return track

    def done(self):
        self.conn.commit()

    def story(self, key="2026-10", kind="month"):
        self.conn.commit()
        return recap(kind, key, UTC)["story"]

    def filler(self, month=10, count=30, artist="Filler", year=2026):
        """Plays spread out over a month, so they trigger nothing on their own."""
        for i in range(count):
            self.play(at(month, 1 + i % 27, 8 + i % 10, i % 60, year) , title=f"F{i}", artists=(artist,), album=f"FA{i}")

    def types(self, story):
        return [slide["type"] for slide in story["slides"]]


class Items(StoryCase):
    def test_opener_is_the_first_play_of_the_period(self):
        self.play(at(9, 30), title="Before")
        self.play(at(10, 2, 9), title="First")
        self.play(at(10, 3), title="Later")
        opener = self.story()["opener"]
        self.assertEqual((opener["title"], opener["date"], opener["time"]), ("First", "2026-10-02", "09:00"))

    def test_loyalty_threshold(self):
        for i in range(15):
            self.play(at(10, 1) + i * 300, title=f"T{i}", artists=("Fan",), album=None)
        for i in range(85):
            self.play(at(10, 2) + i * 300, title=f"O{i}", artists=(f"Other{i}",), album=None)
        loyalty = self.story()["loyalty"]
        self.assertEqual(loyalty["artist"]["name"], "Fan")
        self.assertEqual(loyalty["percent"], 15)
        self.assertEqual(loyalty["one_in"], 7)

    def test_loyalty_just_under(self):
        for i in range(14):
            self.play(at(10, 1) + i * 300, title=f"T{i}", artists=("Fan",), album=None)
        for i in range(86):
            self.play(at(10, 2) + i * 300, title=f"O{i}", artists=(f"Other{i}",), album=None)
        self.assertIsNone(self.story()["loyalty"])

    def test_obsession_threshold(self):
        for i in range(5):
            self.play(at(10, 14, 9) + i * 400, title="Stuck")
        obsession = self.story()["obsession"]
        self.assertEqual((obsession["title"], obsession["date"], obsession["plays"]), ("Stuck", "2026-10-14", 5))

    def test_obsession_just_under_and_across_days(self):
        for day in range(1, 5):
            for i in range(4):
                self.play(at(10, day, 9) + i * 400, title="Stuck")
        self.assertIsNone(self.story()["obsession"])

    def test_binge_threshold(self):
        # 10 plays 800 s apart with gaps under 30 minutes: 2 h exactly with the last track's length.
        for i in range(10):
            self.play(at(10, 5, 20) + i * 780, title=f"B{i}", artists=("Binger",), duration=180)
        binge = self.story()["binge"]
        self.assertEqual(binge["plays"], 10)
        self.assertEqual(binge["seconds"], 9 * 780 + 180)
        self.assertEqual(binge["top_artist"], "Binger")
        self.assertEqual(binge["date"], "2026-10-05")

    def test_binge_broken_by_a_long_gap(self):
        for i in range(5):
            self.play(at(10, 5, 20) + i * 1000, title=f"B{i}")
        for i in range(5):
            self.play(at(10, 5, 20) + 5000 + 1900 + i * 1000, title=f"C{i}")
        self.assertIsNone(self.story()["binge"])

    def test_album_run(self):
        for i in range(8):
            self.play(at(10, 6, 20) + i * 200, title=f"Track {i}", artists=("Band",), album="Full Album")
        for i in range(8, 10):
            self.play(at(10, 9, 20) + i * 200, title=f"Track {i}", artists=("Band",), album="Full Album")
        run = self.story()["album_run"]
        self.assertEqual((run["title"], run["tracks"], run["of"], run["date"]), ("Full Album", 8, 10, "2026-10-06"))

    def test_album_run_needs_half_the_album_and_four_tracks(self):
        for i in range(3):
            self.play(at(10, 6, 20) + i * 200, title=f"Track {i}", album="Short")
        self.assertIsNone(self.story()["album_run"])
        for i in range(4):
            self.play(at(10, 7, 20) + i * 200, title=f"X{i}", album="Long")
        for i in range(4, 12):
            self.play(at(10, 9, 20) + i * 3000, title=f"X{i}", album="Long")
        self.assertIsNone(self.story()["album_run"])

    def test_movers_comeback_and_dropped(self):
        for i in range(10):
            self.play(at(9, 1) + i * 300, title="R", artists=("Riser",))
        for i in range(30):
            self.play(at(10, 1) + i * 300, title="R", artists=("Riser",))
        for i in range(20):
            self.play(at(9, 2) + i * 300, title="Fa", artists=("Faller",))
        for i in range(6):
            self.play(at(10, 2) + i * 300, title="Fa", artists=("Faller",))
        self.play(at(8, 1), title="C", artists=("Returning",))
        for i in range(7):
            self.play(at(10, 3) + i * 300, title="C", artists=("Returning",))
        for i in range(25):
            self.play(at(9, 3) + i * 300, title="D", artists=("Gone",))
        story = self.story()
        self.assertEqual((story["movers"]["rise"]["name"], story["movers"]["rise"]["delta"]), ("Riser", 20))
        self.assertEqual((story["movers"]["fall"]["name"], story["movers"]["fall"]["delta"]), ("Faller", -14))
        self.assertEqual((story["comeback"]["name"], story["comeback"]["plays"]), ("Returning", 7))
        self.assertEqual((story["dropped"]["name"], story["dropped"]["previous_plays"]), ("Gone", 25))

    def test_so_far_period_skips_comparisons(self):
        now = int(time.time())
        local = datetime.fromtimestamp(now, timezone.utc)
        for i in range(10):
            self.play(now - 40 * 86400 + i * 300, title="R", artists=("Old",))
        self.play(now - 5, title="Now", artists=("New",))
        story = self.story(f"{local.year}-{local.month:02d}")
        self.assertIsNone(story["movers"])
        self.assertIsNone(story["dropped"])
        self.assertIsNone(story["comeback"])

    def test_comparisons_only_when_at_least_one(self):
        self.play(at(10, 1), duration=3 * HOUR)
        items = self.story()["comparisons"]
        self.assertEqual([i["unit"] for i in items], ["films"])
        self.assertEqual(items[0]["value"], 1)
        self.play(at(10, 2), title="L", duration=30 * HOUR)
        units = {i["unit"]: i["value"] for i in self.story()["comparisons"]}
        self.assertEqual(units, {"films": 16, "flights from Paris to Tokyo": 2, "days of non-stop music": 1})

    def test_clock(self):
        self.play(at(10, 1, 22))
        self.play(at(10, 2, 22), title="B")
        self.play(at(10, 3, 7), title="C")
        clock = self.story()["clock"]
        self.assertEqual(len(clock["hours"]), 24)
        self.assertEqual((clock["peak_hour"], clock["hours"][22], clock["hours"][7]), (22, 2, 1))

    def test_year_has_a_biggest_month(self):
        self.play(at(3, 1))
        self.play(at(6, 1), title="B")
        self.play(at(6, 2), title="C")
        biggest = self.story("2026", "year")["biggest_month"]
        self.assertEqual((biggest["label"], biggest["plays"]), ("June 2026", 2))
        self.play(at(10, 1), title="D")
        self.assertIsNone(self.story()["biggest_month"])


BASE = dict(plays=1000, top_track_share=0, top_artist_share=0, night_share=0, morning_share=0, weekend_share=0,
            new_artist_share=0, has_previous=True, genre_count=0, top_genre_share=1, genre_pct=100, top_albums_share=0)


class Personality(unittest.TestCase):
    CASES = {
        "One-Track Mind": ("top_track_share", 0.08),
        "Superfan": ("top_artist_share", 0.20),
        "Obsessive": ("obsession_plays", 25),
        "Marathon Listener": ("binge_hours", 10),
        "Comeback Kid": ("comeback_plays", 100),
        "Night Owl": ("night_share", 0.35),
        "Early Bird": ("morning_share", 0.25),
        "Weekend Warrior": ("weekend_share", 0.45),
        "Explorer": ("new_artist_share", 0.25),
        "Album Purist": ("top_albums_share", 0.40),
    }

    def test_each_rule_fires_at_its_threshold_and_not_just_under(self):
        for name, (field, value) in self.CASES.items():
            self.assertEqual(personality({**BASE, field: value})["name"], name)
            self.assertEqual(personality({**BASE, field: value - 0.001})["name"], "Steady Listener", name)
            self.assertIn(personality({**BASE, field: value})["name"], [rule[0] for rule in PERSONALITY_RULES])

    def test_genre_hopper(self):
        hopper = {**BASE, "genre_count": 6, "top_genre_share": 0.40}
        self.assertEqual(personality(hopper)["name"], "Genre Hopper")
        self.assertEqual(personality({**hopper, "genre_count": 5})["name"], "Steady Listener")
        self.assertEqual(personality({**hopper, "top_genre_share": 0.41})["name"], "Steady Listener")
        self.assertEqual(personality({**hopper, "genre_pct": 40})["name"], "Steady Listener")

    def test_the_strongest_fit_wins(self):
        both = {**BASE, "top_track_share": 0.5, "night_share": 0.5}
        self.assertEqual(personality(both)["name"], "One-Track Mind")
        self.assertEqual(personality({**BASE, "top_track_share": 0.09, "night_share": 0.9})["name"], "Night Owl")

    def test_a_habit_has_to_beat_your_own_usual(self):
        always_up_late = {**BASE, "night_share": 0.47, "usual_night_share": 0.44}
        self.assertEqual(personality(always_up_late)["name"], "Steady Listener")
        self.assertEqual(personality({**always_up_late, "night_share": 0.54})["name"], "Night Owl")

    def test_explorer_needs_earlier_history(self):
        self.assertEqual(personality({**BASE, "new_artist_share": 0.9, "has_previous": False})["name"], "Steady Listener")

    def test_reasons_carry_the_real_number(self):
        self.assertIn("38%", personality({**BASE, "night_share": 0.38})["reason"])
        self.assertIn("1,000", personality(BASE)["reason"])

    def test_every_rule_has_a_name_and_every_name_is_reachable(self):
        names = {rule[0] for rule in PERSONALITY_RULES}
        self.assertLessEqual(set(self.CASES), names)
        self.assertIn("Genre Hopper", names)

    def test_too_few_plays_say_nothing_bold(self):
        self.assertEqual(personality({**BASE, "plays": 10, "top_track_share": 0.5})["name"], "Just Warming Up")


class Slides(StoryCase):
    def rich_month(self):
        self.filler(9, 30)
        self.play(at(8, 1), title="C", artists=("Returning",))
        for i in range(30):
            self.play(at(10, 1 + i % 25, 9) + i, title=f"A{i % 4}", artists=("Top",), album="Top Album", genre="Rap")
        for i in range(12):
            self.play(at(10, 14, 20) + i * 240, title="Stuck", artists=("Second",), album="S", genre="Pop")
        for i in range(8):
            self.play(at(10, 20, 21) + i * 200, title=f"Run{i}", artists=("Third",), album="Run Album", genre="Rock")
        for i in range(5):
            self.play(at(10, 22, 10) + i * 2000, title=f"N{i}", artists=(f"New{i}",), album=f"NA{i}", genre="Jazz")
        for i in range(7):
            self.play(at(10, 24) + i * 900, title="C", artists=("Returning",))

    def test_size_and_required_slides(self):
        self.rich_month()
        types = self.types(self.story())
        self.assertLessEqual(len(types), 12)
        self.assertGreaterEqual(len(types), 10)
        for required in ("intro", "artist_countdown", "top_artist", "top_track", "personality", "time", "outro"):
            self.assertIn(required, types)
        self.assertEqual(types[0], "intro")
        self.assertEqual(types[-1], "outro")
        self.assertLess(types.index("personality"), types.index("time"))

    def test_strongest_stories_are_chosen(self):
        self.rich_month()
        self.assertIn("obsession", self.types(self.story()))

    def test_stable_between_openings(self):
        self.rich_month()
        self.assertEqual(self.types(self.story()), self.types(self.story()))

    def test_every_slide_with_a_song_gets_that_artists_own_track(self):
        for i in range(10):
            self.play(at(10, 1) + i * 300, title="Lovely", artists=("Yeat",))
        for i in range(12):
            self.play(at(10, 2) + i * 300, title="Love", artists=("Ye",))
        story = self.story()
        top = next(s for s in story["slides"] if s["type"] == "top_artist")
        self.assertEqual(top["track"]["title"], "Love")
        self.assertTrue(all(key in top["track"] for key in ("id", "duration", "deezer_track_id")))

    def test_placeholder_artist_stays_out_of_the_story(self):
        for i in range(20):
            self.play(at(10, 1) + i * 300, title="Untagged", artists=("[Unknown Artist]",))
        for i in range(5):
            self.play(at(10, 2) + i * 300, title="Real", artists=("Real One",))
        story = self.story()
        self.assertEqual([a["name"] for a in story["top_artists"]], ["Real One"])
        self.assertEqual(story["loyalty"]["artist"]["name"], "Real One")

    def test_sparse_month_never_breaks(self):
        self.play(at(10, 1))
        story = self.story()
        self.assertEqual(self.types(story)[0], "intro")
        self.assertIn("outro", self.types(story))
        self.assertNotIn("artist_countdown", self.types(story))
        self.assertNotIn("then_now", self.types(story))

    def test_empty_month_has_only_the_frame(self):
        self.play(at(9, 1))
        self.assertEqual(self.types(self.story()), ["intro", "outro"])

    def test_months_differ_on_real_differences(self):
        for i in range(12):
            self.play(at(9, 14, 20) + i * 240, title="Stuck", artists=("B",), album="S")
        self.filler(10, 40)
        self.assertNotEqual(self.types(self.story("2026-09")), self.types(self.story("2026-10")))


if __name__ == "__main__":
    unittest.main()
