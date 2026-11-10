"""The API's resources: what the web interface does, the app can do under
/api/v1, in the API's format."""
import io
import os
import re
import unittest
from pathlib import Path
from unittest import mock

import requests
from flask import jsonify, send_file

from core import config, content, nd_accounts
from core.deezer import accounts_for, load_playlists, save_playlists
from routes import api_v1, system
from tests.test_api_v1 import REPO, Base

# The web routes with nothing under /api/v1, and why.
WEB_ONLY = {
    "listenbrainz.submit": "Navidrome's scrobbles: from server to server",
    "listenbrainz.submit_slash": "Navidrome's scrobbles: from server to server",
    "listenbrainz.validate": "Navidrome's scrobbles: from server to server",
    "listenbrainz.validate_slash": "Navidrome's scrobbles: from server to server",
    "navidrome_accounts.choose_active": "a device names its profile in each request (X-Navidrome-Account)",
    "system.favicon": "the browser's icon",
    "system.health": "Docker's health check; an app asks /api/v1/auth/status",
}


class Parity(Base):
    def test_every_web_route_has_its_counterpart(self):
        missing = []
        for rule in self.app.url_map.iter_rules():
            endpoint = rule.endpoint
            if endpoint == "static" or endpoint.startswith("api_v1.") or endpoint in WEB_ONLY:
                continue
            if self.app.view_functions[endpoint] not in api_v1.COVERED:
                missing.append(f"{endpoint} {rule.rule}")
        self.assertEqual(missing, [], "web routes with nothing under /api/v1: expose() them, or say why in WEB_ONLY")

    def test_the_routes_left_to_the_web_exist(self):
        self.assertEqual(set(WEB_ONLY) - {rule.endpoint for rule in self.app.url_map.iter_rules()}, set())


class Translation(Base):
    def translate(self, answer, method="GET"):
        with self.app.test_request_context("/api/v1/anything", method=method):
            response = api_v1.translate(answer)
            return response.status_code, response.get_json(silent=True), response

    def test_a_web_failure_becomes_an_api_error(self):
        with self.app.test_request_context():
            self.assertEqual(self.translate((jsonify({"ok": False, "error": "invalid type"}), 400))[:2],
                             (400, {"error": {"code": "invalid", "message": "invalid type"}}))
            # A failure answered 200 is still one.
            self.assertEqual(self.translate(jsonify({"ok": False, "error": "Nope"}))[0], 400)
            self.assertEqual(self.translate((jsonify({"error": "No such playlist"}), 404))[1]["error"]["code"], "not_found")
            # What else it said is kept.
            status, data, _ = self.translate((jsonify({"ok": False, "error": "Running", "task_id": "t1"}), 409))
            self.assertEqual((status, data["error"]["code"], data["error"]["task_id"]), (409, "conflict", "t1"))

    def test_an_answer_loses_ok_and_links_its_media_here(self):
        with self.app.test_request_context():
            answer = jsonify({"ok": True, "cover": "/stats/cover/album/3?a=nd2",
                              "tracks": [{"cover": "/covers/a.jpg"}, {"cover": "/api/mixes/trial/12/cover"}],
                              "link": "https://e-cdns-images.dzcdn.net/images/covers/x.jpg", "path": "/music/a.flac"})
        status, data, response = self.translate(answer)
        self.assertEqual(status, 200)
        self.assertEqual(data, {"cover": "/api/v1/stats/cover/album/3?a=nd2",
                                "tracks": [{"cover": "/api/v1/covers/a.jpg"}, {"cover": "/api/v1/mixes/trial/12/cover"}],
                                "link": "https://e-cdns-images.dzcdn.net/images/covers/x.jpg", "path": "/music/a.flac"})
        self.assertTrue(response.headers.get("ETag"))
        with self.app.test_request_context():
            self.assertEqual(self.translate(jsonify([1, 2]))[1], {"items": [1, 2]})
            # A change answers without an ETag.
            self.assertIsNone(self.translate(jsonify({"ok": True}), method="POST")[2].headers.get("ETag"))

    def test_files_pass_as_they_are(self):
        picture = Path(config.DATA_DIR) / "api-picture.jpg"
        picture.write_bytes(b"\xff\xd8\xff picture")
        self.addCleanup(picture.unlink)
        with self.app.test_request_context("/api/v1/anything"):
            response = api_v1.translate(send_file(picture, mimetype="image/jpeg"))
            response.direct_passthrough = False
            self.assertEqual((response.mimetype, response.get_data()), ("image/jpeg", b"\xff\xd8\xff picture"))
            response.close()

    def test_through_the_routes(self):
        auth = {"Authorization": f"Bearer {self.token()}"}
        bad = self.client.get("/api/v1/search?q=x&type=bogus", headers=auth)
        self.assertEqual((bad.status_code, bad.get_json()), (400, {"error": {"code": "invalid", "message": "invalid type"}}))
        figures = self.client.get("/api/v1/library/stats", headers=auth)
        self.assertEqual(figures.status_code, 200)
        self.assertNotIn("ok", figures.get_json())
        again = self.client.get("/api/v1/library/stats", headers={**auth, "If-None-Match": figures.headers["ETag"]})
        self.assertEqual(again.status_code, 304)
        cover = self.client.get("/api/v1/stats/cover/album/999", headers=auth)
        self.assertEqual((cover.status_code, cover.get_json()["error"]["code"]), (404, "not_found"))
        # The Stats blueprint answers its own errors: here too.
        no_zone = self.client.get("/api/v1/stats/overview?period=all", headers=auth)
        self.assertEqual((no_zone.status_code, no_zone.get_json()), (400, {"error": {"code": "invalid", "message": "Unknown timezone"}}))
        self.assertEqual(self.client.get("/api/v1/stats/overview?period=all&tz=Europe/Paris", headers=auth).status_code, 200)
        # A body too large, in the API's format too.
        with mock.patch.dict(self.app.config, {"MAX_CONTENT_LENGTH": 10}):
            large = self.client.post("/api/v1/playlists", json={"link": "x" * 50}, headers=auth)
        self.assertEqual((large.status_code, large.get_json()["error"]["code"]), (413, "too_large"))
        self.assertEqual(self.client.get("/api/v1/library/stats").status_code, 401)


