"""Release feed: recent albums, EPs and singles from the user's favorite
Deezer artists. Refreshing walks every artist's discography (one public API
call each), so the result is cached in data/releases.json."""
import json
import threading
import time
from datetime import date, timedelta

import requests

from core.config import DATA_DIR, ensure_dirs, load_config
from core.deezer_account import API_URL, favorite_artists

RELEASES_FILE = DATA_DIR / "releases.json"
PREFS_FILE = DATA_DIR / "release_prefs.json"
refresh_lock = threading.Lock()
WINDOW_DAYS = 180
# Deezer allows 50 requests per 5 seconds; stay well under it.
REQUEST_GAP_SECONDS = 0.15


def load_releases():
    try:
        return json.loads(RELEASES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": None, "artists": 0, "window_days": WINDOW_DAYS, "releases": []}


def refresh_hours():
    """Hours between automatic refreshes, from Settings; 0 means manual only."""
    try:
        return max(0, int(load_config().get("release_refresh_hours", 24)))
    except (TypeError, ValueError):
        return 24


def is_stale():
    hours = refresh_hours()
    if hours == 0:
        return False
    updated = load_releases().get("updated_at")
    return not updated or time.time() - updated > hours * 3600


def _artist_releases(artist, since):
    """Recent releases listed in a followed artist's discography. Deezer also
    lists releases the artist only appears on; the album details tell them apart."""
    found = []
    index = 0
    while True:
        page = requests.get(
            f"{API_URL}/artist/{artist['id']}/albums", params={"limit": 100, "index": index}, timeout=30
        ).json()
        data = page.get("data") or []
        for album in data:
            released = album.get("release_date") or ""
            if released >= since:
                found.append({
                    "id": str(album["id"]),
                    "title": album.get("title") or "",
                    "cover": album.get("cover_medium") or "",
                    "release_date": released,
                    "record_type": album.get("record_type") or "album",
                    "explicit": bool(album.get("explicit_lyrics")),
                })
        index += len(data)
        if not data or index >= int(page.get("total") or 0) or "next" not in page:
            return found
        time.sleep(REQUEST_GAP_SECONDS)


def load_prefs():
    try:
        prefs = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    except Exception:
        prefs = {}
    prefs.setdefault("muted", {})
    return prefs


def set_muted(artist_id, name, muted):
    """Muted artists stay in the Deezer favorites but leave the feed."""
    prefs = load_prefs()
    if muted:
        prefs["muted"][str(artist_id)] = name
    else:
        prefs["muted"].pop(str(artist_id), None)
    ensure_dirs()
    PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    return prefs


def refresh_releases(progress_cb=None):
    def emit(message=None, progress=None, stage=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage)

    emit("Reading your favorite artists", stage="artists", progress=0)
    artists = favorite_artists()
    muted = load_prefs()["muted"]
    since = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()

    releases, failed = {}, 0
    counts = {}
    for i, artist in enumerate(artists, start=1):
        if artist["id"] in muted:
            continue
        try:
            for release in _artist_releases(artist, since):
                entry = releases.setdefault(release["id"], {**release, "followed": []})
                entry["followed"].append({"id": artist["id"], "name": artist["name"]})
                counts[artist["id"]] = counts.get(artist["id"], 0) + 1
        except Exception:
            failed += 1
        emit(f"{i}/{len(artists)}: {artist['name']}", stage="releases", progress=round(i / max(1, len(artists)) * 100))
        time.sleep(REQUEST_GAP_SECONDS)

    # Album details give the real main artist and the track count.
    previous = {r["id"]: r for r in load_releases().get("releases", [])}
    for i, release in enumerate(releases.values(), start=1):
        known = previous.get(release["id"], {})
        if known.get("artist_id") and known.get("nb_tracks") and "featured" in known:
            details = {k: known[k] for k in ("artist", "artist_id", "nb_tracks")}
        else:
            try:
                album = requests.get(f"{API_URL}/album/{release['id']}", timeout=30).json()
                details = {
                    "artist": (album.get("artist") or {}).get("name") or release["followed"][0]["name"],
                    "artist_id": str((album.get("artist") or {}).get("id") or release["followed"][0]["id"]),
                    "nb_tracks": album.get("nb_tracks") or 0,
                }
            except Exception:
                details = {"artist": release["followed"][0]["name"], "artist_id": release["followed"][0]["id"], "nb_tracks": 0}
            emit(f"Release details {i}/{len(releases)}", stage="details", progress=round(i / max(1, len(releases)) * 100))
            time.sleep(REQUEST_GAP_SECONDS)
        release.update(details)
        # A followed artist only appears on it (guest, compilation) when none of them is the main artist.
        release["featured"] = all(f["id"] != release["artist_id"] for f in release["followed"])

    feed = {
        "updated_at": int(time.time()),
        "artists": len(artists),
        "failed_artists": failed,
        "window_days": WINDOW_DAYS,
        "followed_artists": [
            {"id": a["id"], "name": a["name"], "picture": a.get("picture", ""), "releases": counts.get(a["id"], 0)}
            for a in artists
        ],
        "releases": sorted(releases.values(), key=lambda r: (r["release_date"], r["artist"]), reverse=True),
    }
    ensure_dirs()
    RELEASES_FILE.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    return feed
