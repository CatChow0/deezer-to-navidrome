import random
import tempfile
import unittest
from pathlib import Path

from core import mix_candidates as mc, mix_features, mix_taste, mixes_db, stats_db

NOW = 1_800_000_000


def item(track_id, artist, title, rank=1000, explicit=False, readable=True, preview="http://p"):
    return {"id": track_id, "title": title, "artist": {"name": artist}, "album": {"title": "Album"}, "rank": rank,
            "explicit_lyrics": explicit, "readable": readable, "preview": preview}


def cand(track_id, artist="A", title=None, **kw):
    return mc.parse(item(track_id or 1_000_000, artist, title or f"Song {track_id}", **kw))


def owned(*pairs):
    return mix_taste.owned_tracks([{"path": f"/m/{a}/{t}.flac", "tag_artist": a, "tag_title": t} for a, t in pairs])


class Base(unittest.TestCase):
    def setUp(self):
        for suffix in ("", "-wal", "-shm"):
            Path(f"{mixes_db.db_path()}{suffix}").unlink(missing_ok=True)
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)


class Parsing(unittest.TestCase):
    def test_reads_a_deezer_track(self):
        c = cand(5, "Vald", "Song (feat. X)", explicit=True)
        self.assertEqual((c.deezer_id, c.artist, c.explicit), ("5", "Vald", True))
        self.assertEqual(c.key, stats_db.track_key(["Vald"], "Song"))

    def test_unreadable_or_nameless_tracks_are_dropped(self):
        self.assertIsNone(mc.parse(item(1, "A", "S", readable=False)))
        self.assertIsNone(mc.parse(item(1, "", "S")))
        self.assertIsNone(mc.parse(item(1, "A", "")))


class Filtering(unittest.TestCase):
    def test_what_you_own_is_out_even_in_another_version(self):
        rules = mc.Exclusions(owned(("Vald", "Song")))
        self.assertFalse(rules.allows(cand(1, "Vald", "Song")))
        self.assertFalse(rules.allows(cand(2, "Vald", "Song (Live)")))
        self.assertTrue(rules.allows(cand(3, "Vald", "Other")))

    def test_removed_tracks_never_come_back(self):
        c = cand(1, "Vald", "Refused")
        self.assertFalse(mc.Exclusions([], known_ids=["1"]).allows(c))
        other_release = cand(2, "Vald", "Refused")
        self.assertFalse(mc.Exclusions([], rejected_keys=[c.key]).allows(other_release))

    def test_skits_are_out(self):
        self.assertFalse(mc.Exclusions([]).allows(cand(1, "A", "Intro")))

    def test_discovery_only_takes_what_you_never_played(self):
        c = cand(1, "Vald", "Heard elsewhere")
        rules = mc.Exclusions([], played={c.key: 3}, never_played_only=True)
        self.assertFalse(rules.allows(c))
        self.assertTrue(rules.allows(cand(2, "Vald", "Never heard")))

    def test_the_explicit_version_wins(self):
        clean, explicit = cand(1, "A", "Song", rank=9000), cand(2, "A", "Song", rank=10, explicit=True)
        self.assertEqual([c.deezer_id for c in mc.distinct_versions([clean, explicit])], ["2"])


class Selecting(unittest.TestCase):
    def pick(self, candidates, want=5, per_artist=2, seeds=None, tempo=lambda c: None):
        return mc.select(candidates, mc.Exclusions([]), want, per_artist, random.Random(1), seeds, tempo)

    def test_keeps_spares_for_failed_downloads(self):
        pool = [cand(i, f"A{i}") for i in range(30)]
        self.assertEqual(len(self.pick(pool)), 5 * mc.SPARE_FACTOR)

    def test_limits_each_artist(self):
        picks = self.pick([cand(i, "Same") for i in range(30)])
        self.assertEqual(len(picks), 2)

    def test_a_preview_at_another_tempo_rules_a_track_out(self):
        slow = [cand(i, f"Slow{i}") for i in range(10)]
        fast = [cand(i + 100, f"Fast{i}") for i in range(10)]
        tempo = lambda c: 134 if c.artist.startswith("Fast") else 100
        picks = self.pick(slow + fast, seeds=[(100, 1)], tempo=tempo)
        self.assertEqual({c.artist[:4] for c in picks}, {"Slow"})

    def test_no_preview_does_not_rule_a_track_out(self):
        self.assertTrue(self.pick([cand(1)], seeds=[(100, 1)]))

    def test_previews_are_not_fetched_without_a_seed_tempo(self):
        calls = []
        self.pick([cand(1)], tempo=lambda c: calls.append(c))
        self.assertEqual(calls, [])

    def test_stops_measuring_after_a_limit(self):
        calls = []
        def tempo(c):
            calls.append(c)
            return 200.5 * 0.7
        self.pick([cand(i, f"A{i}") for i in range(300)], want=100, seeds=[(100, 1)], tempo=tempo)
        self.assertEqual(len(calls), mc.MAX_PREVIEW_CHECKS)


