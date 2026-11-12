import random
import unittest

from core import mix_taste, mixes_db, stats_db
from tests.test_stats_db import reset

NOW = 1_800_000_000
DAY = 86400


def add_plays(conn, artist, title, count, *, genre=None, days_ago=1, album=None, guests=()):
    track = stats_db.upsert_track(conn, title, [artist, *guests], genre=genre, genre_source="file" if genre else None)
    album_id = stats_db.upsert_album(conn, album, artist) if album else None
    for i in range(count):
        stats_db.add_play(conn, track, album_id, 200, NOW - days_ago * DAY - i * 60, "navidrome")
    return track


def entry(artist, title, path=None):
    return {"path": path or f"/music/{artist}/{title}.flac", "tag_artist": artist, "tag_title": title,
            "tag_album": "Album", "duration": 200}


def owned(*items):
    """items: (artist, title, bpm, genre)"""
    entries, features = [], {}
    for artist, title, bpm, genre in items:
        e = entry(artist, title)
        entries.append(e)
        features[e["path"]] = (bpm, genre)
    return mix_taste.owned_tracks(entries, features=features)


class Base(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = stats_db.connect("nd1")
        self.addCleanup(self.conn.close)

    def taste(self):
        self.conn.commit()
        return mix_taste.build_taste(self.conn, NOW)

    def seeds(self):
        self.conn.commit()
        return mix_taste.find_seeds(self.conn, NOW)


class Scores(Base):
    def test_recent_plays_weigh_more_than_old_ones(self):
        add_plays(self.conn, "Old", "Then", 5, days_ago=360)
        add_plays(self.conn, "New", "Now", 5, days_ago=1)
        taste = self.taste()
        self.assertGreater(taste.track_score[stats_db.track_key(["New"], "Now")],
                           taste.track_score[stats_db.track_key(["Old"], "Then")] * 10)

    def test_empty_history(self):
        self.assertEqual(self.taste().track_score, {})
        self.assertEqual(self.seeds(), {"track": [], "album": [], "artist": []})


class Seeds(Base):
    def test_a_track_played_a_lot_is_a_seed(self):
        add_plays(self.conn, "Men I Trust", "Show Me How", 40)
        add_plays(self.conn, "Other", "Once", 1)
        self.assertEqual([s.label for s in self.seeds()["track"]], ["Show Me How"])

    def test_an_album_needs_several_of_its_tracks_played(self):
        for t in range(5):
            add_plays(self.conn, "Vald", f"Song{t}", 5, album="PANDEMONIUM")
        add_plays(self.conn, "Solo", "Hit", 50, album="One hit")
        self.assertEqual([s.label for s in self.seeds()["album"]], ["PANDEMONIUM"])

    def test_an_artist_needs_many_of_its_tracks_played(self):
        for t in range(10):
            add_plays(self.conn, "Bad Bunny", f"Song{t}", 3)
        add_plays(self.conn, "Solo", "Hit", 50)
        self.assertEqual([s.label for s in self.seeds()["artist"]], ["Bad Bunny"])

    def test_unknown_names_are_never_seeds(self):
        for t in range(10):
            add_plays(self.conn, "[Unknown Artist]", f"Song{t}", 10, album="Fine album")
            add_plays(self.conn, "Known", f"Song{t}", 10, album="[Unknown Album]")
        seeds = self.seeds()
        self.assertNotIn("[Unknown Artist]", [s.label for s in seeds["artist"]])
        self.assertEqual(seeds["album"], [])
        self.assertFalse([s for s in seeds["track"] if s.artist_key == stats_db.name_key("[Unknown Artist]")])

    def test_album_seed_knows_its_guests(self):
        for t in range(5):
            add_plays(self.conn, "Vald", f"Song{t}", 5, album="PANDEMONIUM", guests=["Vladimir Cauchemar"])
        album = self.seeds()["album"][0]
        self.assertIn(stats_db.name_key("Vladimir Cauchemar"), album.artists)

    def test_album_seed_knows_its_album_artists(self):
        track = stats_db.upsert_track(self.conn, "S", ["Vald"])
        for t in range(5):
            track = stats_db.upsert_track(self.conn, f"S{t}", ["Vald"])
            album_id = stats_db.upsert_album(self.conn, "PANDEMONIUM", "Vald • Todiefor")
            for i in range(5):
                stats_db.add_play(self.conn, track, album_id, 200, NOW - DAY - i, "navidrome")
        self.assertIn(stats_db.name_key("Todiefor"), self.seeds()["album"][0].artists)


class Choice(Base):
    def rich_history(self):
        for a in range(10):
            for t in range(10):
                add_plays(self.conn, f"Artist{a}", f"Song{t}", 6, album=f"Album{a}")

    def test_one_of_each_kind_and_never_one_artist_twice(self):
        self.rich_history()
        chosen = mix_taste.choose_seeds(self.seeds(), rng=random.Random(1))
        self.assertEqual(len(chosen), 4)
        self.assertEqual({"track", "album", "artist"} - {s.kind for s in chosen}, set())
        self.assertEqual(len({s.artist_key for s in chosen}), 4)

    def test_a_seed_does_not_come_back_the_next_day(self):
        self.rich_history()
        seeds = self.seeds()
        first = mix_taste.choose_seeds(seeds, rng=random.Random(1))
        second = mix_taste.choose_seeds(seeds, recent_ids={s.id for s in first}, rng=random.Random(2))
        self.assertEqual({s.id for s in first} & {s.id for s in second}, set())

    def test_too_few_seeds_for_a_new_set_bring_back_the_last_ones(self):
        for a in range(4):
            add_plays(self.conn, f"Artist{a}", "Song", 6, album=f"Album{a}")
        seeds = self.seeds()
        first = mix_taste.choose_seeds(seeds, rng=random.Random(1))
        second = mix_taste.choose_seeds(seeds, recent_ids={s.id for s in first}, rng=random.Random(2))
        self.assertEqual(len(first), len(second))
        self.assertEqual(len({s.artist_key for s in second}), len(second))

    def test_few_artists_give_fewer_mixes_rather_than_repeats(self):
        for t in range(10):
            add_plays(self.conn, "Only", f"Song{t}", 6, album="Album")
        chosen = mix_taste.choose_seeds(self.seeds(), rng=random.Random(1))
        self.assertEqual(len(chosen), 1)

    def test_nothing_to_choose_from(self):
        self.assertEqual(mix_taste.choose_seeds(self.seeds(), rng=random.Random(1)), [])


class OwnedTracks(unittest.TestCase):
    def test_same_track_in_two_files_counts_once(self):
        found = mix_taste.owned_tracks([entry("A", "One", "/x/1.flac"), entry("A", "One", "/y/2.flac")])
        self.assertEqual(len(found), 1)

    def test_the_file_with_a_known_tempo_is_preferred(self):
        found = mix_taste.owned_tracks([entry("A", "One", "/x/1.flac"), entry("A", "One", "/y/2.flac")],
                                       features={"/y/2.flac": (120, "Rock")})
        self.assertEqual(found[0].bpm, 120)

    def test_entry_without_a_usable_name_is_left_out(self):
        self.assertEqual(mix_taste.owned_tracks([{"path": "/x/1.flac"}]), [])
        self.assertEqual(mix_taste.owned_tracks([entry("[Unknown Artist]", "One")]), [])

    def test_parsed_names_are_used_when_tags_are_missing(self):
        found = mix_taste.owned_tracks([{"path": "/x/1.flac", "parsed_artist": "A", "parsed_title": "One"}])
        self.assertEqual(found[0].key, stats_db.track_key(["A"], "One"))

    def test_trial_folder_is_not_owned(self):
        found = mix_taste.owned_tracks([entry("A", "One", "/dl/trial/1.flac"), entry("B", "Two", "/dl/songs/2.flac")],
                                       exclude_under=["/dl/trial"])
        self.assertEqual([t.artist for t in found], ["B"])


class BaseTitle(unittest.TestCase):
    def test_version_marks_are_ignored(self):
        same = ("Show Me How", "Show Me How (Album V)", "Show Me How [Live]", "Show Me How - Remastered 2011",
                "Show Me How (feat. Someone)")
        self.assertEqual({mix_taste.base_title(t) for t in same}, {mix_taste.base_title("Show Me How")})

    def test_guest_versions_written_with_a_plus_are_the_same_track(self):
        self.assertEqual(mix_taste.base_title("Stars + DJ Caio Prince + Adame DJ"), mix_taste.base_title("Stars"))

    def test_a_title_that_is_only_a_bracket_is_kept(self):
        self.assertTrue(mix_taste.base_title("(Intro)"))


class TrackMix(Base):
    def setUp(self):
        super().setUp()
        add_plays(self.conn, "Men I Trust", "Show Me How", 40, genre="Pop")

    def seed(self):
        return self.seeds()["track"][0]

    def pick(self, library, **kw):
        kw.setdefault("rng", random.Random(1))
        return mix_taste.pick_for_seed(self.taste(), self.seed(), library, **kw)

    def similar(self, count=40, bpm=100, genre="Pop"):
        return [(f"Artist{i // 2}", f"Song{i}", bpm, genre) for i in range(count)]

    def test_the_seed_comes_first(self):
        picks = self.pick(owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar()))
        self.assertEqual(picks[0].title, "Show Me How")

    def test_artists_close_to_the_seed_come_before_favorites_of_the_same_genre(self):
        for i in range(20):
            add_plays(self.conn, f"Favorite{i}", "Hit", 10, genre="Pop")
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *[(f"Favorite{i}", "Hit", 100, "Pop") for i in range(20)],
                        *[(f"Near{i // 2}", f"Song{i}", 100, "Pop") for i in range(6)])
        near = {stats_db.name_key(f"Near{i}"): 0.7 for i in range(3)}
        picks = self.pick(library, size=12, near=near)
        self.assertEqual(6, len([p for p in picks if p.artist.startswith("Near")]))
        # Too few close tracks: the others fill the mix, as before.
        self.assertEqual(12, len(picks))

    def test_without_close_artists_the_mix_is_as_before(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar())
        before = [p.key for p in self.pick(library)]
        self.assertEqual(before, [p.key for p in self.pick(library, near={})])

    def test_only_close_tempo(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(),
                        *[(f"Fast{i}", "Song", 134, "Pop") for i in range(40)])
        self.assertFalse([p for p in self.pick(library) if p.artist.startswith("Fast")])

    def test_double_tempo_counts_as_close(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"),
                        *[(f"Double{i}", "Song", 200, "Pop") for i in range(40)])
        self.assertGreaterEqual(len(self.pick(library)), 30)

    def test_only_the_same_genre(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(),
                        *[(f"Metal{i}", "Song", 100, "Metal") for i in range(40)])
        self.assertFalse([p for p in self.pick(library) if p.artist.startswith("Metal")])

    def test_at_most_two_per_artist(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"),
                        *[(f"Artist{i // 5}", f"Song{i}", 100, "Pop") for i in range(100)])
        counts = {}
        for pick in self.pick(library):
            counts[pick.artist] = counts.get(pick.artist, 0) + 1
        self.assertLessEqual(max(counts.values()), 2)

    def test_near_duplicates_stay_out(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), ("Men I Trust", "Show Me How (Album V)", 100, "Pop"),
                        *self.similar())
        self.assertEqual([p.title for p in self.pick(library)].count("Show Me How (Album V)"), 0)

    def test_unknown_tempo_does_not_exclude_a_track(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(bpm=None))
        self.assertGreaterEqual(len(self.pick(library)), 30)

    def test_seed_with_no_known_tempo_still_works(self):
        library = owned(("Men I Trust", "Show Me How", None, "Pop"), *self.similar(bpm=134))
        self.assertGreaterEqual(len(self.pick(library)), 30)

    def test_too_few_tracks_that_belong_gives_no_mix(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *[(f"M{i}", "S", 100, "Metal") for i in range(50)])
        self.assertEqual(self.pick(library), [])

    def test_the_minimum_can_be_lowered_for_a_mix_that_adds_new_tracks(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(count=7))
        self.assertEqual(self.pick(library), [])
        self.assertEqual(len(self.pick(library, minimum=6)), 8)

    def test_shorter_mix_rather_than_tracks_that_do_not_belong(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(count=15),
                        *[(f"M{i}", "S", 100, "Metal") for i in range(50)])
        picks = self.pick(library)
        self.assertEqual(len(picks), 16)

    def test_genre_of_the_artist_is_only_used_when_nearly_all_its_plays_have_it(self):
        for t in range(6):
            add_plays(self.conn, "Mixed", f"R{t}", 10, genre="Rock")
            add_plays(self.conn, "Mixed", f"P{t}", 8, genre="Pop")
            add_plays(self.conn, "Steady", f"P{t}", 10, genre="Rock")
        taste = self.taste()
        untagged = lambda artist: owned((artist, "Never played", None, None))[0]
        self.assertIsNone(mix_taste._genre_of(untagged("Mixed"), taste))
        self.assertEqual(mix_taste._genre_of(untagged("Steady"), taste), "Rock")

    def test_no_known_genre_stays_out_even_at_the_right_tempo(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(),
                        *[(f"Ambient{i}", "Song", 100, None) for i in range(40)])
        self.assertFalse([p for p in self.pick(library) if p.artist.startswith("Ambient")])

    def test_skits_and_interludes_stay_out(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(),
                        *[(f"Filler{i}", name, 100, "Pop") for i, name in enumerate(
                            ("Doom, Are You Awake? (Skit)", "Internet baby (interlude)", "Intro", "Outro", "Interlude 2"))])
        self.assertFalse([p for p in self.pick(library) if p.artist.startswith("Filler")])

    def test_an_interlude_you_really_play_stays(self):
        add_plays(self.conn, "Fan", "Internet baby (interlude)", 30, genre="Pop")
        track = owned(("Fan", "Internet baby (interlude)", 100, "Pop"))[0]
        self.assertFalse(mix_taste._is_filler(track, self.taste()))

    def test_a_word_inside_a_title_is_not_a_filler(self):
        track = owned(("A", "Introspection", 100, "Pop"))[0]
        self.assertFalse(mix_taste._is_filler(track, self.taste()))

    def test_a_few_mislabelled_tracks_do_not_decide_for_a_whole_artist(self):
        # Their files carry no genre, and Deezer calls the two tracks played Pop.
        add_plays(self.conn, "System of A Down", "One", 3, genre="Pop")
        add_plays(self.conn, "System of A Down", "Two", 3, genre="Pop")
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar(),
                        *[("System of A Down", f"Song {i}", 100, None) for i in range(40)])
        self.assertFalse([p for p in self.pick(library) if p.artist == "System of A Down"])

    def test_same_seed_same_mix(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"), *self.similar())
        self.assertEqual([p.key for p in self.pick(library, rng=random.Random(7))],
                         [p.key for p in self.pick(library, rng=random.Random(7))])

    def test_avoids_what_it_just_proposed(self):
        library = owned(("Men I Trust", "Show Me How", 100, "Pop"),
                        *[(f"Artist{i}", f"Song{i}", 100, "Pop") for i in range(90)])
        first = self.pick(library, rng=random.Random(1))
        second = self.pick(library, recent={p.key for p in first}, rng=random.Random(2))
        self.assertLessEqual(len({p.key for p in first} & {p.key for p in second}), 1)


class AlbumMix(Base):
    def setUp(self):
        super().setUp()
        tempos = [100] * 7 + [140]
        for t, _ in enumerate(tempos):
            add_plays(self.conn, "Vald", f"Album song {t}", 1 if t == 7 else 20, genre="Rap", album="PANDEMONIUM",
                      guests=["Todiefor"] if t == 0 else ())
        self.library = [("Vald", f"Album song {t}", bpm, "Rap") for t, bpm in enumerate(tempos)]

    def pick(self, library):
        return mix_taste.pick_for_seed(self.taste(), self.seeds()["album"][0], library, rng=random.Random(1))

    def test_the_album_artists_come_first(self):
        library = owned(*self.library, *[("Todiefor", f"T{i}", 100, "Rap") for i in range(10)],
                        *[(f"Other{i}", "Song", 100, "Rap") for i in range(60)])
        artists = [p.artist for p in self.pick(library)]
        self.assertEqual(artists.count("Vald"), mix_taste.PER_ALBUM_ARTIST)
        self.assertGreaterEqual(artists.count("Todiefor"), 2)

    def test_a_rarely_played_outlier_does_not_shift_the_tempo(self):
        # The mean of the album is about 101 with the outlier; what counts is that 140 stays out.
        library = owned(*self.library, *[(f"Slow{i}", "Song", 100, "Rap") for i in range(40)],
                        *[(f"Fast{i}", "Song", 140, "Rap") for i in range(40)])
        artists = [p.artist for p in self.pick(library)]
        self.assertFalse([a for a in artists if a.startswith("Fast")])


class ArtistMix(Base):
    def setUp(self):
        super().setUp()
        for t in range(10):
            add_plays(self.conn, "Bad Bunny", f"Played {t}", 5 + t, genre="Latin Music")

    def pick(self, library, **kw):
        return mix_taste.pick_for_seed(self.taste(), self.seeds()["artist"][0], library, rng=random.Random(1), **kw)

    def library(self, never_played=20, tempo=None):
        items = [("Bad Bunny", f"Played {t}", tempo, None) for t in range(10)]
        items += [("Bad Bunny", f"Never {t}", tempo, None) for t in range(never_played)]
        return owned(*items, *[(f"Other{i}", "Song", tempo, "Latin Music") for i in range(40)])

    def test_only_that_artist(self):
        self.assertEqual({p.artist for p in self.pick(self.library())}, {"Bad Bunny"})

    def test_adds_what_you_barely_played(self):
        titles = [p.title for p in self.pick(self.library())]
        self.assertTrue([t for t in titles if t.startswith("Played")])
        self.assertTrue([t for t in titles if t.startswith("Never")])

    def test_familiar_part_favours_what_you_really_play(self):
        for t in range(60):
            add_plays(self.conn, "Bad Bunny", f"Barely {t}", 2, genre="Latin Music")
        for t in range(10):
            add_plays(self.conn, "Bad Bunny", f"Loved {t}", 80, genre="Latin Music")
        items = [("Bad Bunny", f"Barely {t}", None, None) for t in range(60)]
        items += [("Bad Bunny", f"Loved {t}", None, None) for t in range(10)]
        picks = mix_taste.pick_for_seed(self.taste(), self.seeds()["artist"][0], owned(*items), size=12,
                                        rng=random.Random(1))
        self.assertGreaterEqual(len([p for p in picks if p.title.startswith("Loved")]), 7)

    def test_an_artist_mix_keeps_its_interludes(self):
        library = owned(*[("Bad Bunny", f"Interlude {t}", None, None) for t in range(14)])
        self.assertEqual(len(self.pick(library)), 14)

    def test_no_limit_per_artist(self):
        self.assertEqual(len(self.pick(self.library(never_played=40))), 30)

    def test_too_few_tracks_gives_no_mix(self):
        self.assertEqual(self.pick(owned(("Bad Bunny", "Played 1", None, None))), [])


class Database(unittest.TestCase):
    def setUp(self):
        reset()
        mixes_db.db_path().unlink(missing_ok=True)

    def test_history_returns_recent_keys_only(self):
        conn = mixes_db.connect()
        self.addCleanup(conn.close)
        mixes_db.remember(conn, "auto-daily-1", ["old"], NOW - 30 * DAY)
        mixes_db.remember(conn, "auto-daily-1", ["new"], NOW - DAY)
        mixes_db.remember(conn, "auto-daily-2", ["other"], NOW - DAY)
        self.assertEqual(mixes_db.recent_keys(conn, "auto-daily-1", NOW - 7 * DAY), {"new"})

    def test_meta_round_trip(self):
        conn = mixes_db.connect()
        self.addCleanup(conn.close)
        self.assertEqual(mixes_db.get_meta(conn, "x", 3), 3)
        mixes_db.set_meta(conn, "x", {"a": 1})
        self.assertEqual(mixes_db.get_meta(conn, "x"), {"a": 1})

    def test_is_not_the_history_database(self):
        self.assertNotEqual(mixes_db.db_path(), stats_db.db_path("nd1"))


if __name__ == "__main__":
    unittest.main()
