"""Deezer account features that need the session cookie (ARL): favorite
artists, the "made for you" mixes and Flow.

Deezer's private gateway (gw-light) is undocumented and may change. Every call
goes through `DeezerSession.gw`, which logs in lazily and refreshes the API
token once when Deezer rejects it.

`DeezerSession` is also what the downloader uses: it needs the same login
(CSRF token) plus the license token that grants the right to fetch a file.
"""
import threading
import time

import requests

from core.normalization import extract_version_flags, normalize_text

GW_URL = "https://www.deezer.com/ajax/gw-light.php"
API_URL = "https://api.deezer.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
FLOW_BATCHES = 4  # Flow returns 12 new tracks per call; a snapshot keeps ~48.

_HOME_SUPPORT = ["channel", "flow", "playlist", "radio", "album", "artist", "smarttracklist"]


class DeezerAccountError(RuntimeError):
    pass


class DeezerSession:
    """One Deezer session: an ARL, its CSRF token, its license token and the
    sound quality that account is entitled to."""

    def __init__(self, arl=None):
        self.lock = threading.RLock()
        self.arl = None
        self.http = None
        self.token = None
        self.user = None
        self.license_token = None
        self.country = ""
        self.quality = {}
        if arl:
            self.login(arl)

    # ── Session ────────────────────────────────────────────────────────────────

    def login(self, arl):
        arl = (arl or "").strip()
        if not arl:
            raise DeezerAccountError("No Deezer account connected. Add your ARL in Settings.")
        http = requests.Session()
        http.headers["User-Agent"] = USER_AGENT
        http.cookies.set("arl", arl, domain=".deezer.com")
        resp = http.post(
            GW_URL,
            params={"method": "deezer.getUserData", "input": "3", "api_version": "1.0", "api_token": "null"},
            json={},
            timeout=30,
        ).json()
        results = resp.get("results") or {}
        user = results.get("USER") or {}
        if not user.get("USER_ID") or str(user["USER_ID"]) == "0":
            raise DeezerAccountError(
                "Deezer did not accept this ARL. It may have expired: copy a fresh one from your browser."
            )
        options = user.get("OPTIONS") or {}
        self.arl = arl
        self.http = http
        self.token = results.get("checkForm")
        self.user = {"id": str(user["USER_ID"]), "name": user.get("BLOG_NAME") or ""}
        self.license_token = options.get("license_token")
        # The catalogue the account may download from: its subscription country.
        self.country = options.get("license_country") or results.get("COUNTRY") or ""
        self.quality = options.get("web_sound_quality") or {}

    def reset(self, keep_arl=False):
        """Forgets the session. The ARL is kept when the session is only being
        renewed, so the next call can log in again."""
        if not keep_arl:
            self.arl = None
        self.http = self.token = self.user = None
        self.license_token = None
        self.country = ""
        self.quality = {}

    def is_premium(self):
        """True when the account may fetch lossless or high quality files."""
        return bool(self.quality.get("lossless") or self.quality.get("high"))

    def sound_format(self):
        """The format this account is entitled to, as Deezer names it."""
        if self.quality.get("lossless"):
            return "FLAC"
        if self.quality.get("high"):
            return "MP3_320"
        return "MP3_128"

    # ── Gateway ────────────────────────────────────────────────────────────────

    def gw(self, method, body=None, retry=True):
        """Calls the private gateway and returns its `results`."""
        with self.lock:
            if self.http is None:
                self.login(self.arl)
            resp = self.http.post(
                GW_URL,
                params={"method": method, "input": "3", "api_version": "1.0", "api_token": self.token},
                json=body or {},
                timeout=30,
            ).json()
            error = resp.get("error")
            if error and retry and ("VALID_TOKEN_REQUIRED" in str(error) or "NEED_API_AUTH_REQUIRED" in str(error)):
                # The token is stale: log in again and try once more.
                self.reset(keep_arl=True)
            elif error:
                raise DeezerAccountError(f"Deezer refused {method}: {error}")
            else:
                return resp.get("results")
        return self.gw(method, body, retry=False)


# One session per Deezer account (core/deezer_accounts.py), kept between calls.
_sessions = {}
_sessions_lock = threading.Lock()


