"""Each Navidrome account has its own listening history: its own database, its
own ListenBrainz token, its own Navidrome user's plays."""
import ast
import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from core import config, nd_accounts, stats_covers, stats_db, stats_enrich, stats_import, stats_ingest, stats_queries
from tests.fixtures import add_navidrome_users, make_maloja, make_navidrome
from tests.test_stats_db import reset

BASE_TIME = 1700000000
REPO = Path(__file__).resolve().parent.parent


def listen(ts, title, artist="A"):
    return {"listened_at": BASE_TIME + ts, "track_metadata": {"track_name": title, "artist_name": artist, "release_name": "Album"}}


def fingerprint(account):
    with closing(stats_db.connect(account)) as conn:
        rows = conn.execute(
            "SELECT p.listened_at, t.key, COALESCE(al.key, ''), COALESCE(p.duration_sec, -1), p.source"
            " FROM plays p JOIN tracks t ON t.id = p.track_id LEFT JOIN albums al ON al.id = p.album_id"
            " ORDER BY p.listened_at, t.key").fetchall()
    return hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest(), len(rows)


def titles(account):
    with closing(stats_db.connect(account)) as conn:
        return sorted(r[0] for r in conn.execute("SELECT t.title FROM plays p JOIN tracks t ON t.id = p.track_id"))


