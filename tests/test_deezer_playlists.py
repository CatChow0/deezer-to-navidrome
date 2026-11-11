"""Deezer playlists: read with a Deezer account first (a private playlist of its
own, and every track in one call), else the public API, paginated past the 400
tracks /playlist/{id} stops at."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from core import deezer, deezer_account


def song(i):
    return {"SNG_ID": str(1000 + i), "SNG_TITLE": f"Song {i}", "VERSION": "", "ART_NAME": "Artist",
            "ALB_TITLE": "Album", "DURATION": "200", "ALB_PICTURE": "md5"}


def public_track(i):
    return {"id": 2000 + i, "title": f"Track {i}", "duration": 180,
            "artist": {"name": "Artist"}, "album": {"title": "Album"}}


class GatewayReads(unittest.TestCase):
    def test_every_track_in_one_call(self):
        songs = [song(i) for i in range(450)]
        with mock.patch.object(deezer_account, "_gw", return_value={"data": songs, "total": 450}) as gw:
            tracks = deezer_account.playlist_tracks("908622995", account="dz2")
        self.assertEqual(450, len(tracks))
        self.assertEqual((1, 1000, "Song 0", "Artist", "Album", 200),
                         tuple(tracks[0][k] for k in ("position", "track_id", "title", "artist", "album", "duration")))
        self.assertEqual(450, tracks[-1]["position"])
        method, body = gw.call_args.args
        self.assertEqual(("playlist.getSongs", {"PLAYLIST_ID": "908622995", "nb": -1}), (method, body))
        self.assertEqual("dz2", gw.call_args.kwargs["account"])

    def test_a_partial_answer_is_refused_rather_than_cut(self):
        with mock.patch.object(deezer_account, "_gw", return_value={"data": [song(1)], "total": 900}):
            with self.assertRaises(deezer_account.DeezerAccountError):
                deezer_account.playlist_tracks("1")

    def test_an_answer_of_another_shape_is_refused(self):
        for answer in ({}, {"data": None}, None):
            with self.subTest(answer=answer), mock.patch.object(deezer_account, "_gw", return_value=answer):
                with self.assertRaises(deezer_account.DeezerAccountError):
                    deezer_account.playlist_tracks("1")

    def test_playlist_info(self):
        page = {"DATA": {"TITLE": "Mine, private", "PLAYLIST_PICTURE": "pic", "NB_SONG": 1200}}
        with mock.patch.object(deezer_account, "_gw", return_value=page) as gw:
            info = deezer_account.playlist_info(77, account="dz1")
        self.assertEqual({"id": "77", "title": "Mine, private", "track_count": 1200}, {k: info[k] for k in ("id", "title", "track_count")})
        self.assertIn("/images/playlist/pic/1000x1000", info["picture"])
        self.assertEqual("deezer.pagePlaylist", gw.call_args.args[0])
        with mock.patch.object(deezer_account, "_gw", return_value={"DATA": {}}):
            with self.assertRaises(deezer_account.DeezerAccountError):
                deezer_account.playlist_info(77)


class WhichAccount(unittest.TestCase):
    def test_the_profiles_accounts_then_the_default_once_each(self):
        own = {"nd1": "dz1", "nd2": "dz2", "nd3": "dz2"}
        with mock.patch("core.account_context.deezer_account_of", side_effect=lambda p: own[p]), \
                mock.patch("core.deezer_accounts.default_id", return_value="dz1"):
            self.assertEqual(["dz2", "dz1"], deezer._reading_accounts("5", profiles=["nd2", "nd3"]))
            self.assertEqual(["dz1"], deezer._reading_accounts("5", profiles=[]))

    def test_no_deezer_account_at_all(self):
        with mock.patch("core.account_context.deezer_account_of", return_value=None), \
                mock.patch("core.deezer_accounts.default_id", return_value=None):
            self.assertEqual([], deezer._reading_accounts("5", profiles=["nd1"]))

    def test_a_saved_playlists_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            saved = Path(folder) / "playlists.json"
            saved.write_text(json.dumps({"playlists": [{"id": "5", "accounts": ["nd2"]}]}), encoding="utf-8")
            with mock.patch.object(deezer, "PLAYLIST_IDS_FILE", saved):
                self.assertEqual(["nd2"], deezer._saved_profiles("5"))
                self.assertEqual([], deezer._saved_profiles("6"))


class FetchTracks(unittest.TestCase):
    def test_read_with_the_first_account_that_can(self):
        def info(pid, account):
            if account == "dz2":
                raise deezer_account.DeezerAccountError("Deezer refused deezer.pagePlaylist: no access")
            return {"id": pid, "title": "Private one", "picture": "", "track_count": 1}

        with mock.patch.object(deezer, "_reading_accounts", return_value=["dz2", "dz1"]), \
                mock.patch.object(deezer_account, "playlist_info", side_effect=info), \
                mock.patch.object(deezer_account, "playlist_tracks", return_value=[{"track_id": 1}]) as tracks, \
                mock.patch.object(deezer, "_public_api") as public:
            title, found = deezer.fetch_deezer_playlist_tracks("42")
        self.assertEqual(("Private one", [{"track_id": 1}]), (title, found))
        self.assertEqual("dz1", tracks.call_args.args[1])
        public.assert_not_called()

    def test_without_an_account_the_public_api_is_read_past_400(self):
        pages = {0: {"data": [public_track(i) for i in range(100)], "total": 450},
                 100: {"data": [public_track(i) for i in range(100, 200)], "total": 450},
                 200: {"data": [public_track(i) for i in range(200, 300)], "total": 450},
                 300: {"data": [public_track(i) for i in range(300, 400)], "total": 450},
                 400: {"data": [public_track(i) for i in range(400, 450)], "total": 450}}
        with mock.patch.object(deezer, "_reading_accounts", return_value=[]), \
                mock.patch.object(deezer, "fetch_deezer_playlist_info", return_value={"title": "Big one"}), \
                mock.patch.object(deezer, "_public_api", side_effect=lambda path, params: pages[params["index"]]) as public:
            title, tracks = deezer.fetch_deezer_playlist_tracks("42")
        self.assertEqual(("Big one", 450), (title, len(tracks)))
        self.assertEqual(list(range(1, 451)), [t["position"] for t in tracks])
        self.assertEqual((2449, "Track 449", "artist"), (tracks[-1]["track_id"], tracks[-1]["title"], tracks[-1]["norm_artist"]))
        self.assertEqual("/playlist/42/tracks", public.call_args.args[0])

    def test_the_public_api_when_every_account_fails(self):
        with mock.patch.object(deezer, "_reading_accounts", return_value=["dz1"]), \
                mock.patch.object(deezer_account, "playlist_info", side_effect=requests.ConnectionError("reset")), \
                mock.patch.object(deezer, "fetch_deezer_playlist_info", return_value={"title": "Public"}), \
                mock.patch.object(deezer, "_public_api", return_value={"data": [public_track(1)], "total": 1}):
            self.assertEqual(("Public", 1), (lambda r: (r[0], len(r[1])))(deezer.fetch_deezer_playlist_tracks("42")))


class FetchInfo(unittest.TestCase):
    def test_the_adding_profiles_account_first(self):
        with mock.patch.object(deezer, "_reading_accounts", return_value=["dz2"]) as accounts, \
                mock.patch.object(deezer_account, "playlist_info", return_value={"id": "9", "title": "Mine", "picture": "", "track_count": 3}), \
                mock.patch.object(deezer.requests, "get") as public:
            self.assertEqual("Mine", deezer.fetch_deezer_playlist_info("9", profiles=["nd2"])["title"])
        self.assertEqual(["nd2"], accounts.call_args.args[1])
        public.assert_not_called()

    def test_the_public_api_answers_otherwise_and_its_error_still_raises(self):
        refused = mock.Mock(**{"json.return_value": {"error": {"code": 800}}})
        with mock.patch.object(deezer, "_reading_accounts", return_value=["dz1"]), \
                mock.patch.object(deezer_account, "playlist_info", side_effect=deezer_account.DeezerAccountError("no")), \
                mock.patch.object(deezer.requests, "get", return_value=refused):
            with self.assertRaises(RuntimeError):
                deezer.fetch_deezer_playlist_info("9")


if __name__ == "__main__":
    unittest.main()