def _account(account=None):
    from core import deezer_accounts

    account_id = account or deezer_accounts.default_id()
    if not account_id:
        raise DeezerAccountError("No Deezer account connected. Add one in Settings → Deezer accounts.")
    return account_id


def _session_for(account=None) -> DeezerSession:
    from core import deezer_accounts

    account_id = _account(account)
    if deezer_accounts.get(account_id) is None:
        raise DeezerAccountError("This Deezer account was removed from Settings → Deezer accounts.")
    arl = deezer_accounts.arl(account_id)
    if not arl:
        raise DeezerAccountError("This Deezer account has no ARL: add it in Settings → Deezer accounts.")
    with _sessions_lock:
        session = _sessions.setdefault(account_id, DeezerSession())
    with session.lock:
        if session.arl != arl or session.http is None:
            session.login(arl)
    return session


def _gw(method, body=None, retry=True, account=None):
    session = _session_for(account)
    with session.lock:
        return session.gw(method, body, retry)


def _status_of(session) -> dict:
    return {"connected": True, "name": session.user["name"], "user_id": session.user["id"],
            "premium": session.is_premium(), "country": session.country, "format": session.sound_format(),
            "error": None}


def account_status(account=None):
    """What a Deezer account is, without raising: {"connected", "name", "error"…}."""
    try:
        return _status_of(_session_for(account))
    except DeezerAccountError as e:
        return {"connected": False, "name": "", "premium": False, "error": str(e)}
    except Exception as e:
        return {"connected": False, "name": "", "premium": False, "error": f"Could not reach Deezer: {e}"}


def check_arl(arl):
    """Signs in with an ARL not saved yet, without keeping the session."""
    try:
        return _status_of(DeezerSession(arl))
    except DeezerAccountError as e:
        return {"connected": False, "name": "", "premium": False, "error": str(e)}
    except Exception as e:
        return {"connected": False, "name": "", "premium": False, "error": f"Could not reach Deezer: {e}"}


def forget_session(account=None):
    """Forgets the session of one account, or of all of them."""
    with _sessions_lock:
        sessions = [_sessions.pop(account, None)] if account else list(_sessions.values())
        if not account:
            _sessions.clear()
    for session in sessions:
        if session is not None:
            with session.lock:
                session.reset()


def _user_id(account=None):
    return _session_for(account).user["id"]


def favorite_artists(account=None):
    """[{id, name, picture}]. The public API answers for a public profile; a
    private one ("This user's profile is private") is read through the
    gateway, with the account's own session."""
    uid = _user_id(account)
    try:
        return _public_favorite_artists(uid)
    except DeezerAccountError as public_error:
        try:
            return _gateway_favorite_artists(uid, account)
        except DeezerAccountError as e:
            raise DeezerAccountError(f"{public_error}; through the account's own session: {e}") from e


def _public_favorite_artists(uid):
    """The public API, paginated: only for a profile that is not private."""
    artists, index = [], 0
    while True:
        page = requests.get(f"{API_URL}/user/{uid}/artists", params={"limit": 100, "index": index}, timeout=30).json()
        if "error" in page:
            raise DeezerAccountError(f"Deezer refused the favorite artists list: {page['error']}")
        data = page.get("data") or []
        artists += [
            {"id": str(a["id"]), "name": a.get("name") or "", "picture": a.get("picture_medium") or ""}
            for a in data
        ]
        index += len(data)
        if not data or index >= int(page.get("total") or 0):
            return artists


# More favorite artists than anyone keeps: the gateway answers them in one page.
GW_FAVORITES_LIMIT = 10000


def _gateway_favorite_artists(uid, account=None):
    """The profile page the account sees of itself, private or not."""
    results = _gw("deezer.pageProfile", {"USER_ID": uid, "tab": "artists", "nb": GW_FAVORITES_LIMIT}, account=account) or {}
    tab = (results.get("TAB") or {}).get("artists")
    if not isinstance(tab, dict):
        # An answer of another shape: say so rather than show an empty feed.
        raise DeezerAccountError("the profile page holds no artists list")
    return [
        {"id": str(a["ART_ID"]), "name": a.get("ART_NAME") or "", "picture": _cover_url(a.get("ART_PICTURE"), "artist", 250)}
        for a in tab.get("data") or []
        if str(a.get("ART_ID") or "").isdigit()
    ]


