"""Made for you per profile: each Navidrome account has its own settings, its own
mixes from its own history, published for it alone, and its own quarantine.
The install's account keeps everything where it was."""
import os
import sqlite3
from pathlib import Path
from unittest import mock

from core import config, mix_builder as mb, mixes_db, nd_accounts, stats_db, trial
from core.deezer import accounts_for, auto_id, is_auto_id, load_playlists, parse_auto_id, playlist_kind, save_playlists
from tests.test_mix_builder import DAY, NOW, Base
from tests.test_stats_db import reset


class Ids(Base):
    def test_the_install_keeps_its_ids_the_others_carry_theirs(self):
        self.assertEqual(auto_id("nd1", "daily", 1), "auto-daily-1")
        self.assertEqual(auto_id("nd2", "daily", 1), "auto-nd2-daily-1")
        self.assertEqual(auto_id("nd2", "discover"), "auto-nd2-discover")
        self.assertEqual(auto_id("nd1", "blend"), "auto-blend")
        self.assertEqual(parse_auto_id("auto-nd12-blend-3"), ("nd12", "blend", 3))
        self.assertEqual(parse_auto_id("auto-trial"), ("nd1", "trial", None))
        self.assertEqual(playlist_kind("auto-nd2-discover"), "auto")
        for wrong in ("auto-nd0-daily-1", "auto-nd2-daily-0", "auto-nd2", "auto-dz2-daily-1"):
            self.assertFalse(is_auto_id(wrong), wrong)