class Base(unittest.TestCase):
    def setUp(self):
        reset()
        data = Path(config.DATA_DIR)
        (data / "navidrome_accounts.json").unlink(missing_ok=True)
        shutil.rmtree(data / "backups" / "removed-accounts", True)
        shutil.rmtree(data / "stats_sources", True)
        for name in ("scrobble_token", "scrobble_token_nd2", "scrobble_token_nd3"):
            config.save_secret(name, "")
            self.addCleanup(config.save_secret, name, "")
        self.src = Path(tempfile.mkdtemp(prefix="d2n-accounts-"))
        self.addCleanup(shutil.rmtree, self.src, True)
        self.nav, self.mal = self.src / "navidrome.db", self.src / "malojadb.sqlite"
        patcher = mock.patch.dict(os.environ, {"STATS_NAVIDROME_DB": str(self.nav), "STATS_MALOJA_DB": str(self.mal)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("SCROBBLE_TOKEN", "SCROBBLE_TOKEN_ND2"):
            os.environ.pop(name, None)
        stats_import._library_cache.clear()
        Path(config.LIBRARY_CACHE_FILE).unlink(missing_ok=True)
        nd_accounts.ensure_initial()
        nd_accounts.update("nd1", {"label": "Alice", "url": "http://navidrome:4533", "username": "alice", "secret": "a-pass"})
        self.bob = nd_accounts.create({"label": "Bob", "url": "http://navidrome:4533", "username": "bob", "secret": "b-pass"})["id"]


class Storage(Base):
    def test_one_database_per_account_the_first_where_it_always_was(self):
        data = Path(config.DATA_DIR)
        self.assertEqual(stats_db.db_path("nd1"), data / "stats.db")
        self.assertEqual(stats_db.db_path("nd2"), data / "stats" / "nd2.db")
        for wrong in ("", None, "nd0", "../stats", "dz1", "nd2/../../x"):
            with self.assertRaises(ValueError):
                stats_db.db_path(wrong)
        with self.assertRaises(TypeError):
            stats_db.connect()
        stats_db.connect("nd2").close()
        self.assertEqual(stats_db.accounts_with_history(), ["nd2"])

    def test_no_code_opens_a_history_without_naming_the_account(self):
        """A forgotten account would read the first one's history: every call names it."""
        found = []
        for path in list((REPO / "core").glob("*.py")) + list((REPO / "routes").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and not node.args and not node.keywords:
                    owner = node.func.value
                    if isinstance(owner, ast.Name) and owner.id == "stats_db" and node.func.attr in ("connect", "db_path"):
                        found.append(f"{path.name}:{node.lineno}")
        self.assertEqual(found, [])


class LivePlays(Base):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def post(self, token, *items):
        return self.app.test_client().post("/apis/listenbrainz/1/submit-listens", json={"listen_type": "import", "payload": list(items)},
                                           headers={"Authorization": f"Token {token}"})

    def test_the_token_says_whose_play_it_is(self):
        config.save_secret("scrobble_token", "alice-token-123")
        stats_ingest.set_scrobble_token("nd2", "bob-token-456")
        self.assertEqual(self.post("alice-token-123", listen(1, "Alice song")).status_code, 200)
        self.assertEqual(self.post("bob-token-456", listen(2, "Bob song")).status_code, 200)
        self.assertEqual(self.post("nobody-789", listen(3, "Nobody")).status_code, 401)
        self.assertEqual(titles("nd1"), ["Alice song"])
        self.assertEqual(titles("nd2"), ["Bob song"])
        check = self.app.test_client().get("/apis/listenbrainz/1/validate-token", headers={"Authorization": "Token bob-token-456"})
        self.assertEqual(check.get_json()["user_name"], "bob")

    def test_two_accounts_cannot_share_a_token(self):
        config.save_secret("scrobble_token", "alice-token-123")
        with self.assertRaises(stats_ingest.TokenTaken):
            stats_ingest.set_scrobble_token("nd2", "alice-token-123")
        stats_ingest.set_scrobble_token("nd1", "alice-token-123")

    def test_the_environment_can_set_each_token(self):
        with mock.patch.dict(os.environ, {"SCROBBLE_TOKEN_ND2": "bob-from-env-1"}):
            self.assertTrue(stats_ingest.token_from_env("nd2"))
            self.assertEqual(stats_ingest.token_env_name("nd2"), "SCROBBLE_TOKEN_ND2")
            self.assertEqual(self.post("bob-from-env-1", listen(1, "Env song")).status_code, 200)
        self.assertEqual(titles("nd2"), ["Env song"])
        self.assertEqual(stats_ingest.token_env_name("nd1"), "SCROBBLE_TOKEN")

    def test_a_removed_account_keeps_its_history_aside_and_its_token_stops(self):
        stats_ingest.set_scrobble_token("nd2", "bob-token-456")
        self.post("bob-token-456", listen(1, "Bob song"))
        before = fingerprint("nd2")
        nd_accounts.delete("nd2")
        self.assertFalse(stats_db.db_path("nd2").exists())
        archives = list((Path(config.DATA_DIR) / "backups" / "removed-accounts").glob("nd2-*.db"))
        self.assertEqual(len(archives), 1)
        with closing(sqlite3.connect(archives[0])) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0], before[1])
        self.assertEqual(self.post("bob-token-456", listen(2, "Late")).status_code, 401)
        self.assertEqual(config.load_secret("scrobble_token_nd2"), "")


class Imports(Base):
    def navidrome(self, users=(("u1", "alice", True), ("u2", "bob", False))):
        make_navidrome(self.nav, [
            {"ts": BASE_TIME + 10, "title": "Alice one", "user": "u1"},
            {"ts": BASE_TIME + 20, "title": "Alice two", "user": "u1"},
            {"ts": BASE_TIME + 30, "title": "Bob one", "user": "u2"},
        ])
        if users:
            add_navidrome_users(self.nav, users)

    def test_each_profile_gets_its_navidrome_users_plays(self):
        self.navidrome()
        stats_import.run_import("nd1", "merge")
        stats_import.run_import("nd2", "merge")
        self.assertEqual(titles("nd1"), ["Alice one", "Alice two"])
        self.assertEqual(titles("nd2"), ["Bob one"])
        self.assertTrue(stats_db.db_path("nd2").with_name("nd2.db").exists())

    def test_the_user_found_by_the_test_wins_over_the_name(self):
        self.navidrome()
        nd_accounts.record_test("nd2", {"ok": True}, navidrome_user={"id": "u1", "user_name": "alice"})
        stats_import.run_import("nd2", "merge")
        self.assertEqual(titles("nd2"), ["Alice one", "Alice two"])

    def test_a_profile_without_a_navidrome_user_reads_nothing_from_navidrome(self):
        self.navidrome()
        carol = nd_accounts.create({"label": "Carol", "url": "http://navidrome:4533", "username": "carol", "secret": "c"})["id"]
        report = stats_import.run_import(carol, "merge")
        self.assertIn(stats_import.NO_USER, report["warnings"])
        self.assertEqual(titles(carol), [])
        with self.assertRaisesRegex(stats_import.ImportRefused, "Navidrome user"):
            stats_import.run_import(carol, "clean")

    def test_the_install_on_a_navidrome_with_one_player_keeps_its_plays(self):
        make_navidrome(self.nav, [{"ts": BASE_TIME + 10, "title": "Mine", "user": "someone"}])
        nd_accounts.update("nd1", {"username": "renamed"})
        stats_import.run_import("nd1", "merge")
        self.assertEqual(titles("nd1"), ["Mine"])
        stats_import.run_import("nd2", "merge")
        self.assertEqual(titles("nd2"), [])

    def test_maloja_belongs_to_the_install_only(self):
        self.navidrome()
        make_maloja(self.mal, [{"ts": BASE_TIME + 5000, "title": "Maloja only"}])
        report = stats_import.run_import("nd2", "merge")
        self.assertEqual(report["read_maloja"], 0)
        self.assertNotIn("Maloja only", titles("nd2"))
        status = stats_import.source_status("nd2")
        self.assertEqual((status["maloja"]["used"], status["maloja"]["owner"]), (False, "Alice"))
        self.assertEqual(stats_import.run_import("nd1", "merge")["read_maloja"], 1)
        self.assertIn("Maloja only", titles("nd1"))

    def test_backups_stay_beside_each_history(self):
        self.navidrome()
        stats_import.run_import("nd2", "merge")
        report = stats_import.run_import("nd2", "merge")
        self.assertTrue((Path(config.DATA_DIR) / "stats" / report["backup"]).exists())
        self.assertEqual(list(Path(config.DATA_DIR).glob("stats.db.bak-*")), [])


class Upgrade(Base):
    def test_the_installs_history_is_the_same_after_the_upgrade(self):
        from core import migrations

        stats_ingest.record_listens("nd1", [listen(i, f"Song {i}", f"Artist {i % 3}") for i in range(40)])
        before = fingerprint("nd1")
        (Path(config.DATA_DIR) / "navidrome_accounts.json").unlink()
        migrations.run()
        migrations.run()
        self.assertEqual(fingerprint("nd1"), before)
        self.assertEqual(before[1], 40)
        self.assertTrue((Path(config.DATA_DIR) / "stats.db").exists())
        self.assertFalse((Path(config.DATA_DIR) / "stats" / "nd1.db").exists())


class Routes(Base):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"})
        patcher.start()
        self.addCleanup(patcher.stop)
        stats_ingest.record_listens("nd1", [listen(1, "Alice song"), listen(2, "Alice again")])
        stats_ingest.record_listens("nd2", [listen(3, "Bob song")])
        self.client = self.app.test_client()

    def total(self, **headers):
        return self.client.get("/api/stats/overview?period=all&tz=UTC", headers=headers).get_json()["totals"]["plays"]

    def test_the_stats_follow_the_profile(self):
        self.assertEqual(self.total(), 2)
        self.assertEqual(self.client.post("/api/navidrome/active", json={"id": "nd2"}).status_code, 200)
        self.assertEqual(self.total(), 1)
        self.assertEqual(self.total(**{"X-Navidrome-Account": "nd1"}), 2)
        tracks = self.client.get("/api/stats/overview?period=all&tz=UTC").get_json()["top"]["tracks"]
        self.assertEqual([t["title"] for t in tracks], ["Bob song"])
        plays = self.client.get("/api/stats/plays").get_json()
        self.assertEqual(plays["total"], 1)

    def test_covers_carry_their_account(self):
        self.client.post("/api/navidrome/active", json={"id": "nd2"})
        data = self.client.get("/api/stats/overview?period=all&tz=UTC").get_json()
        images = [row["image"] for rows in data["top"].values() for row in rows if row["image"]]
        self.assertTrue(images)
        self.assertTrue(all("a=nd2" in image for image in images), images)
        with mock.patch.object(stats_covers, "cover_for", return_value=None) as cover:
            self.client.get("/stats/cover/track/1?a=nd1")
            self.client.get("/stats/cover/track/1")
            self.client.get("/stats/cover/track/1?a=nd9")
        self.assertEqual([c.args[0] for c in cover.call_args_list], ["nd1", "nd2", "nd2"])

    def test_status_and_token_are_the_profiles(self):
        config.save_secret("scrobble_token", "alice-token-123")
        self.client.post("/api/navidrome/active", json={"id": "nd2"})
        status = self.client.get("/api/stats/status").get_json()
        self.assertEqual((status["account"]["id"], status["account"]["username"], status["token"]), ("nd2", "bob", ""))
        self.assertEqual(status["plays"], 1)
        self.assertEqual(status["token_env"], "SCROBBLE_TOKEN_ND2")
        self.assertFalse(status["sources"]["maloja"]["used"])
        made = self.client.post("/api/stats/token", json={}).get_json()["token"]
        self.assertEqual(config.load_secret("scrobble_token_nd2"), made)
        self.assertEqual(config.load_secret("scrobble_token"), "alice-token-123")
        taken = self.client.post("/api/stats/token", json={"token": "alice-token-123"})
        self.assertEqual(taken.status_code, 409)
        self.assertEqual(self.client.delete("/api/stats/token").status_code, 200)
        self.assertEqual(config.load_secret("scrobble_token_nd2"), "")
        self.assertEqual(config.load_secret("scrobble_token"), "alice-token-123")


class Shared(Base):
    """The library is the same for everyone: what one history learned serves the others."""

    def test_deezer_details_found_for_one_history_serve_the_other(self):
        stats_ingest.record_listens("nd1", [listen(1, "Shared")])
        stats_ingest.record_listens("nd2", [listen(2, "Shared")])
        with closing(stats_db.connect("nd1")) as conn:
            conn.execute("UPDATE tracks SET deezer_track_id='77', deezer_album_id='88', cover_url='http://c',"
                         " genre='Rap', genre_source='deezer', duration_sec=200, duration_source='deezer'")
            # An artist a played track gave: the other history takes it as it is.
            conn.execute("UPDATE artists SET picture_url='http://p', deezer_id='99', deezer_source='track'")
            conn.commit()
        with mock.patch("core.deezer._public_api", side_effect=AssertionError("no call expected")):
            stats_enrich.enrich_batch("nd2")
        with closing(stats_db.connect("nd2")) as conn:
            track = conn.execute("SELECT deezer_track_id, genre, duration_sec FROM tracks").fetchone()
            artist = conn.execute("SELECT picture_url, deezer_id, deezer_source FROM artists").fetchone()
        self.assertEqual(tuple(track), ("77", "Rap", 200))
        self.assertEqual(tuple(artist), ("http://p", "99", "track"))

    def test_a_cover_found_for_one_history_serves_the_other(self):
        stats_ingest.record_listens("nd1", [listen(1, "Shared")])
        stats_ingest.record_listens("nd2", [listen(2, "Other"), listen(3, "Shared")])
        folder = stats_covers.covers_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "abc123.jpg").write_bytes(b"\xff\xd8 not really")
        with closing(stats_db.connect("nd1")) as conn:
            key = conn.execute("SELECT key FROM tracks").fetchone()[0]
            conn.execute("INSERT INTO covers(kind, item_key, file, color, source, checked_at) VALUES ('track', ?, 'abc123.jpg', '#123456', 'file', 1)", (key,))
            conn.commit()
        with closing(stats_db.connect("nd2")) as conn:
            track_id = conn.execute("SELECT id FROM tracks WHERE key = ?", (key,)).fetchone()[0]
        with mock.patch("core.stats_covers.requests.get", side_effect=AssertionError("no download expected")):
            found = stats_covers.cover_for("nd2", "track", track_id)
        self.assertEqual(found.name, "abc123.jpg")

    def test_genres_and_moved_files_reach_every_history(self):
        from core import metadata_fix, trial

        stats_ingest.record_listens("nd2", [listen(1, "Only Bob", "B")])
        with closing(stats_db.connect("nd2")) as conn:
            conn.execute("UPDATE tracks SET genre='Jazz', file_path=?", (str(Path("/music/old.flac")),))
            conn.commit()
        stats_ingest.record_listens("nd1", [listen(2, "Alice", "A")])
        self.assertEqual(metadata_fix._genre_from_history("B", "Only Bob"), "Jazz")
        trial._follow_move(Path("/music/old.flac"), Path("/music/new.flac"))
        with closing(stats_db.connect("nd2")) as conn:
            self.assertEqual(conn.execute("SELECT file_path FROM tracks").fetchone()[0], str(Path("/music/new.flac")))

    def test_maloja_stays_the_installs_whatever_the_default(self):
        nd_accounts.set_default(self.bob)
        self.assertEqual(stats_import.maloja_account(), "nd1")


if __name__ == "__main__":
    unittest.main()
