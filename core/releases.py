"""Release feed: recent albums, EPs and singles from the favorite artists of a
Deezer account. Refreshing walks every artist's discography (one public API
call each), so the result is cached: data/releases.json for the first account
(dz1, the single account of older versions), releases-<id>.json for the others.
The muted artists are kept per account the same way. Without an account given,
the default one."""
import json
import threading
import time
from datetime import date, timedelta
from pathlib import Path


from core import files
from core.config import DATA_DIR, load_config
from core.deezer_account import favorite_artists

RELEASES_FILE = DATA_DIR / "releases.json"
PREFS_FILE = DATA_DIR / "release_prefs.json"
WINDOW_DAYS = 180
# Deezer allows 50 requests per 5 seconds; stay well under it.
REQUEST_GAP_SECONDS = 0.15
_locks = {}
_locks_guard = threading.Lock()


def _account(account=None):
    from core import deezer_accounts

    return account or deezer_accounts.default_id() or "dz1"


def _files(account=None):
    account_id = _account(account)
    if account_id == "dz1":
        return RELEASES_FILE, PREFS_FILE
    return Path(DATA_DIR) / f"releases-{account_id}.json", Path(DATA_DIR) / f"release_prefs-{account_id}.json"


def forget_account(account_id) -> None:
    """The feed and muted artists of a Deezer account that was removed."""
    for path in _files(account_id):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def lock_for(account=None) -> threading.Lock:
    """One refresh at a time for each account."""
    with _locks_guard:
        return _locks.setdefault(_account(account), threading.Lock())


def load_releases(account=None):
    try:
        return json.loads(_files(account)[0].read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": None, "artists": 0, "window_days": WINDOW_DAYS, "releases": []}


def refresh_hours():
    """Hours between automatic refreshes, from Settings; 0 means manual only."""
    try:
        return max(0, int(load_config().get("release_refresh_hours", 24)))
    except (TypeError, ValueError):
        return 24


def is_stale(account=None):
    hours = refresh_hours()
    if hours == 0:
        return False
    updated = load_releases(account).get("updated_at")
    return not updated or time.time() - updated > hours * 3600


def _artist_releases(artist, since):
    """Recent releases listed in a followed artist's discography. Deezer also
    lists releases the artist only appears on; the album details tell them apart."""
    # Through the shared pace of the public API: a quota answer was read as
    # "no release", and the artist dropped out of the feed without a word. An
    # error is raised now, and the artist counts as failed.
    from core.deezer import public_pages

    found = []
    for album in public_pages(f"/artist/{artist['id']}/albums"):
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
    return found


def load_prefs(account=None):
    try:
        prefs = json.loads(_files(account)[1].read_text(encoding="utf-8"))
    except Exception:
        prefs = {}
    prefs.setdefault("muted", {})
    return prefs


def set_muted(artist_id, name, muted, account=None):
    """Muted artists stay in the Deezer favorites but leave the feed."""
    prefs = load_prefs(account)
    if muted:
        prefs["muted"][str(artist_id)] = name
    else:
        prefs["muted"].pop(str(artist_id), None)
    files.write_json(_files(account)[1], prefs)
    return prefs


def refresh_releases(progress_cb=None, account=None):
    def emit(message=None, progress=None, stage=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage)

    emit("Reading your favorite artists", stage="artists", progress=0)
    artists = favorite_artists(_account(account))
    muted = load_prefs(account)["muted"]
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
    previous = {r["id"]: r for r in load_releases(account).get("releases", [])}
    for i, release in enumerate(releases.values(), start=1):
        known = previous.get(release["id"], {})
        if known.get("artist_id") and known.get("nb_tracks") and "featured" in known:
            details = {k: known[k] for k in ("artist", "artist_id", "nb_tracks")}
        else:
            try:
                from core.deezer import _public_api

                album = _public_api(f"/album/{release['id']}")
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
    files.write_json(_files(account)[0], feed)
    return feed
