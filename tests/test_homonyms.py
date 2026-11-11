"""Two artists with one name (Deezer lists four "PLK"): the history keeps the one
a played track gave, the mixes only use that one, and tracks of the other one
already on trial leave the quarantine."""
import random
import unittest
from contextlib import closing
from unittest import mock

from core import mix_candidates as mc, stats_db, stats_enrich, trial
from core.stats_db import name_key
from tests.test_stats_db import reset
from tests.test_trial import NOW, Base as TrialBase

RAPPER, NAMESAKE = "1479842", "76232252"
# Deezer's real answer to /search/artist?q=PLK, the rapper fourth.
PLK_SEARCH = {"data": [
    {"id": 76232252, "name": "PLK", "nb_fan": 134, "picture_big": "http://img/namesake.jpg"},
    {"id": 15138795, "name": "PLK", "nb_fan": 54, "picture_big": "http://img/other.jpg"},
    {"id": 163354927, "name": "PLK & 7", "nb_fan": 355},
    {"id": 1479842, "name": "PLK", "nb_fan": 2421062, "picture_big": "http://img/rapper.jpg"},
]}


def rapper(**extra):
    return {"id": int(RAPPER), "name": "PLK", "picture_medium": "http://img/rapper-m.jpg",
            "picture_big": "http://img/rapper.jpg", **extra}


def track_item(track_id=555, title="Pas les mêmes"):
    return {"id": track_id, "title": title, "duration": 180, "artist": rapper(),
            "album": {"id": 9, "title": "Album", "cover_medium": "http://img/c.jpg"}}