def _cover_url(md5, kind="cover", size=500):
    return f"https://e-cdns-images.dzcdn.net/images/{kind}/{md5}/{size}x{size}-000000-80-0-0.jpg" if md5 else ""


def available_mixes(account=None):
    """Mixes offered on the user's Deezer home: "made for you" smart tracklists
    and the Flow moods, plus the playlists Deezer recommends or the user follows."""
    support = {layout: _HOME_SUPPORT for layout in ("grid", "horizontal-grid", "slideshow", "long-card-horizontal-grid")}
    support["filterable-grid"] = ["flow"]
    page = _gw("page.get", {"PAGE": "home", "VERSION": "2.5", "SUPPORT": support, "LANG": "en"}, account=account)

    mixes, playlists = [], []
    for section in (page or {}).get("sections") or []:
        for item in section.get("items") or []:
            data = item.get("data") or {}
            if item.get("type") == "smarttracklist":
                mixes.append({
                    "kind": "stl",
                    "source_id": str(data.get("SMARTTRACKLIST_ID") or item.get("id")),
                    "title": data.get("TITLE") or item.get("title") or "Mix",
                    "subtitle": data.get("SUBTITLE") or data.get("DESCRIPTION") or "",
                    "group": section.get("title") or "Made for you",
                })
            elif item.get("type") == "flow":
                mixes.append({
                    "kind": "flow",
                    "source_id": str(data.get("id") or item.get("id") or "default"),
                    "title": item.get("title") or "Flow",
                    "subtitle": data.get("description") or "",
                    "group": section.get("title") or "Flow",
                })
            elif item.get("type") == "playlist":
                pid = str(data.get("PLAYLIST_ID") or item.get("id") or "")
                if pid.isdigit():
                    playlists.append({
                        "id": pid,
                        "title": item.get("title") or data.get("TITLE") or "",
                        "subtitle": item.get("subtitle") or "",
                        "picture": _cover_url(data.get("PLAYLIST_PICTURE"), "playlist", 250),
                        "group": section.get("title") or "Playlists",
                    })
    return {"mixes": mixes, "playlists": playlists}


def _song_to_track(song, position):
    title = song.get("SNG_TITLE") or ""
    version = (song.get("VERSION") or "").strip()
    if version and version.lower() not in title.lower():
        title = f"{title} {version}"
    artist = song.get("ART_NAME") or ""
    album = song.get("ALB_TITLE") or ""
    duration = song.get("DURATION")
    return {
        "position": position,
        "track_id": int(song["SNG_ID"]) if str(song.get("SNG_ID", "")).isdigit() else song.get("SNG_ID"),
        "title": title,
        "artist": artist,
        "album": album,
        "duration": int(duration) if str(duration or "").isdigit() else None,
        "picture": _cover_url(song.get("ALB_PICTURE")),
        "norm_title": normalize_text(title),
        "norm_artist": normalize_text(artist),
        "norm_album": normalize_text(album),
        "version_flags": extract_version_flags(title, artist),
    }


def mix_tracks(kind, source_id, account=None):
    """Current tracks of a mix, in the same shape as playlist tracks, read with
    the Deezer account whose mix it is."""
    if kind == "stl":
        results = _gw("smartTracklist.getSongs", {"SMARTTRACKLIST_ID": source_id}, account=account) or {}
        songs = results.get("data") or []
    elif kind == "flow":
        uid = _user_id(account)
        songs, seen = [], set()
        for _ in range(FLOW_BATCHES):
            body = {"USER_ID": uid} if source_id == "default" else {"USER_ID": uid, "CONFIG_ID": source_id}
            batch = (_gw("radio.getUserRadio", body, account=account) or {}).get("data") or []
            for song in batch:
                if song.get("SNG_ID") not in seen:
                    seen.add(song.get("SNG_ID"))
                    songs.append(song)
            time.sleep(0.2)
    else:
        raise DeezerAccountError(f"Unknown mix type: {kind}")
    return [_song_to_track(song, i) for i, song in enumerate(songs, start=1)]