class RelatedCache(Base):
    def test_asks_deezer_once_within_two_weeks(self):
        calls = []
        def api(path, params=None):
            calls.append(path)
            return {"data": [{"id": 9, "name": "Near"}]}
        self.assertEqual(mc.related_artists(self.conn, "1", NOW, api), [{"id": "9", "name": "Near"}])
        mc.related_artists(self.conn, "1", NOW + 86400, api)
        self.assertEqual(len(calls), 1)
        mc.related_artists(self.conn, "1", NOW + 15 * 86400, api)
        self.assertEqual(len(calls), 2)


class Pools(Base):
    def fake_api(self, path, params=None):
        if path.endswith("/related"):
            return {"data": [{"id": 50, "name": "Near"}]}
        artist = path.split("/")[2]
        return {"data": [item(int(artist) * 100 + i, f"Artist {artist}", f"Top {i}") for i in range(3)]}

    def test_an_artist_seed_only_looks_at_that_artist(self):
        seed = mix_taste.Seed("artist", "bad bunny", "Bad Bunny", "bad bunny", 1.0, artists={"bad bunny"})
        pool = mc.seed_pool(self.conn, seed, {"bad bunny": "7"}, NOW, self.fake_api)
        self.assertEqual({c.artist for c in pool}, {"Artist 7"})

    def test_a_track_seed_adds_close_artists(self):
        seed = mix_taste.Seed("track", "x|y", "Y", "x", 1.0, artists={"x"})
        pool = mc.seed_pool(self.conn, seed, {"x": "7"}, NOW, self.fake_api)
        self.assertEqual({c.artist for c in pool}, {"Artist 7", "Artist 50"})

    def test_an_artist_unknown_to_deezer_gives_nothing_without_failing(self):
        seed = mix_taste.Seed("artist", "x", "X", "x", 1.0, artists={"x"})
        self.assertEqual(mc.seed_pool(self.conn, seed, {}, NOW, self.fake_api), [])

    def test_a_deezer_failure_does_not_stop_the_pool(self):
        def api(path, params=None):
            raise RuntimeError("down")
        seed = mix_taste.Seed("track", "x|y", "Y", "x", 1.0, artists={"x"})
        self.assertEqual(mc.seed_pool(self.conn, seed, {"x": "7"}, NOW, api), [])

    def test_habits_favor_artists_close_to_several_favorites(self):
        def api(path, params=None):
            source = path.split("/")[2]
            if path.endswith("/related"):
                return {"data": [{"id": 500, "name": "Shared"}, {"id": int(source) + 1000, "name": "Own"}]}
            return {"data": [item(int(source) * 100, f"Artist {source}", "Top")]}
        taste = mix_taste.Taste({}, {}, {}, {"a": 5.0, "b": 4.0}, {})
        pool = mc.habit_pool(self.conn, taste, {"a": "1", "b": "2"}, NOW, api)
        self.assertEqual(pool[0].artist, "Artist 500")

    def test_releases_skip_guest_appearances_and_old_ones(self):
        releases = [
            {"id": "1", "title": "New", "release_date": "2026-11-01", "featured": False},
            {"id": "2", "title": "Guest", "release_date": "2026-11-01", "featured": True},
            {"id": "3", "title": "Old", "release_date": "2026-01-01", "featured": False},
        ]
        seen = []
        def api(path, params=None):
            seen.append(path)
            return {"data": [item(11, "A", "Song")]}
        pool = mc.release_pool(releases, "2026-09-01", api)
        self.assertEqual(seen, ["/album/1/tracks"])
        self.assertEqual(pool[0].album, "Album")


class Features(Base):
    def test_measures_once_and_again_when_a_file_changes(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "a.flac"
        path.write_bytes(b"not audio")
        entry = {"path": str(path), "mtime_ns": 1}
        self.assertEqual(mix_features.status(self.conn, [entry]), {"total": 1, "left": 1})
        self.assertEqual(mix_features.analyze(self.conn, [entry]), 1)
        self.assertEqual(mix_features.status(self.conn, [entry])["left"], 0)
        self.assertEqual(mix_features.features_map(self.conn), {str(path): (None, None)})
        self.assertEqual(mix_features.pending(self.conn, [{**entry, "mtime_ns": 2}]), [{**entry, "mtime_ns": 2}])

    def test_can_be_stopped_and_resumed(self):
        entries = [{"path": f"/none/{i}.flac", "mtime_ns": 1} for i in range(5)]
        seen = []
        stop = lambda: seen.append(1) or len(seen) > 2
        self.assertEqual(mix_features.analyze(self.conn, entries, should_stop=stop), 2)
        self.assertEqual(len(mix_features.pending(self.conn, entries)), 3)


if __name__ == "__main__":
    unittest.main()
