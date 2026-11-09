import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import config, migrations, mixes_db, navidrome_db, nd_accounts, publish
from core.deezer import accounts_for, load_playlists, save_playlists, write_playlist_outputs
from tests.fake_subsonic import FakeSubsonic

ALICE = ("alice", "alice-pass-SENTINEL")


def navidrome_database(path, songs, users=(("uid-alice", "alice", True), ("uid-bob", "bob", False)),
                       rights=None, playlists=()):
    """songs: (id, relative path, library id). rights: user id -> library ids."""
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE library (id INTEGER PRIMARY KEY, name TEXT, path TEXT);
        CREATE TABLE media_file (id TEXT PRIMARY KEY, path TEXT, library_id INTEGER, missing INTEGER DEFAULT 0);
        CREATE TABLE user (id TEXT PRIMARY KEY, user_name TEXT, name TEXT, is_admin INTEGER);
        CREATE TABLE user_library (user_id TEXT, library_id INTEGER);
        CREATE TABLE playlist (id TEXT PRIMARY KEY, name TEXT, path TEXT, owner_id TEXT, sync INTEGER DEFAULT 0);
        INSERT INTO library VALUES (1, 'Music', '/music'), (2, 'Other', '/music/B');
    """)
    conn.executemany("INSERT INTO media_file(id, path, library_id) VALUES (?, ?, ?)", songs)
    conn.executemany("INSERT INTO user(id, user_name, name, is_admin) VALUES (?, ?, ?, ?)",
                     [(u, n, n, int(a)) for u, n, a in users])
    for user_id, libraries in (rights or {u: [1, 2] for u, _, _ in users}).items():
        conn.executemany("INSERT INTO user_library VALUES (?, ?)", [(user_id, lib) for lib in libraries])
    conn.executemany("INSERT INTO playlist(id, name, path, owner_id, sync) VALUES (?, ?, ?, ?, 1)", playlists)
    conn.commit()
    conn.close()


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.library = self.root / "library"
        self.playlists_dir = self.root / "playlists"
        for directory in (self.library / "A", self.playlists_dir):
            directory.mkdir(parents=True)
        self.nav = self.root / "navidrome.db"
        mappings = {self.library: Path("/music"), self.playlists_dir: Path("/playlists")}
        paths = ([self.library], self.playlists_dir, self.root / "cache.json", mappings)
        patches = [
            mock.patch("core.config.get_paths_from_config", return_value=paths),
            mock.patch("core.deezer.get_paths_from_config", return_value=paths),
            mock.patch.dict(os.environ, {"STATS_NAVIDROME_DB": str(self.nav)}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        Path(config.DATA_DIR, "navidrome_accounts.json").unlink(missing_ok=True)
        save_playlists([])
        config.save_preview_state({})
        conn = mixes_db.connect()
        conn.execute("DELETE FROM publications")
        conn.commit()
        conn.close()
        navidrome_db.forget()
        navidrome_db.forget_songs()
        self.addCleanup(navidrome_db.forget_songs)
        self.server = FakeSubsonic().start()
        self.addCleanup(self.server.stop)
        self.server.add_user(*ALICE, admin=True)
        self.server.add_user("bob", "bob-pass")
        for number in range(1, 5):
            self.server.add_song(f"s{number}", f"Song {number}", "A", folder=1)
        self.server.add_song("s9", "Elsewhere", "A", folder=2)
        navidrome_database(self.nav, [(f"s{n}", f"A/{n}.flac", 1) for n in range(1, 5)] + [("s9", "9.flac", 2)])
        nd_accounts.ensure_initial()
        self.alice = nd_accounts.create({"label": "Alice", "url": self.server.url, "username": ALICE[0],
                                         "secret": ALICE[1]})["id"]
        nd_accounts.record_test(self.alice, {"ok": True, "admin": True}, {"id": "uid-alice", "user_name": "alice"})

    def rows(self, numbers):
        return [{"number": i, "matched": True, "local_path": str(self.library / "A" / f"{n}.flac"),
                 "deezer_name": f"A - Song {n}", "deezer_artist": "A", "deezer_title": f"Song {n}"}
                for i, n in enumerate(numbers, start=1)]

    def save(self, playlist_id, title, accounts, numbers=(1, 2)):
        save_playlists([*load_playlists(), {"id": playlist_id, "title": title, "picture": "", "accounts": accounts}])
        config.update_preview_state(playlist_id, {"playlist_id": playlist_id, "playlist_title": title,
                                                  "rows": self.rows(numbers)})

    def made(self, owner="alice"):
        return [p for p in self.server.playlists.values() if p["owner"] == owner]

    def publication(self, playlist_id, account_id):
        conn = mixes_db.connect()
        try:
            row = conn.execute("SELECT * FROM publications WHERE playlist_id=? AND account_id=?",
                               (playlist_id, account_id)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


class Files(Base):
    def test_the_install_account_still_gets_the_same_m3u8_and_no_api_call(self):
        self.save("111", "Road trip", ["nd1"])
        path, report = publish.publish("111", "Road trip", self.rows([1, 2]))
        self.assertTrue(path.exists())
        expected_dir = self.root / "expected"
        with mock.patch("core.deezer.get_paths_from_config",
                        return_value=([self.library], expected_dir, self.root / "cache.json",
                                      {self.library: Path("/music"), expected_dir: Path("/playlists")})):
            expected, _ = write_playlist_outputs("111", "Road trip", self.rows([1, 2]))
        self.assertEqual(path.read_bytes(), expected.read_bytes())
        self.assertEqual(report["matched_count"], 2)
        self.assertEqual(self.server.requests, [])

    def test_an_api_account_gets_no_file(self):
        self.save("112", "Mine", [self.alice])
        path, report = publish.publish("112", "Mine", self.rows([1]), wait=True)
        self.assertIsNone(path)
        self.assertEqual(report["matched_count"], 1)
        self.assertFalse((self.playlists_dir / "Mine").exists())


class Api(Base):
    def test_made_as_the_user_private_in_order_and_marked(self):
        self.save("113", "Road trip", [self.alice], numbers=(3, 1, 2))
        publish.publish("113", "Road trip", self.rows([3, 1, 2]), wait=True)
        made = self.made()
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["songs"], ["s3", "s1", "s2"])
        self.assertEqual(made[0]["comment"], publish.COMMENT)
        self.assertFalse(made[0]["public"])
        pub = self.publication("113", self.alice)
        self.assertEqual((pub["song_count"], pub["missing"], pub["error"]), (3, 0, ""))

    def test_unchanged_sends_nothing_and_a_change_keeps_the_id(self):
        self.save("114", "Mix", [self.alice])
        publish.publish("114", "Mix", self.rows([1, 2]), wait=True)
        first = self.made()[0]["id"]
        calls = len(self.server.requests)
        publish.publish("114", "Mix", self.rows([1, 2]), wait=True)
        self.assertEqual(len(self.server.requests), calls)
        publish.publish("114", "Mix renamed", self.rows([2, 4]), wait=True)
        made = self.made()
        self.assertEqual([p["id"] for p in made], [first])
        self.assertEqual((made[0]["name"], made[0]["songs"]), ("Mix renamed", ["s2", "s4"]))

    def test_deleted_in_navidrome_an_update_takes_it_off_this_account(self):
        self.save("115", "Mix", ["nd1", self.alice])
        publish.publish("115", "Mix", self.rows([1]), wait=True)
        self.server.playlists.clear()
        publish.publish("115", "Mix", self.rows([1, 2]), wait=True)
        self.assertEqual(self.made(), [])
        self.assertEqual(accounts_for("115"), ["nd1"])
        self.assertIsNone(self.publication("115", self.alice))

    def test_forced_publication_replaces_an_edit_made_in_navidrome(self):
        self.save("116", "Mix", [self.alice])
        publish.publish("116", "Mix", self.rows([1, 2]), wait=True)
        self.made()[0]["songs"] = ["s4"]
        publish.publish("116", "Mix", self.rows([1, 2]), force=True, wait=True)
        self.assertEqual(self.made()[0]["songs"], ["s1", "s2"])

    def test_a_song_navidrome_does_not_know_yet_is_added_later(self):
        (self.library / "A" / "new.flac").write_bytes(b"x")
        rows = self.rows([1]) + [{"number": 2, "matched": True, "local_path": str(self.library / "A" / "new.flac")}]
        self.save("117", "Fresh", [self.alice])
        config.update_preview_state("117", {"playlist_title": "Fresh", "rows": rows})
        publish.publish("117", "Fresh", rows, wait=True)
        self.assertEqual(self.publication("117", self.alice)["missing"], 1)
        navidrome_database(self.nav, [("s1", "A/1.flac", 1), ("s5", "A/new.flac", 1)])
        self.server.add_song("s5", "New", "A")
        navidrome_db.forget_songs()
        self.assertEqual(publish.retry_pending(now=time.time() + publish.RETRY_AFTER + 1), 1)
        self.assertTrue(publish.flush(30))
        self.assertEqual(self.made()[0]["songs"], ["s1", "s5"])
        self.assertEqual(self.publication("117", self.alice)["missing"], 0)

    def test_songs_this_user_may_not_see_are_left_out_and_counted(self):
        navidrome_database(self.nav, [("s1", "A/1.flac", 1), ("s9", "9.flac", 2)],
                           rights={"uid-alice": [1], "uid-bob": [1, 2]})
        rows = self.rows([1]) + [{"number": 2, "matched": True, "local_path": str(self.library / "B" / "9.flac")}]
        self.save("118", "Mix", [self.alice])
        publish.publish("118", "Mix", rows, wait=True)
        self.assertEqual(self.made()[0]["songs"], ["s1"])
        pub = self.publication("118", self.alice)
        self.assertEqual((pub["hidden"], pub["missing"]), (1, 0))

    def test_navidrome_down_is_kept_and_never_raises(self):
        self.save("119", "Mix", [self.alice])
        self.server.stop()
        publish.publish("119", "Mix", self.rows([1]), wait=True)
        error = self.publication("119", self.alice)["error"]
        self.assertIn("Could not reach", error)
        self.assertNotIn(ALICE[1], error)
        account = next(a for a in publish.status("119")["accounts"] if a["id"] == self.alice)
        self.assertEqual(account["publication"]["error"], error)

    def test_an_account_without_its_password_says_so(self):
        nd_accounts.update("nd1", {"url": "http://nowhere:4533", "username": "x"})
        nd_accounts.set_publish_mode("nd1", "api")
        self.save("120", "Mix", ["nd1"])
        publish.publish("120", "Mix", self.rows([1]), wait=True)
        self.assertIn("address and password", self.publication("120", "nd1")["error"])

    def test_in_the_background_by_default(self):
        self.save("121", "Mix", [self.alice])
        publish.publish("121", "Mix", self.rows([1]))
        self.assertTrue(publish.flush(30))
        self.assertEqual(len(self.made()), 1)

    def test_unpublish_removes_only_what_the_app_made(self):
        self.server.playlists["other"] = {"id": "other", "name": "Own playlist", "owner": "alice", "comment": "",
                                          "public": False, "songs": [], "created": "", "changed": ""}
        self.save("122", "Mix", [self.alice])
        publish.publish("122", "Mix", self.rows([1]), wait=True)
        publish.unpublish("122")
        self.assertEqual(list(self.server.playlists), ["other"])
        self.assertIsNone(self.publication("122", self.alice))

    def test_each_account_its_own_playlist(self):
        bob = nd_accounts.create({"label": "Bob", "url": self.server.url, "username": "bob", "secret": "bob-pass"})["id"]
        self.save("123", "Shared", ["nd1", self.alice, bob])
        path, _ = publish.publish("123", "Shared", self.rows([1, 2]), wait=True)
        self.assertTrue(path.exists())
        self.assertEqual(len(self.made("alice")), 1)
        self.assertEqual(len(self.made("bob")), 1)
        publish.remove_from("123", "Shared", [self.alice])
        self.assertEqual(self.made("alice"), [])
        self.assertEqual(len(self.made("bob")), 1)
        self.assertTrue(path.exists())
        publish.remove_from("123", "Shared", ["nd1"])
        self.assertFalse(path.exists())


class RemovingAFile(Base):
    def test_the_copy_navidrome_imported_goes_too_when_the_account_can_sign_in(self):
        nd_accounts.delete(self.alice)
        nd_accounts.update("nd1", {"url": self.server.url, "username": "alice", "secret": ALICE[1]})
        self.save("141", "Gone", ["nd1"])
        path, _ = publish.publish("141", "Gone", self.rows([1]))
        navidrome_database(self.nav, [("s1", "A/1.flac", 1)],
                           playlists=[("copy-1", "Gone", "/playlists/Gone/Gone.m3u8", "uid-alice")])
        self.server.playlists["copy-1"] = {"id": "copy-1", "name": "Gone", "owner": "alice", "comment": "",
                                           "public": False, "songs": ["s1"], "created": "", "changed": ""}
        self.assertTrue(publish.remove_from("141", "Gone", ["nd1"]))
        self.assertFalse(path.exists())
        self.assertNotIn("copy-1", self.server.playlists)

    def test_without_its_password_it_says_a_copy_may_be_left(self):
        self.save("142", "Gone", ["nd1"])
        path, _ = publish.publish("142", "Gone", self.rows([1]))
        self.assertFalse(publish.remove_from("142", "Gone", ["nd1"]))
        self.assertFalse(path.exists())

    def test_nothing_to_remove_is_complete(self):
        self.save("143", "Never written", ["nd1"])
        self.assertTrue(publish.remove_from("143", "Never written", ["nd1"]))


class Sync(Base):
    """What the user does in Navidrome comes back to the app."""

    def publish_three(self):
        for pid, title in (("151", "One"), ("152", "Two"), ("153", "Three")):
            self.save(pid, title, ["nd1", self.alice])
            publish.publish(pid, title, self.rows([1]), wait=True)

    def by_name(self, name):
        return next(p for p in self.server.playlists.values() if p["name"] == name)

    def test_deleted_there_it_leaves_the_account_and_the_app_when_it_was_the_last(self):
        self.publish_three()
        self.save("154", "Alone", [self.alice])
        publish.publish("154", "Alone", self.rows([2]), wait=True)
        del self.server.playlists[self.by_name("Two")["id"]]
        del self.server.playlists[self.by_name("Alone")["id"]]
        report = publish.sync_account(self.alice)
        self.assertEqual(sorted(report["removed"]), ["Alone", "Two"])
        self.assertEqual(accounts_for("152"), ["nd1"])
        self.assertNotIn("154", {p["id"] for p in load_playlists()})
        self.assertEqual(accounts_for("151"), ["nd1", self.alice])

    def test_all_gone_at_once_is_navidrome_losing_them_so_they_come_back(self):
        self.publish_three()
        self.server.playlists.clear()
        report = publish.sync_account(self.alice)
        self.assertEqual((report["removed"], report["republished"]), ([], 3))
        self.assertIn("published again", report["warning"])
        self.assertTrue(publish.flush(30))
        self.assertEqual(sorted(p["name"] for p in self.made()), ["One", "Three", "Two"])
        self.assertEqual(accounts_for("152"), ["nd1", self.alice])

    def test_a_name_given_there_is_kept_and_never_sent_back(self):
        self.save("155", "Deezer name", [self.alice])
        publish.publish("155", "Deezer name", self.rows([1]), wait=True)
        self.by_name("Deezer name")["name"] = "My name"
        self.assertEqual(publish.sync_account(self.alice)["renamed"], 1)
        self.assertEqual(publish.custom_titles(self.alice), {"155": "My name"})
        publish.publish("155", "New Deezer name", self.rows([1, 2]), wait=True)
        self.assertEqual(self.made()[0]["name"], "My name")
        self.assertEqual(self.made()[0]["songs"], ["s1", "s2"])

    def test_the_original_name_given_back_hands_the_name_back_to_the_app(self):
        self.save("156", "Original", [self.alice])
        publish.publish("156", "Original", self.rows([1]), wait=True)
        self.by_name("Original")["name"] = "Mine"
        publish.sync_account(self.alice)
        self.by_name("Mine")["name"] = "Original"
        publish.sync_account(self.alice)
        self.assertEqual(publish.custom_titles(self.alice), {})
        publish.publish("156", "Renamed on Deezer", self.rows([1]), wait=True)
        self.assertEqual(self.made()[0]["name"], "Renamed on Deezer")

    def test_playlists_made_by_hand_are_listed_but_not_those_of_the_app_or_others(self):
        self.save("157", "From the app", [self.alice])
        publish.publish("157", "From the app", self.rows([1]), wait=True)
        for pid, owner, name, comment in (("hand-1", "alice", "By hand", ""), ("bob-1", "bob", "Bob's", ""),
                                          ("lost-1", "alice", "Lost app copy", publish.COMMENT)):
            self.server.playlists[pid] = {"id": pid, "name": name, "owner": owner, "comment": comment, "public": False,
                                          "songs": ["s1", "s2"], "created": "", "changed": ""}
        report = publish.sync_account(self.alice)
        self.assertEqual(report["handmade"], 1)
        handmade = publish.handmade(self.alice)
        self.assertEqual([(p["navidrome_id"], p["name"], p["song_count"]) for p in handmade], [("hand-1", "By hand", 2)])
        self.assertEqual(handmade[0]["cover_art"], "pl-hand-1")

    def test_an_account_with_m3u8_files_is_never_taken_off_anything(self):
        nd_accounts.delete(self.alice)
        nd_accounts.update("nd1", {"url": self.server.url, "username": "alice", "secret": ALICE[1]})
        self.save("158", "File one", ["nd1"])
        publish.publish("158", "File one", self.rows([1]))
        report = publish.sync_account("nd1")
        self.assertEqual(report["removed"], [])
        self.assertEqual(accounts_for("158"), ["nd1"])

    def test_the_m3u8_copies_of_the_app_are_not_made_by_hand(self):
        nd_accounts.delete(self.alice)
        nd_accounts.update("nd1", {"url": self.server.url, "username": "alice", "secret": ALICE[1]})
        navidrome_database(self.nav, [("s1", "A/1.flac", 1)],
                           playlists=[("file-1", "Road trip", "/playlists/Road trip/Road trip.m3u8", "uid-alice")])
        for pid, name in (("file-1", "Road trip"), ("own-1", "Own")):
            self.server.playlists[pid] = {"id": pid, "name": name, "owner": "alice", "comment": "", "public": False,
                                          "songs": [], "created": "", "changed": ""}
        publish.sync_account("nd1")
        self.assertEqual([p["name"] for p in publish.handmade("nd1")], ["Own"])

    def test_navidrome_down_is_said_and_changes_nothing(self):
        self.publish_three()
        self.server.stop()
        report = publish.sync_account(self.alice)
        self.assertIn("Could not reach", report["error"])
        self.assertEqual(accounts_for("151"), ["nd1", self.alice])
        self.assertEqual(publish.sync_report(self.alice)["error"], report["error"])

    def test_an_account_without_its_password_is_not_synced(self):
        self.assertIsNone(publish.sync_account("nd1"))

    def test_a_recent_sync_is_not_started_again(self):
        publish.sync_account(self.alice)
        self.assertFalse(publish.sync_soon(self.alice))


class WithoutTheDatabase(Base):
    def test_songs_are_searched_by_their_tags(self):
        self.nav.unlink()
        (self.root / "cache.json").write_text(json.dumps({"library": [
            {"path": str(self.library / "A" / "1.flac"), "tag_title": "Song 1", "tag_artist": "A", "duration": 200},
            {"path": str(self.library / "A" / "2.flac"), "tag_title": "Unknown here", "tag_artist": "A", "duration": 200},
        ]}), encoding="utf-8")
        self.save("124", "Mix", [self.alice])
        publish.publish("124", "Mix", self.rows([1, 2]), wait=True)
        self.assertEqual(self.made()[0]["songs"], ["s1"])
        self.assertEqual(self.publication("124", self.alice)["missing"], 1)


class Switching(Base):
    def setUp(self):
        super().setUp()
        # nd1 is the install, signed in as alice here: the other account goes.
        nd_accounts.delete(self.alice)
        nd_accounts.update("nd1", {"url": self.server.url, "username": "alice", "secret": ALICE[1]})
        nd_accounts.record_test("nd1", {"ok": True, "admin": True}, {"id": "uid-alice", "user_name": "alice"})
        self.save("131", "Road trip", ["nd1"])
        self.save("132", "Never scanned", ["nd1"])
        config.save_preview_state({"131": config.get_preview_state("131")})
        self.file, _ = write_playlist_outputs("131", "Road trip", self.rows([1, 2]))
        navidrome_database(self.nav, [(f"s{n}", f"A/{n}.flac", 1) for n in range(1, 5)],
                           playlists=[("old-1", "Road trip", "/playlists/Road trip/Road trip.m3u8", "uid-alice"),
                                      ("mine", "By hand", "/playlists/By hand/By hand.m3u8", "uid-alice")])
        for pid, name in (("old-1", "Road trip"), ("mine", "By hand")):
            self.server.playlists[pid] = {"id": pid, "name": name, "owner": "alice", "comment": "", "public": False,
                                          "songs": ["s1"], "created": "", "changed": ""}

    def test_the_preview_says_what_will_change(self):
        preview = publish.switch_preview("nd1")
        self.assertTrue(preview["ok"], preview)
        self.assertEqual((preview["playlists"], preview["files"]), (2, 1))
        self.assertEqual(preview["old"], [{"name": "Road trip", "owner": "alice"}])

    def test_switch_publishes_then_removes_the_files_and_only_their_copies(self):
        report = publish.switch_to_api("nd1")
        self.assertEqual(nd_accounts.get("nd1")["publish_mode"], "api")
        self.assertFalse(self.file.exists())
        self.assertNotIn("old-1", self.server.playlists)
        self.assertIn("mine", self.server.playlists)
        made = [p for p in self.made() if p["comment"] == publish.COMMENT]
        self.assertEqual([p["name"] for p in made], ["Road trip"])
        self.assertEqual((report["published"], report["files_removed"], report["old_removed"]), (1, 1, 1))

    def test_a_refusal_undoes_everything(self):
        self.server.stop()
        with self.assertRaises(publish.SwitchError):
            publish.switch_to_api("nd1")
        self.assertEqual(nd_accounts.get("nd1")["publish_mode"], "m3u8")
        self.assertTrue(self.file.exists())

    def test_it_needs_a_tested_account(self):
        nd_accounts.update("nd1", {"username": "bob"})
        self.assertFalse(publish.switch_preview("nd1")["ok"])
        with self.assertRaises(publish.SwitchError):
            publish.switch_to_api("nd1")


class Migration(Base):
    def test_old_playlists_go_to_nd1_once_with_a_backup(self):
        config.PLAYLIST_IDS_FILE.write_text(json.dumps({"playlists": [
            {"id": "201", "title": "Old", "picture": ""},
            {"id": "202", "title": "Shared", "picture": "", "accounts": [self.alice]},
        ]}), encoding="utf-8")
        backup = Path(config.DATA_DIR) / "backups" / migrations.BACKUP_FOLDER / config.PLAYLIST_IDS_FILE.name
        backup.unlink(missing_ok=True)
        self.assertEqual(migrations.playlist_accounts(), 1)
        self.assertEqual(migrations.playlist_accounts(), 0)
        self.assertTrue(backup.exists())
        self.assertNotIn("accounts", backup.read_text(encoding="utf-8").split('"201"')[1].split("}")[0])
        self.assertEqual(accounts_for("201"), ["nd1"])
        self.assertEqual(accounts_for("202"), [self.alice])

    def test_a_publications_table_from_the_previous_build_gets_its_new_column(self):
        import sqlite3

        old = Path(tempfile.mkdtemp()) / "mixes.db"
        conn = sqlite3.connect(old)
        conn.execute("CREATE TABLE publications (playlist_id TEXT, account_id TEXT, navidrome_id TEXT, title TEXT,"
                     " content_hash TEXT, song_count INTEGER, missing INTEGER, hidden INTEGER, published_at INTEGER,"
                     " tried_at INTEGER, error TEXT, PRIMARY KEY (playlist_id, account_id))")
        conn.execute("INSERT INTO publications VALUES ('1', 'nd2', 'pl', 'T', '', 0, 0, 0, 0, 0, '')")
        conn.commit()
        conn.close()
        with mock.patch("core.mixes_db.db_path", return_value=old):
            conn = mixes_db.connect()
            row = dict(conn.execute("SELECT * FROM publications").fetchone())
            conn.close()
        self.assertEqual((row["title"], row["custom_title"]), ("T", ""))

    def test_a_save_keeps_the_accounts(self):
        self.save("203", "Kept", [self.alice])
        playlists = load_playlists()
        for playlist in playlists:
            playlist.pop("accounts")
        save_playlists(playlists)
        self.assertEqual(accounts_for("203"), [self.alice])


if __name__ == "__main__":
    unittest.main()
