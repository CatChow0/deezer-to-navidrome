import unittest

from core import stats_db
from core.stats_db import add_play, connect, play_count, split_artists, track_key, upsert_album, upsert_track


def reset():
    path = stats_db.db_path()
    for suffix in ("", "-wal", "-shm"):
        target = path.with_name(path.name + suffix)
        if target.exists():
            target.unlink()


class TrackKey(unittest.TestCase):
    def test_track_key_rules(self):
        k = track_key
        self.assertEqual(k(["Kendrick Lamar"], "Money Trees"), k(["Kendrick Lamar", "Jay Rock"], "Money Trees (feat. Jay Rock)"))
        self.assertEqual(k(["VALD"], "(EXCLU) VALD - SPORT"), k(["VALD"], "[EXCLU] VALD - SPORT (Feat. Vladimir Cauchemar & Todiefor)"))
        self.assertEqual(k(["Earth, Wind & Fire"], "Boogie Wonderland"), k(["Earth, Wind & Fire", "The Emotions"], "Boogie Wonderland (with The Emotions)"))
        self.assertEqual(k(["Beyoncé"], "Déjà Vu"), k(["beyonce"], "deja vu"))
        self.assertNotEqual(k(["A"], "Song"), k(["A"], "Song (Remix)"))
        self.assertNotEqual(k(["A"], "Song"), k(["A"], "Song - Live"))
        self.assertNotEqual(k(["宇多田ヒカル"], "光"), k(["宇多田ヒカル"], "誰かの願いが叶うころ"))
        self.assertTrue(k(["!!!"], "???"))  # all punctuation still yields a usable key

    def test_inline_feat_is_dropped(self):
        self.assertEqual(track_key(["A"], "Song feat. B"), track_key(["A"], "Song"))
        self.assertEqual(track_key(["A"], "Song ft B & C"), track_key(["A"], "Song"))

    def test_punctuation_only_names_stay_distinct(self):
        self.assertNotEqual(track_key(["!!!"], "???"), track_key(["!!!"], "..."))

    def test_split_artists(self):
        self.assertEqual(split_artists("Kendrick Lamar • Rihanna"), ["Kendrick Lamar", "Rihanna"])
        self.assertEqual(split_artists("Earth, Wind & Fire"), ["Earth, Wind & Fire"])
        self.assertEqual(split_artists(["A", " ", None]), ["A"])
        self.assertEqual(split_artists(None), [])
        self.assertEqual(split_artists(["A • B", "C"]), ["A", "B", "C"])


class Storage(unittest.TestCase):
    def setUp(self):
        reset()
        self.conn = connect()

    def tearDown(self):
        self.conn.close()

    def test_add_play_twice_is_one_play(self):
        track = upsert_track(self.conn, "Song", ["A"])
        self.assertTrue(add_play(self.conn, track, None, 200, 1000, "live"))
        self.assertFalse(add_play(self.conn, track, None, 200, 1000, "live"))
        self.assertEqual(play_count(self.conn), 1)

    def test_same_track_on_two_albums(self):
        first = upsert_track(self.conn, "Song", ["A"])
        second = upsert_track(self.conn, "Song (feat. B)", ["A", "B"])
        self.assertEqual(first, second)
        album_a = upsert_album(self.conn, "Album A", "A")
        album_b = upsert_album(self.conn, "Album B", "A")
        add_play(self.conn, first, album_a, 100, 1000, "live")
        add_play(self.conn, first, album_b, 130, 2000, "live")
        rows = self.conn.execute("SELECT album_id, duration_sec FROM plays ORDER BY listened_at").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(album_a, 100), (album_b, 130)])

    def test_upsert_keeps_known_values(self):
        track = upsert_track(self.conn, "Song", ["A"], duration=200, duration_source="navidrome", genre="Rap", genre_source="navidrome")
        upsert_track(self.conn, "Song", ["A"])
        row = self.conn.execute("SELECT duration_sec, genre FROM tracks WHERE id=?", (track,)).fetchone()
        self.assertEqual((row["duration_sec"], row["genre"]), (200, "Rap"))

    def test_empty_album_has_no_id(self):
        self.assertIsNone(upsert_album(self.conn, "", "A"))

    def test_track_credits_every_artist_once(self):
        track = upsert_track(self.conn, "Song", ["A", "B", "A"])
        names = [r[0] for r in self.conn.execute(
            "SELECT a.name FROM track_artists ta JOIN artists a ON a.id=ta.artist_id WHERE ta.track_id=? ORDER BY ta.position", (track,))]
        self.assertEqual(names, ["A", "B"])

    def test_meta_round_trip(self):
        stats_db.set_meta(self.conn, "report", {"added": 3})
        self.assertEqual(stats_db.get_meta(self.conn, "report"), {"added": 3})
        self.assertEqual(stats_db.get_meta(self.conn, "nothing", 7), 7)


if __name__ == "__main__":
    unittest.main()