class Api:
    """A Deezer that counts the calls; `answers` maps a path to its answer."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def __call__(self, path, params=None):
        self.calls.append(path)
        if path not in self.answers:
            raise AssertionError(f"unexpected call: {path}")
        return self.answers[path]


class History(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = stats_db.connect("nd1")
        self.addCleanup(self.conn.close)

    def play(self, title="Pas les mêmes", artist="PLK", plays=3, **complete):
        track = stats_db.upsert_track(self.conn, title, [artist])
        for n in range(plays):
            stats_db.add_play(self.conn, track, None, None, 1000 + track * 100 + n, "live")
        if complete:
            # Already matched on Deezer: only the artist lookup is left to do.
            self.conn.execute("UPDATE tracks SET deezer_track_id=?, duration_sec=200, genre='Rap', cover_url='c',"
                              " lookup_at=? WHERE id=?", (complete["deezer_track_id"], 2**40, track))
        self.conn.commit()
        return track

    def artist(self, deezer_id=None, source=None, picture=None):
        self.conn.execute("UPDATE artists SET deezer_id=?, deezer_source=?, picture_url=?, lookup_at=NULL WHERE key=?",
                          (deezer_id, source, picture, name_key("PLK")))
        self.conn.commit()

    def plk(self):
        self.conn.rollback()
        return self.conn.execute("SELECT deezer_id, deezer_source, picture_url FROM artists WHERE key=?",
                                 (name_key("PLK"),)).fetchone()

    def batch(self, api):
        with mock.patch("core.deezer._public_api", api):
            stats_enrich.enrich_batch("nd1")


class Identity(History):
    def test_a_played_track_replaces_the_namesake_a_search_gave(self):
        self.play()
        self.artist(NAMESAKE, "search", "http://img/namesake.jpg")
        self.batch(Api(**{"/search/track": {"data": [track_item()]}, "/album/9": {"genres": {"data": []}}}))
        self.assertEqual(tuple(self.plk()), (RAPPER, "track", "http://img/rapper-m.jpg"))

    def test_a_search_by_name_never_replaces_the_artist_of_a_played_track(self):
        self.play(deezer_track_id="555")
        self.artist(RAPPER, "track", "http://img/rapper.jpg")
        api = Api(**{"/search/artist": PLK_SEARCH})
        self.batch(api)
        self.assertEqual(tuple(self.plk()), (RAPPER, "track", "http://img/rapper.jpg"))
        self.assertEqual([], api.calls)  # Known, with its photo: nothing to ask.

    def test_a_history_from_before_is_repaired_through_a_played_track(self):
        # 1.18.1 had written the namesake over the rapper, with no source.
        self.play(deezer_track_id="555")
        self.artist(NAMESAKE, None, "http://img/namesake.jpg")
        api = Api(**{"/track/555": track_item()})
        self.batch(api)
        self.assertEqual(tuple(self.plk()), (RAPPER, "track", "http://img/rapper.jpg"))
        self.assertEqual(["/track/555"], api.calls)

    def test_a_featured_artist_is_found_among_the_contributors(self):
        self.play(artist="Ninho feat. PLK", deezer_track_id="556")
        self.artist(None, None, None)
        answer = {**track_item(556), "artist": {"id": 1, "name": "Ninho"}, "contributors": [{"id": 1, "name": "Ninho"}, rapper()]}
        self.batch(Api(**{"/track/556": answer}))
        self.assertEqual(self.plk()["deezer_id"], RAPPER)

    def test_by_name_alone_the_most_followed_and_only_for_the_photo(self):
        self.play()
        self.artist(None, None, None)
        self.batch(Api(**{"/search/track": {"data": []}, "/search/artist": PLK_SEARCH}))
        self.assertEqual(tuple(self.plk()), (RAPPER, "search", "http://img/rapper.jpg"))
        self.assertEqual({}, mc.artist_ids(self.conn))

    def test_another_artist_drops_the_old_photo(self):
        self.play(deezer_track_id="555")
        self.artist(NAMESAKE, None, "http://img/namesake.jpg")
        self.batch(Api(**{"/track/555": {**track_item(), "artist": {"id": int(RAPPER), "name": "PLK"}}}))
        self.assertEqual(tuple(self.plk()), (RAPPER, "track", None))

    def test_the_upgrade_looks_every_artist_up_again(self):
        self.play()
        self.conn.execute("UPDATE artists SET lookup_at = 99999999999")
        self.conn.execute("PRAGMA user_version = 2")
        self.conn.commit()
        self.conn.close()
        with closing(stats_db.connect("nd1")) as again:
            self.assertEqual([None], [r[0] for r in again.execute("SELECT lookup_at FROM artists")])
            self.assertEqual(3, again.execute("PRAGMA user_version").fetchone()[0])
        self.conn = stats_db.connect("nd1")
        self.addCleanup(self.conn.close)


class Mixes(History):
    def test_only_the_artists_a_played_track_gave(self):
        self.play()
        self.play(title="Other", artist="Vald")
        self.artist(RAPPER, "track")
        self.conn.execute("UPDATE artists SET deezer_id='9', deezer_source='search' WHERE key=?", (name_key("Vald"),))
        self.conn.commit()
        self.assertEqual({name_key("PLK"): RAPPER}, mc.artist_ids(self.conn))

    def test_a_namesake_is_never_proposed(self):
        def cand(track_id, artist_id, artist="PLK"):
            return mc.parse({"id": track_id, "title": f"Song {track_id}", "rank": 1000, "preview": "",
                             "artist": {"id": int(artist_id), "name": artist}, "album": {"title": "A"}})

        exclusions = mc.Exclusions(owned=[], artist_ids={name_key("PLK"): RAPPER})
        pool = [cand(1, NAMESAKE), cand(2, RAPPER), cand(3, "15138795"), cand(4, "42", "Someone")]
        self.assertEqual([False, True, False, True], [exclusions.allows(c) for c in pool])
        chosen = mc.select(pool, exclusions, want=4, per_artist=4, rng=random.Random(1))
        self.assertEqual({"2", "4"}, {c.deezer_id for c in chosen})
        self.assertEqual(NAMESAKE, pool[0].artist_id)


class Quarantine(TrialBase):
    def setUp(self):
        super().setUp()
        reset()
        self.stats = stats_db.connect("nd1")
        self.addCleanup(self.stats.close)
        self.known("PLK", RAPPER, "track")

    def known(self, name, deezer_id, source):
        self.stats.execute("INSERT OR REPLACE INTO artists(key, name, deezer_id, deezer_source) VALUES (?,?,?,?)",
                           (name_key(name), name, deezer_id, source))
        self.stats.commit()

    def drop(self, api):
        return trial.drop_homonyms(self.conn, self.stats, "nd1", NOW + 60, api=api)

    def test_the_namesakes_tracks_leave_and_the_rappers_stay(self):
        self.add("1", "PLK", "Not him")
        self.add("2", "PLK", "Him")
        self.add("3", "Someone", "Else")
        api = Api(**{"/track/1": {"artist": {"id": int(NAMESAKE)}}, "/track/2": {"artist": {"id": int(RAPPER)}}})
        self.assertEqual(1, self.drop(api))
        self.assertTrue(self.in_trash("1"))
        self.assertEqual(trial.HOMONYM_REASON, trial.get(self.conn, "1", "nd1")["reason"])
        self.assertEqual(("on_trial", "on_trial"), (self.state("2"), self.state("3")))
        self.assertIn(trial.get(self.conn, "1", "nd1")["track_key"], trial.rejected(self.conn, "nd1")["keys"])
        # Each track's artist is asked once: the next pass needs no call.
        self.assertEqual(0, self.drop(Api()))
        self.assertEqual(sorted(api.calls), ["/track/1", "/track/2"])

    def test_nothing_goes_while_the_artist_is_not_confirmed(self):
        self.known("PLK", NAMESAKE, "search")
        self.add("1", "PLK", "Not him")
        self.assertEqual(0, self.drop(Api()))
        self.assertEqual("on_trial", self.state("1"))

    def test_a_download_keeps_its_artist_no_call_needed(self):
        path = trial.trial_dir() / "PLK - New.flac"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        trial.add_download(self.conn, "nd1", "7", "PLK", "New", "", path, "auto-discover", NOW, artist_id=NAMESAKE)
        self.assertEqual(1, self.drop(Api()))
        self.assertTrue(self.in_trash("7"))

    def test_a_track_deezer_no_longer_knows_is_not_asked_again(self):
        self.add("1", "PLK", "Gone")
        calls = []

        def api(path, params=None):
            calls.append(path)
            raise RuntimeError("{'code': 800}")

        self.assertEqual(0, self.drop(api))
        self.assertEqual(0, self.drop(api))
        self.assertEqual(["/track/1"], calls)
        self.assertEqual("on_trial", self.state("1"))


if __name__ == "__main__":
    unittest.main()