class Profiles(Base):
    def setUp(self):
        super().setUp()
        Path(config.DATA_DIR, "navidrome_accounts.json").unlink(missing_ok=True)
        nd_accounts.ensure_initial()
        self.bob = nd_accounts.create({"label": "Bob", "url": "http://navidrome:4533", "username": "bob",
                                       "secret": "bob-secret-value"})["id"]
        self.auth = {"Authorization": f"Bearer {self.token()}"}

    def test_a_web_function_answers_for_the_profile_of_the_header(self):
        self.assertEqual(self.client.get("/api/v1/mixes", headers=self.auth).get_json()["profile"]["id"], "nd1")
        mine = self.client.get("/api/v1/mixes", headers={**self.auth, "X-Navidrome-Account": self.bob})
        self.assertEqual(mine.get_json()["profile"]["id"], self.bob)

    def test_the_accounts_never_show_their_secret(self):
        listed = self.client.get("/api/v1/navidrome/accounts", headers=self.auth)
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("bob-secret-value", listed.get_data(as_text=True))
        self.assertIn(self.bob, [a["id"] for a in listed.get_json()["accounts"]])
        unknown = self.client.patch("/api/v1/navidrome/accounts/nope", json={"label": "x"}, headers=self.auth)
        self.assertEqual(unknown.get_json()["error"]["code"], "not_found")