class Profiles(Base):
    def setUp(self):
        reset()
        super().setUp()
        (Path(config.DATA_DIR) / "navidrome_accounts.json").unlink(missing_ok=True)
        nd_accounts.ensure_initial()
        nd_accounts.update("nd1", {"label": "Alice", "url": "http://navidrome:4533", "username": "alice", "secret": "a"})
        self.bob = nd_accounts.create({"label": "Bob", "url": "http://navidrome:4533", "username": "bob", "secret": "b"})["id"]
        self.jobs = []
        for patcher in (mock.patch("core.publish._enqueue", side_effect=lambda pid, job: self.jobs.append((pid, job["accounts"]))),
                        mock.patch("core.trial.trash_dir", return_value=self.root / "trash")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bob_stats = stats_db.connect("nd2")
        self.addCleanup(self.bob_stats.close)

    def two_tastes(self):
        """Both own everything; Alice plays the A artists, Bob the B ones."""
        for prefix, stats in (("A", self.stats), ("B", self.bob_stats)):
            for a in range(6):
                for t in range(10):
                    self.own(f"{prefix}{a}", f"Song{t}", album=f"{prefix}Album{a}")
                    if t < 6:
                        track = stats_db.upsert_track(stats, f"Song{t}", [f"{prefix}{a}"], genre="Rock", genre_source="file")
                        album = stats_db.upsert_album(stats, f"{prefix}Album{a}", f"{prefix}{a}")
                        for i in range(6):
                            stats_db.add_play(stats, track, album, 200, NOW - DAY - i * 60, "navidrome")
        self.conn.commit()
        self.stats.commit()
        self.bob_stats.commit()

    def on_trial(self, account, deezer_id, artist="T", title=None):
        path = trial.trial_dir() / f"{artist} - {title or deezer_id}.flac"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        trial.add_download(self.conn, account, deezer_id, artist, title or f"Song {deezer_id}", "Album", path,
                           auto_id(account, "discover"), NOW)
        return path


class Mixes(Profiles):
    def test_each_profile_its_own_mixes_from_its_own_history(self):
        self.two_tastes()
        alice = mb.generate("nd1", ["daily"], now=NOW)["built"]["daily"]
        bob = mb.generate("nd2", ["daily"], now=NOW)["built"]["daily"]
        self.assertTrue(alice and bob)
        self.assertTrue(all(p.startswith("auto-daily-") for p in alice), alice)
        self.assertTrue(all(p.startswith("auto-nd2-daily-") for p in bob), bob)
        self.assertEqual((accounts_for(alice[0]), accounts_for(bob[0])), (["nd1"], ["nd2"]))
        alice_seeds = [s.split(":", 1)[1] for s in mixes_db.get_meta(self.conn, "seeds_daily")]
        bob_seeds = [s.split(":", 1)[1] for s in mixes_db.get_meta(self.conn, "nd2:seeds_daily")]
        self.assertTrue(alice_seeds and all(k.startswith("a") for k in alice_seeds), alice_seeds)
        self.assertTrue(bob_seeds and all(k.startswith("b") for k in bob_seeds), bob_seeds)
        # The install writes its files as before; Bob's mixes go to his Navidrome user, and to no one else.
        self.assertTrue((self.playlists_dir / "Daily Mix 1" / "Daily Mix 1.m3u8").exists())
        self.assertTrue(self.jobs and all(a == ["nd2"] for _, a in self.jobs), self.jobs)
        self.assertTrue(all(pid.startswith("auto-nd2-") for pid, _ in self.jobs))

    def test_another_profiles_mix_leaving_keeps_the_installs_file(self):
        self.two_tastes()
        mb.generate("nd1", ["daily"], now=NOW)
        mb.generate("nd2", ["daily"], now=NOW)
        mb.set_mix_mode(self.conn, "nd2", "off")
        ids = {p["id"] for p in load_playlists()}
        self.assertFalse([i for i in ids if i.startswith("auto-nd2-")])
        self.assertIn("auto-daily-1", ids)
        self.assertTrue((self.playlists_dir / "Daily Mix 1" / "Daily Mix 1.m3u8").exists())

    def test_settings_are_each_profiles_and_disk_limits_everyones(self):
        mb.save_settings(self.conn, "nd2", {"mix_size": 40, "max_trial_gb": 7, "trial_days": 9})
        alice, bob = mb.load_settings(self.conn, "nd1"), mb.load_settings(self.conn, "nd2")
        self.assertEqual((alice["mix_size"], bob["mix_size"]), (mb.DEFAULTS["mix_size"], 40))
        self.assertEqual((alice["trial_days"], bob["trial_days"]), (mb.DEFAULTS["trial_days"], 9))
        self.assertEqual((alice["max_trial_gb"], bob["max_trial_gb"]), (7, 7))
        self.assertIsNone(mixes_db.get_meta(self.conn, "settings"))
        self.assertIn("mix_size", mixes_db.get_meta(self.conn, "nd2:settings"))

    def test_the_limits_saved_before_profiles_are_kept(self):
        mixes_db.set_meta(self.conn, "settings", {"mix_mode": "daily", "max_trial_gb": 3, "max_unheard": 12})
        self.assertEqual(mb.load_settings(self.conn, "nd1")["mix_mode"], "daily")
        self.assertEqual(mb.load_settings(self.conn, "nd2")["mix_mode"], "off")
        self.assertEqual((mb.load_settings(self.conn, "nd2")["max_trial_gb"], mb.load_settings(self.conn, "nd2")["max_unheard"]), (3, 12))

    def test_one_profile_at_a_time(self):
        mb.set_mix_mode(self.conn, "nd1", "daily")
        mb.set_mix_mode(self.conn, "nd2", "daily")
        with mock.patch("core.mix_builder.start_task") as start, mock.patch("core.metadata_fix.start_background"):
            mb.tick(NOW)
            start.assert_called_once_with("nd1", ["daily"])
            mixes_db.set_meta(self.conn, "last_daily", NOW)
            mb.tick(NOW + 60)
            self.assertEqual(start.call_args.args, ("nd2", ["daily"]))
        self.assertEqual(mb.due_versions(self.conn, "nd2", NOW), ["daily"])
        self.assertEqual(mb.due_versions(self.conn, "nd1", NOW + 60), [])

    def test_discover_reads_the_releases_of_the_profiles_deezer_account(self):
        with mock.patch("core.account_context.deezer_account_of", side_effect=lambda a: {"nd1": "dz1", "nd2": "dz2"}[a]), \
                mock.patch("core.releases.load_releases", return_value={"releases": []}) as feed, \
                mock.patch("core.mix_builder.download_to_trial", return_value=[]):
            mb.generate("nd2", ["discover"], now=NOW)
        feed.assert_called_once_with("dz2")


class Quarantine(Profiles):
    def test_each_profile_sees_and_decides_its_own(self):
        self.on_trial("nd1", "1")
        self.on_trial("nd2", "2")
        self.assertEqual([r["deezer_id"] for r in trial.listing(self.conn, trial.ON_TRIAL, "nd2")], ["2"])
        self.assertEqual([r["deezer_id"] for r in trial.active(self.conn, "nd1")], ["1"])
        self.assertEqual(sorted(r["deezer_id"] for r in trial.active(self.conn, None)), ["1", "2"])
        self.assertEqual(trial.owners(self.conn), ["nd1", "nd2"])
        trial.remove(self.conn, "2", "nd2", NOW)
        self.assertEqual(len(trial.rejected(self.conn, "nd2")["keys"]), 1)
        self.assertEqual(trial.rejected(self.conn, "nd1")["keys"], set())

    def test_what_the_profile_had_or_anyone_kept_is_not_proposed_again(self):
        self.on_trial("nd2", "2")
        self.on_trial("nd2", "3")
        self.on_trial("nd1", "4")
        trial.keep(self.conn, "3", "nd2", NOW)
        ids = mb._Run(self.conn, self.stats, "nd1", NOW, "x").exclusions().ids
        self.assertNotIn("2", ids)
        self.assertIn("3", ids)
        self.assertIn("4", ids)

    def test_nobody_gets_anothers_tracks_on_trial_in_a_mix(self):
        self.two_tastes()
        path = self.on_trial("nd2", "2", artist="A0", title="Fresh")
        with mock.patch("core.mix_builder.download_to_trial", return_value=[]):
            built = mb.generate("nd1", ["blend"], now=NOW)["built"]["blend"]
        self.assertTrue(built)
        for playlist_id in built:
            paths = {r["local_path"] for r in config.get_preview_state(playlist_id)["rows"]}
            self.assertNotIn(str(path), paths)

    def test_the_owners_plays_and_rules_decide(self):
        path = self.on_trial("nd2", "2", artist="Bob Artist", title="Liked")
        self.on_trial("nd1", "1", artist="Bob Artist", title="Other")
        mb.save_settings(self.conn, "nd2", {"trial_plays": 1, "trial_bypass": True})
        track = stats_db.upsert_track(self.bob_stats, "Liked", ["Bob Artist"])
        stats_db.add_play(self.bob_stats, track, None, 200, NOW + 10, "live")
        track = stats_db.upsert_track(self.bob_stats, "Other", ["Bob Artist"])
        stats_db.add_play(self.bob_stats, track, None, 200, NOW + 20, "live")
        self.bob_stats.commit()
        report = mb.review_quarantine(NOW + 30)
        self.assertEqual(report["kept"], 1)
        self.assertEqual(trial.get(self.conn, "2", "nd2")["state"], trial.KEPT)
        self.assertFalse(path.exists())
        # Bob's play of the same song does not count for Alice's track.
        self.assertEqual(trial.get(self.conn, "1", "nd1")["state"], trial.ON_TRIAL)

    def test_only_the_owners_stars_count(self):
        db = self.root / "navidrome.db"
        nd = sqlite3.connect(db)
        nd.executescript("""
            CREATE TABLE user (id TEXT PRIMARY KEY, user_name TEXT);
            INSERT INTO user VALUES ('u1', 'alice'), ('u2', 'bob');
            CREATE TABLE media_file (id TEXT PRIMARY KEY, path TEXT);
            CREATE TABLE annotation (user_id TEXT, item_id TEXT, item_type TEXT, starred INT, rating INT);
            INSERT INTO media_file VALUES ('a', 'trial/T - Mine.flac'), ('b', 'trial/T - His.flac');
            INSERT INTO annotation VALUES ('u2', 'a', 'media_file', 1, 5), ('u2', 'b', 'media_file', 1, 0);
        """)
        nd.commit()
        nd.close()
        self.on_trial("nd1", "1", title="Mine")
        self.on_trial("nd2", "2", title="His")
        trial._marks_cache.clear()
        with mock.patch("core.stats_import._navidrome_path", return_value=db):
            self.assertEqual(trial.navidrome_marks(self.conn, "nd1", NOW), {})
            self.assertEqual(trial.navidrome_marks(self.conn, "nd2", NOW), {"2": {"starred": True, "rating": 0}})

    def test_the_disk_limits_count_everyones_tracks(self):
        self.on_trial("nd1", "1")
        self.on_trial("nd2", "2")
        self.assertEqual(trial.usage(self.conn, {})["unheard"], 2)
        self.assertEqual(trial.usage(self.conn, {}, "nd2")["unheard"], 1)


class Removal(Profiles):
    def test_a_removed_profile_leaves_nothing_behind(self):
        self.two_tastes()
        mb.generate("nd1", ["daily"], now=NOW)
        mb.generate("nd2", ["daily"], now=NOW)
        mb.save_settings(self.conn, "nd2", {"mix_size": 40})
        self.on_trial("nd2", "2")
        save_playlists([*load_playlists(), {"id": "111", "title": "Shared", "picture": "", "accounts": ["nd1", "nd2"]},
                        {"id": "222", "title": "His only", "picture": "", "accounts": ["nd2"]}])
        nd_accounts.delete("nd2")
        ids = {p["id"] for p in load_playlists()}
        self.assertFalse([i for i in ids if i.startswith("auto-nd2-")])
        self.assertIn("auto-daily-1", ids)
        self.assertEqual(accounts_for("111"), ["nd1"])
        self.assertNotIn("222", ids)
        self.assertIsNotNone(trial.get(self.conn, "2", "nd1"))
        self.assertIsNone(trial.get(self.conn, "2", "nd2"))
        self.assertIsNone(mixes_db.get_meta(self.conn, "nd2:settings"))
        self.assertTrue((self.playlists_dir / "Daily Mix 1" / "Daily Mix 1.m3u8").exists())


class Routes(Profiles):
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
        self.as_bob = {"X-Navidrome-Account": "nd2"}

    def test_made_for_you_follows_the_profile(self):
        self.on_trial("nd1", "1")
        self.on_trial("nd2", "2")
        with mock.patch("core.metadata_fix.start_background"):
            saved = self.client.post("/api/mixes/settings", json={"mix_mode": "daily", "max_unheard": 50}, headers=self.as_bob)
        self.assertEqual(saved.status_code, 200)
        bob, alice = self.client.get("/api/mixes", headers=self.as_bob).get_json(), self.client.get("/api/mixes").get_json()
        self.assertEqual((bob["profile"]["id"], bob["settings"]["mix_mode"]), ("nd2", "daily"))
        self.assertEqual((alice["profile"]["id"], alice["settings"]["mix_mode"]), ("nd1", "off"))
        self.assertEqual(alice["settings"]["max_unheard"], 50)
        self.assertEqual([t["id"] for t in bob["on_trial"]], ["2"])
        self.assertEqual([t["id"] for t in alice["on_trial"]], ["1"])
        self.assertEqual(bob["usage"]["unheard"], 2)
        self.assertTrue(bob["profile"]["several"])

    def test_a_profile_cannot_decide_on_anothers_track(self):
        self.on_trial("nd1", "1")
        self.assertEqual(self.client.post("/api/mixes/trial/1/keep", headers=self.as_bob).status_code, 404)
        self.assertEqual(trial.get(self.conn, "1", "nd1")["state"], trial.ON_TRIAL)
        self.assertEqual(self.client.post("/api/mixes/trial/1/remove").status_code, 200)

    def test_regenerate_builds_the_profiles_mixes(self):
        mb.set_mix_mode(self.conn, "nd2", "daily")
        with mock.patch("core.mix_builder.start_task", return_value="t1") as start:
            self.assertEqual(self.client.post("/api/mixes/generate", headers=self.as_bob).get_json()["task_id"], "t1")
        start.assert_called_once_with("nd2", ["daily"])

    def test_a_generated_playlist_stays_its_profiles(self):
        save_playlists([{"id": "auto-nd2-daily-1", "title": "Daily Mix 1", "picture": "", "accounts": ["nd2"]}])
        response = self.client.post("/playlist/auto-nd2-daily-1/accounts", json={"accounts": ["nd1", "nd2"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(accounts_for("auto-nd2-daily-1"), ["nd2"])


class Candidate:
    def __init__(self, deezer_id, artist="T", title=None):
        self.deezer_id, self.artist, self.title, self.album = str(deezer_id), artist, title or f"Song {deezer_id}", "Album"


def no_download(*args, **kwargs):
    raise AssertionError("a shared track must not be downloaded again")


class SharedQuarantine(Profiles):
    """One file per track, a verdict from each profile that got it."""

    def share_with_bob(self, deezer_id="1"):
        path = self.on_trial("nd1", deezer_id)
        saved = mb.download_to_trial(self.conn, "nd2", [Candidate(deezer_id)], 1, auto_id("nd2", "discover"), NOW,
                                     enqueue=no_download)
        self.assertEqual([t["path"] for t in saved], [str(path)])
        return path

    def files(self, folder):
        return sorted(p.name for p in folder.glob("*")) if folder.exists() else []

    def test_a_track_on_trial_for_one_is_given_to_the_other_without_a_download(self):
        path = self.share_with_bob()
        self.assertEqual((trial.get(self.conn, "1", "nd1")["path"], trial.get(self.conn, "1", "nd2")["path"]),
                         (str(path), str(path)))
        self.assertEqual(self.files(trial.trial_dir()), [path.name])
        self.assertEqual(trial.shared_with(self.conn, "nd2"), {"1": ["nd1"]})
        self.assertEqual(trial.usage(self.conn, {}), {"unheard": 1, "bytes": 5})

    def test_each_decides_and_the_file_waits_for_the_other(self):
        path = self.share_with_bob()
        config.update_preview_state("auto-daily-1", {"rows": [{"local_path": str(path)}]})
        config.update_preview_state("auto-nd2-daily-1", {"rows": [{"local_path": str(path)}]})
        self.addCleanup(lambda: [config.delete_playlist_cache(p) for p in ("auto-daily-1", "auto-nd2-daily-1")])
        trial.remove(self.conn, "1", "nd1", NOW)
        self.assertTrue(path.exists())
        self.assertEqual((trial.get(self.conn, "1", "nd1")["state"], trial.get(self.conn, "1", "nd2")["state"]),
                         (trial.TRASH, trial.ON_TRIAL))
        # It leaves Alice's mixes only.
        self.assertEqual(config.get_preview_state("auto-daily-1")["rows"], [])
        self.assertEqual(len(config.get_preview_state("auto-nd2-daily-1")["rows"]), 1)
        trial.remove(self.conn, "1", "nd2", NOW + 10)
        self.assertFalse(path.exists())
        self.assertEqual(self.files(trial.trash_dir()), [path.name])
        self.assertEqual({trial.get(self.conn, "1", a)["path"] for a in ("nd1", "nd2")}, {str(trial.trash_dir() / path.name)})

    def test_kept_by_one_is_kept_for_all(self):
        path = self.share_with_bob()
        trial.keep(self.conn, "1", "nd1", NOW)
        kept = self.downloads / "songs" / path.name
        self.assertTrue(kept.exists())
        bob = trial.get(self.conn, "1", "nd2")
        self.assertEqual((bob["state"], bob["reason"], bob["path"]), (trial.KEPT, "Kept by Alice", str(kept)))
        self.assertEqual(trial.listing(self.conn, trial.ON_TRIAL, "nd2"), [])

    def test_a_refusal_is_the_profiles_own(self):
        path = self.on_trial("nd1", "1")
        trial.remove(self.conn, "1", "nd1", NOW)
        self.assertEqual(self.files(trial.trash_dir()), [path.name])
        self.assertNotIn("1", mb._Run(self.conn, self.bob_stats, "nd2", NOW, "x").exclusions().ids)
        # Bob's mix wants it: out of Alice's trash, back on trial, for him.
        saved = mb.download_to_trial(self.conn, "nd2", [Candidate("1")], 1, auto_id("nd2", "discover"), NOW,
                                     enqueue=no_download)
        self.assertEqual([t["path"] for t in saved], [str(trial.trial_dir() / path.name)])
        self.assertEqual(trial.get(self.conn, "1", "nd1")["state"], trial.TRASH)
        self.assertEqual(trial.rejected(self.conn, "nd2")["ids"], set())
        trial.keep(self.conn, "1", "nd2", NOW)
        self.assertEqual(trial.get(self.conn, "1", "nd1")["state"], trial.DELETED)
        self.assertIn("1", trial.rejected(self.conn, "nd1")["ids"])
        self.assertEqual(trial.listing(self.conn, trial.TRASH, "nd1"), [])

    def test_another_profiles_playlist_keeps_the_file_out_of_the_trash(self):
        path = self.on_trial("nd1", "1")
        save_playlists([{"id": "555", "title": "Bob's", "picture": "", "accounts": ["nd2"]}])
        config.update_preview_state("555", {"playlist_title": "Bob's", "rows": [{"local_path": str(path), "matched": True}]})
        self.addCleanup(config.delete_playlist_cache, "555")
        row = trial.get(self.conn, "1", "nd1")
        reason = trial._earned(row, {}, {}, trial.paths_in_regular_playlists(), set(), trial.Rules())
        self.assertEqual(reason, "In a playlist of Bob")
        with mock.patch("core.trial._rewrite_playlist"):
            trial.remove(self.conn, "1", "nd1", NOW)
        moved = self.downloads / "songs" / path.name
        self.assertTrue(moved.exists())
        self.assertEqual(self.files(trial.trash_dir()), [])
        self.assertEqual(trial.get(self.conn, "1", "nd1")["state"], trial.DELETED)
        self.assertEqual(config.get_preview_state("555")["rows"][0]["local_path"], str(moved))

    def test_the_trash_waits_for_everyone(self):
        path = self.share_with_bob()
        trial.remove(self.conn, "1", "nd1", NOW)
        trial.remove(self.conn, "1", "nd2", NOW)
        in_trash = trial.trash_dir() / path.name
        self.assertEqual(trial.empty_trash(self.conn, "nd1", NOW), 1)
        self.assertTrue(in_trash.exists())
        self.assertEqual(trial.empty_trash(self.conn, "nd2", NOW), 1)
        self.assertFalse(in_trash.exists())

    def test_a_track_also_downloaded_by_hand_leaves_no_second_copy(self):
        path = self.share_with_bob()
        by_hand = self.downloads / "songs" / "T - Song 1.flac"
        by_hand.write_bytes(b"audio")
        config.update_preview_state("auto-nd2-daily-1", {"rows": [{"local_path": str(path)}]})
        self.addCleanup(config.delete_playlist_cache, "auto-nd2-daily-1")
        key = trial.get(self.conn, "1", "nd1")["track_key"]
        with mock.patch("core.mix_builder.library_copies", return_value={key: str(by_hand)}), \
                mock.patch("core.trial._rewrite_playlist"):
            mb.review_quarantine(NOW + 10)
        self.assertFalse(path.exists())
        for account in ("nd1", "nd2"):
            row = trial.get(self.conn, "1", account)
            self.assertEqual((row["state"], row["reason"], row["path"]), (trial.KEPT, "Also in your library", str(by_hand)))
        self.assertEqual(config.get_preview_state("auto-nd2-daily-1")["rows"][0]["local_path"], str(by_hand))
        self.assertEqual(sorted(p.name for p in (self.downloads / "songs").glob("*")), ["T - Song 1.flac"])

    def test_a_removed_profile_hands_over_what_only_it_had(self):
        self.share_with_bob("1")
        self.on_trial("nd2", "2")
        nd_accounts.delete("nd2")
        self.assertIsNone(trial.get(self.conn, "1", "nd2"))
        self.assertEqual(trial.get(self.conn, "1", "nd1")["state"], trial.ON_TRIAL)
        self.assertEqual(trial.get(self.conn, "2", "nd1")["state"], trial.ON_TRIAL)


class SharedRoutes(Routes):
    def test_a_shared_track_says_with_whom(self):
        path = self.on_trial("nd1", "1")
        trial.share(self.conn, "nd2", "1", auto_id("nd2", "discover"), NOW)
        bob = self.client.get("/api/mixes", headers=self.as_bob).get_json()
        self.assertEqual(bob["on_trial"][0]["shared_with"], ["Alice"])
        self.assertEqual(self.client.post("/api/mixes/trial/1/remove", headers=self.as_bob).status_code, 200)
        self.assertTrue(path.exists())
        self.assertEqual(self.client.get("/api/mixes").get_json()["on_trial"][0]["shared_with"], [])


class OldQuarantine(Base):
    def test_the_quarantine_of_before_profiles_becomes_the_installs(self):
        self.conn.close()
        db = mixes_db.db_path()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{db}{suffix}").unlink(missing_ok=True)
        backup = Path(config.DATA_DIR) / "backups" / "pre-1.16.0" / "mixes.db"
        backup.unlink(missing_ok=True)
        old = sqlite3.connect(db)
        old.executescript("""
            CREATE TABLE trial_tracks (deezer_id TEXT PRIMARY KEY, track_key TEXT NOT NULL, artist TEXT NOT NULL,
                title TEXT NOT NULL, album TEXT NOT NULL DEFAULT '', path TEXT, size INTEGER NOT NULL DEFAULT 0,
                mix_id TEXT NOT NULL DEFAULT '', downloaded_at INTEGER NOT NULL, trial_ends_at INTEGER NOT NULL,
                state TEXT NOT NULL, state_at INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '');
            INSERT INTO trial_tracks VALUES ('7', 'a|b', 'A', 'B', '', '/x.flac', 1, 'auto-blend-1', 1, 2, 'on_trial', 1, '');
            INSERT INTO trial_tracks VALUES ('8', 'a|c', 'A', 'C', '', '/y.flac', 1, 'auto-discover', 1, 2, 'trash', 1, 'Never played');
        """)
        old.close()
        self.conn = mixes_db.connect()
        self.addCleanup(self.conn.close)
        keyed = {row[1]: row[5] for row in self.conn.execute("PRAGMA table_info(trial_tracks)")}
        self.assertTrue(keyed["deezer_id"] and keyed["account_id"])
        self.assertEqual([(r["deezer_id"], r["account_id"], r["state"]) for r in self.conn.execute(
            "SELECT * FROM trial_tracks ORDER BY deezer_id")], [("7", "nd1", "on_trial"), ("8", "nd1", "trash")])
        self.assertTrue(backup.exists())
        mixes_db.connect().close()
