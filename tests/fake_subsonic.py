"""A small Subsonic server for the tests, shaped like Navidrome's answers.

It runs for real on 127.0.0.1 (a thread), so the client is tested over HTTP,
with POST bodies and query strings as they would go out. Every request is
recorded, which lets a test check that no credential ever went into a URL."""
import hashlib
import itertools
import threading
import time

from flask import Flask, jsonify, request
from werkzeug.serving import WSGIRequestHandler, make_server

VERSION = "1.16.1"


class _Quiet(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


class FakeSubsonic:
    def __init__(self, server_version="0.64.0 (fake)", extensions=("apiKeyAuthentication", "formPost"),
                 accept_post=True, open_subsonic=True):
        self.server_version = server_version
        self.extensions = list(extensions)
        self.accept_post = accept_post
        self.open_subsonic = open_subsonic
        self.users = {}
        self.folders = {1: "Music"}
        self.songs = {}
        self.playlists = {}
        self.scans = 0
        self.requests = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.app = self._make_app()
        self._server = None
        self._thread = None

    # --- Setup -------------------------------------------------------------------

    def add_user(self, name, password, admin=False, api_key=None, folders=(1,)):
        self.users[name] = {"password": password, "admin": admin, "api_key": api_key, "folders": list(folders)}

    def add_song(self, song_id, title, artist, album="Album", path="", folder=1, duration=200):
        self.songs[str(song_id)] = {"id": str(song_id), "title": title, "artist": artist, "album": album,
                                    "path": path, "folder": folder, "duration": duration}

    # --- Running -----------------------------------------------------------------

    def start(self):
        self._server = make_server("127.0.0.1", 0, self.app, threaded=True, request_handler=_Quiet)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    @property
    def url(self):
        return f"http://127.0.0.1:{self._server.server_port}"

    # --- Protocol ----------------------------------------------------------------

    def _reply(self, **payload):
        body = {"status": "ok", "version": VERSION, "type": "navidrome", "serverVersion": self.server_version}
        if self.open_subsonic:
            body["openSubsonic"] = True
        body.update(payload)
        return jsonify({"subsonic-response": body})

    def _fail(self, code, message):
        body = {"status": "failed", "version": VERSION, "type": "navidrome", "serverVersion": self.server_version,
                "error": {"code": code, "message": message}}
        return jsonify({"subsonic-response": body})

    def _authenticate(self, params):
        """The user name, or a failure answer."""
        if params.get("apiKey"):
            if "apiKeyAuthentication" not in self.extensions:
                return None, self._fail(42, "Provided authentication mechanism not supported")
            if params.get("u"):
                return None, self._fail(43, "Multiple conflicting authentication mechanisms provided")
            for name, user in self.users.items():
                if user["api_key"] and user["api_key"] == params["apiKey"]:
                    return name, None
            return None, self._fail(44, "Invalid API key")
        name = params.get("u", "")
        user = self.users.get(name)
        if user is None:
            return None, self._fail(40, "Wrong username or password")
        if params.get("t") and params.get("s"):
            expected = hashlib.md5((user["password"] + params["s"]).encode()).hexdigest()
            ok = params["t"] == expected
        elif params.get("p"):
            given = params["p"]
            if given.startswith("enc:"):
                given = bytes.fromhex(given[4:]).decode()
            ok = given == user["password"]
        else:
            return None, self._fail(10, "Required parameter is missing")
        return (name, None) if ok else (None, self._fail(40, "Wrong username or password"))

    def _song(self, song_id):
        song = self.songs[song_id]
        return {"id": song["id"], "title": song["title"], "artist": song["artist"], "album": song["album"],
                "path": song["path"], "duration": song["duration"], "isDir": False}

    def _visible(self, user, song_id):
        song = self.songs.get(song_id)
        return song is not None and song["folder"] in self.users[user]["folders"]

    def _playlist_view(self, playlist, with_songs=False):
        view = {"id": playlist["id"], "name": playlist["name"], "owner": playlist["owner"],
                "comment": playlist["comment"], "public": playlist["public"], "songCount": len(playlist["songs"]),
                "changed": playlist["changed"], "created": playlist["created"]}
        if with_songs:
            view["entry"] = [self._song(s) for s in playlist["songs"]]
        return view

    def _make_app(self):
        app = Flask("fake-subsonic")

        @app.route("/rest/<name>", methods=["GET", "POST"])
        def endpoint(name):
            name = name.removesuffix(".view")
            with self._lock:
                self.requests.append({"method": request.method, "endpoint": name,
                                      "query": request.query_string.decode(), "form": sorted(request.form.keys())})
            if request.method == "POST" and not self.accept_post:
                return "Method not allowed", 405
            params = {**request.args.to_dict(), **request.form.to_dict()}
            lists = {key: request.values.getlist(key) for key in request.values.keys()}
            if params.get("f") != "json":
                return "Only JSON in this fake", 400
            user, failure = self._authenticate(params)
            if failure is not None:
                return failure
            handler = getattr(self, f"_do_{name}", None)
            if handler is None:
                return self._fail(0, f"Unknown endpoint {name}")
            with self._lock:
                return handler(user, params, lists)

        return app

    # --- Endpoints ---------------------------------------------------------------

    def _do_ping(self, user, params, lists):
        return self._reply()

    def _do_getOpenSubsonicExtensions(self, user, params, lists):
        return self._reply(openSubsonicExtensions=[{"name": n, "versions": [1]} for n in self.extensions])

    def _do_getUser(self, user, params, lists):
        wanted = params.get("username", user)
        if wanted != user and not self.users[user]["admin"]:
            return self._fail(50, "User is not authorized for the given operation.")
        info = self.users.get(wanted)
        if info is None:
            return self._fail(70, "User not found")
        return self._reply(user={"username": wanted, "adminRole": info["admin"], "scrobblingEnabled": True,
                                 "folder": info["folders"]})

    def _do_getMusicFolders(self, user, params, lists):
        folders = [{"id": fid, "name": self.folders[fid]} for fid in self.users[user]["folders"] if fid in self.folders]
        return self._reply(musicFolders={"musicFolder": folders})

    def _do_getPlaylists(self, user, params, lists):
        mine = [self._playlist_view(p) for p in self.playlists.values() if p["owner"] == user or p["public"]]
        return self._reply(playlists={"playlist": mine})

    def _do_getPlaylist(self, user, params, lists):
        playlist = self.playlists.get(params.get("id", ""))
        if playlist is None or (playlist["owner"] != user and not playlist["public"]):
            return self._fail(70, "Playlist not found")
        return self._reply(playlist=self._playlist_view(playlist, with_songs=True))

    def _do_createPlaylist(self, user, params, lists):
        songs = [s for s in lists.get("songId", []) if self._visible(user, s)]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if params.get("playlistId"):
            playlist = self.playlists.get(params["playlistId"])
            if playlist is None:
                return self._fail(70, "Playlist not found")
            if playlist["owner"] != user:
                return self._fail(50, "User is not authorized for the given operation.")
            playlist["songs"] = songs
            playlist["changed"] = now
        else:
            if not params.get("name"):
                return self._fail(10, "Required parameter is missing")
            playlist_id = f"pl-{next(self._ids)}"
            playlist = {"id": playlist_id, "name": params["name"], "owner": user, "comment": "", "public": False,
                        "songs": songs, "created": now, "changed": now}
            self.playlists[playlist_id] = playlist
        return self._reply(playlist=self._playlist_view(playlist, with_songs=True))

    def _do_updatePlaylist(self, user, params, lists):
        playlist = self.playlists.get(params.get("playlistId", ""))
        if playlist is None:
            return self._fail(70, "Playlist not found")
        if playlist["owner"] != user and not self.users[user]["admin"]:
            return self._fail(50, "User is not authorized for the given operation.")
        if "name" in params:
            playlist["name"] = params["name"]
        if "comment" in params:
            playlist["comment"] = params["comment"]
        if "public" in params:
            playlist["public"] = params["public"] == "true"
        remove = sorted({int(i) for i in lists.get("songIndexToRemove", [])}, reverse=True)
        for index in remove:
            if 0 <= index < len(playlist["songs"]):
                playlist["songs"].pop(index)
        playlist["songs"].extend(s for s in lists.get("songIdToAdd", []) if self._visible(user, s))
        playlist["changed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return self._reply()

    def _do_deletePlaylist(self, user, params, lists):
        playlist = self.playlists.get(params.get("id", ""))
        if playlist is None:
            return self._fail(70, "Playlist not found")
        if playlist["owner"] != user and not self.users[user]["admin"]:
            return self._fail(50, "User is not authorized for the given operation.")
        del self.playlists[playlist["id"]]
        return self._reply()

    def _do_search3(self, user, params, lists):
        words = (params.get("query") or "").lower().replace('"', "").split()
        found = [self._song(s) for s in self.songs if self._visible(user, s)
                 and all(w in f"{self.songs[s]['title']} {self.songs[s]['artist']} {self.songs[s]['album']}".lower() for w in words)]
        return self._reply(searchResult3={"song": found[: int(params.get("songCount", 20))]})

    def _do_startScan(self, user, params, lists):
        if not self.users[user]["admin"]:
            return self._fail(50, "User is not authorized for the given operation.")
        self.scans += 1
        return self._reply(scanStatus={"scanning": True, "count": 0})

    def _do_getScanStatus(self, user, params, lists):
        return self._reply(scanStatus={"scanning": False, "count": len(self.songs)})

    def _do_getStarred2(self, user, params, lists):
        return self._reply(starred2={"song": []})