class Playlists(Profiles):
    def setUp(self):
        super().setUp()
        save_playlists([])
        config.save_preview_state({})
        patches = (
            mock.patch("routes.playlists.fetch_deezer_playlist_info",
                       side_effect=lambda pid: {"id": pid, "title": f"Deezer {pid}", "picture": ""}),
            mock.patch("routes.playlists.cache_cover", return_value=None),
            mock.patch("core.publish.custom_titles", return_value={}),
            mock.patch("core.publish.handmade", return_value=[]),
            mock.patch("core.publish.sync_soon"),
            mock.patch("core.publish.remove_from", return_value=True),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def ids(self, profile=None):
        headers = {**self.auth, **({"X-Navidrome-Account": profile} if profile else {})}
        data = self.client.get("/api/v1/playlists", headers=headers).get_json()
        return [p["id"] for p in data["playlists"]]

    def test_adding_listing_and_deleting_for_a_profile(self):
        bob = {**self.auth, "X-Navidrome-Account": self.bob}
        added = self.client.post("/api/v1/playlists", json={"link": "https://www.deezer.com/playlist/9101"}, headers=bob)
        self.assertEqual(added.status_code, 201)
        self.assertEqual(added.get_json(), {"id": "9101", "added": True, "task_id": None, "message": "Playlist added"})
        self.assertEqual(accounts_for("9101"), [self.bob])
        self.assertEqual((self.ids(self.bob), self.ids()), (["9101"], []))
        tile = self.client.get("/api/v1/playlists", headers=bob).get_json()["playlists"][0]
        self.assertEqual((tile["title"], tile["accounts"], tile["tracks"]), ("Deezer 9101", [self.bob], None))
        # Saved already: now the default profile's too.
        shared = self.client.post("/api/v1/playlists", json={"link": "9101"}, headers=self.auth)
        self.assertEqual((shared.status_code, shared.get_json()["added"]), (200, False))
        self.assertEqual(accounts_for("9101"), [self.bob, "nd1"])
        off_bob = self.client.delete("/api/v1/playlists/9101", headers=bob)
        self.assertEqual(off_bob.get_json()["deleted"], False)
        self.assertEqual(accounts_for("9101"), ["nd1"])
        gone = self.client.delete("/api/v1/playlists/9101", headers=self.auth)
        self.assertEqual(gone.get_json()["deleted"], True)
        self.assertEqual(load_playlists(), [])
        self.assertEqual(self.client.delete("/api/v1/playlists/9101", headers=self.auth).status_code, 404)

    def test_a_tile_says_how_far_matching_got(self):
        save_playlists([{"id": "9102", "title": "Matched", "picture": "", "cover_cached": "9102.jpg"}])
        # As a scan saves it: the rows, without their counts.
        config.save_preview_state({"9102": {"rows": [{"matched": True}, {"matched": True}, {"matched": False}, {"matched": None}]}})
        tile = self.client.get("/api/v1/playlists", headers=self.auth).get_json()["playlists"][0]
        self.assertEqual(tile["tracks"], {"total": 4, "matched": 2, "unmatched": 1, "unchecked": 1})
        self.assertEqual(tile["cover"], "/api/v1/covers/9102.jpg")

    def test_a_bad_link_and_deezer_not_answering(self):
        empty = self.client.post("/api/v1/playlists", json={}, headers=self.auth)
        self.assertEqual((empty.status_code, empty.get_json()["error"]["code"]), (400, "invalid"))
        wrong = self.client.post("/api/v1/playlists", json={"link": "not a playlist"}, headers=self.auth)
        self.assertEqual((wrong.status_code, wrong.get_json()["error"]["message"]), (400, "Invalid ID or URL"))
        with mock.patch("routes.playlists.fetch_deezer_playlist_info", side_effect=requests.ConnectionError("timed out")):
            down = self.client.post("/api/v1/playlists", json={"link": "9103"}, headers=self.auth)
        self.assertEqual((down.status_code, down.get_json()["error"]["code"]), (502, "upstream_error"))
        with mock.patch("routes.playlists.fetch_deezer_playlist_info", side_effect=RuntimeError("{'code': 800}")):
            unknown = self.client.post("/api/v1/playlists", json={"link": "9104"}, headers=self.auth)
            with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
                self.client.post("/playlist/add", data={"playlist_input": "9104"})
                page = self.client.get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        self.assertEqual((unknown.status_code, unknown.get_json()["error"]["message"]),
                         (400, "Deezer has no public playlist with this ID"))
        self.assertIn("Deezer has no public playlist with this ID", page)
        self.assertEqual(load_playlists(), [])

    def test_another_profiles_playlist_is_never_deleted_from_here(self):
        save_playlists([{"id": "9105", "title": "Bob's", "picture": "", "accounts": [self.bob]}])
        refused = self.client.delete("/api/v1/playlists/9105", headers=self.auth)
        self.assertEqual((refused.status_code, refused.get_json()["error"]["code"]), (404, "not_found"))
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            self.client.post("/playlist/9105/delete")
        self.assertEqual(accounts_for("9105"), [self.bob])

    def test_spotify_and_csv_start_finding_their_tracks(self):
        with mock.patch("routes.playlists.crossplatform.add_spotify", return_value=("sp-1", True)), \
                mock.patch("routes.playlists._start_scan", return_value="task-1") as scan:
            spotify = self.client.post("/api/v1/playlists", json={"link": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"},
                                       headers=self.auth)
        self.assertEqual((spotify.status_code, spotify.get_json()["id"], spotify.get_json()["task_id"]), (201, "sp-1", "task-1"))
        self.assertTrue(scan.call_args.kwargs["quick"])
        with mock.patch("routes.playlists.crossplatform.add_csv", return_value="csv-1") as add_csv, \
                mock.patch("routes.playlists._start_scan", return_value="task-2"):
            imported = self.client.post("/api/v1/playlists/import", headers=self.auth, content_type="multipart/form-data",
                                        data={"csv_file": (io.BytesIO(b"Track Name,Artist Name(s)\nA,B\n"), "mine.csv")})
        self.assertEqual((imported.status_code, imported.get_json()["task_id"]), (201, "task-2"))
        self.assertEqual(add_csv.call_args.args[0], "mine.csv")
        self.assertEqual(add_csv.call_args.kwargs["accounts"], ["nd1"])
        nothing = self.client.post("/api/v1/playlists/import", headers=self.auth, content_type="multipart/form-data", data={})
        self.assertEqual(nothing.status_code, 400)


class Settings(Base):
    def setUp(self):
        super().setUp()
        self.addCleanup(config.save_config, config.load_config())
        self.auth = {"Authorization": f"Bearer {self.token()}"}

    def put(self, values):
        return self.client.put("/api/v1/settings", json=values, headers=self.auth)

    def test_reading_and_changing_some_settings(self):
        read = self.client.get("/api/v1/settings", headers=self.auth)
        self.assertEqual(set(read.get_json()["settings"]), set(system.SETTINGS_KEYS))
        self.assertIn("downloads_folder", read.get_json())
        self.assertTrue(read.headers.get("ETag"))
        before = read.get_json()["settings"]
        changed = self.put({"match_workers": 8, "host_to_navidrome_roots": [{"host": "/srv/music", "navidrome": "/music"}],
                            "deezer_dl_dir": "http://old-downloader:6595"})
        self.assertEqual(changed.status_code, 200)
        after = changed.get_json()["settings"]
        self.assertEqual((after["match_workers"], after["host_to_navidrome_roots"], after["deezer_dl_dir"]),
                         (8, [{"host": "/srv/music", "navidrome": "/music"}], ""))
        self.assertEqual(after["scan_dirs"], before["scan_dirs"])
        self.assertEqual(config.load_config()["match_workers"], 8)

    def test_settings_it_refuses(self):
        for values, words in (({"nope": 1}, "nope"), ({"match_workers": "many"}, "match_workers"),
                              ({"match_workers": 7}, "1, 2, 4, 6, 8, 12, 16"), ({"download_workers": True}, "download_workers"),
                              ({"scan_dirs": "/music"}, "scan_dirs")):
            refused = self.put(values)
            self.assertEqual((refused.status_code, refused.get_json()["error"]["code"]), (400, "invalid"))
            self.assertIn(words, refused.get_json()["error"]["message"])

    def test_the_app_gets_the_choices_of_the_menus(self):
        choices = self.client.get("/api/v1/settings", headers=self.auth).get_json()["choices"]
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            page = self.client.get("/config", headers={"Accept": "text/html"}).get_data(as_text=True)
        for key, values in choices.items():
            menu = re.search(rf'<select name="{key}">(.*?)</select>', page, re.S).group(1)
            self.assertEqual([int(v) for v in re.findall(r'value="(\d+)"', menu)], values, key)

    def test_the_web_form_still_saves_them(self):
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            self.client.post("/config", data={"scan_dirs": "/music/a\n\n/music/b\n", "mapping_host[]": ["/srv", ""],
                                              "mapping_navidrome[]": ["/music", "/x"], "match_workers": "5"})
            refused = self.client.post("/config", data={"match_workers": "five"})
            self.assertEqual((refused.status_code, refused.get_json()["error"]), (400, "match_workers must be a number"))
        cfg = config.load_config()
        self.assertEqual((cfg["scan_dirs"], cfg["host_to_navidrome_roots"], cfg["match_workers"]),
                         (["/music/a", "/music/b"], [{"host": "/srv", "navidrome": "/music"}], 5))

    def test_reset_data(self):
        cleared = mock.Mock()
        with mock.patch.dict(system.CLEARS, {"dedup-report": (cleared, "dedup_report cleared")}):
            done = self.client.post("/api/v1/settings/clear/dedup-report", headers=self.auth)
            self.assertEqual(done.get_json(), {"cleared": "dedup-report", "message": "dedup_report cleared"})
            with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
                self.assertEqual(self.client.post("/admin/clear/dedup-report").status_code, 302)
        self.assertEqual(cleared.call_count, 2)
        self.assertEqual(self.client.post("/api/v1/settings/clear/everything", headers=self.auth).status_code, 404)


class Content(Base):
    def test_the_help_by_section(self):
        auth = {"Authorization": f"Bearer {self.token()}"}
        sections = self.client.get("/api/v1/content/help", headers=auth).get_json()["sections"]
        self.assertEqual([s["id"] for s in sections], [key for key, _ in content.HELP_SECTIONS])
        self.assertTrue(all("<" in s["html"] for s in sections))
        with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            page = self.client.get("/", headers={"Accept": "text/html"}).get_data(as_text=True)
        for key, title in content.HELP_SECTIONS:
            self.assertIn(title, page)

    def test_the_notes_newest_first(self):
        auth = {"Authorization": f"Bearer {self.token()}"}
        data = self.client.get("/api/v1/content/notes", headers=auth).get_json()
        self.assertEqual(data["notes"][0]["version"], (REPO / "VERSION").read_text(encoding="utf-8").strip())
        self.assertTrue(all(n["html"].strip() for n in data["notes"]))
        self.assertIsInstance(data["unseen"], bool)


if __name__ == "__main__":
    unittest.main()
