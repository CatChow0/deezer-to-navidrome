"""Plays Navidrome sends as they happen, in the ListenBrainz format, and the
token that lets it send them (separate from the read-only API token)."""
import hmac
import math
import secrets
import time

from core import stats_db
from core.config import load_secret, save_secret, secret_from_env
from core.stats_import import library_durations

# Plays outside this range would break every chart that includes them: a time
# in milliseconds is thousands of years away.
EARLIEST_PLAY = 946684800  # 2000-01-01
LATEST_AHEAD = 86400
LONGEST_TRACK = 7 * 86400


def scrobble_token() -> str:
    return load_secret("scrobble_token")


def token_from_env() -> bool:
    return secret_from_env("scrobble_token")


def new_scrobble_token() -> str:
    token = secrets.token_urlsafe(32)
    save_secret("scrobble_token", token)
    return token


def set_scrobble_token(value: str) -> None:
    save_secret("scrobble_token", (value or "").strip())


def token_valid(header) -> bool:
    expected = scrobble_token()
    scheme, _, sent = (header or "").strip().partition(" ")
    if not expected or scheme.lower() != "token":
        return False
    return bool(sent.strip()) and hmac.compare_digest(sent.strip().encode(), expected.encode())


def _seconds(value, unit=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        seconds = value / unit
    except OverflowError:
        return None
    return seconds if math.isfinite(seconds) and 0 < seconds <= LONGEST_TRACK else None


def _duration(meta):
    info = meta.get("additional_info")
    if not isinstance(info, dict):
        return None
    return _seconds(info.get("duration_ms"), 1000) or _seconds(info.get("duration"))


def _text(value):
    """Clean text, or None when it is missing or cannot be stored."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        value.encode("utf-8")
    except UnicodeError:
        return None
    return value.strip()


def _parse(item):
    """(listened_at, title, artists, album, duration), or None for an unusable entry."""
    if not isinstance(item, dict):
        return None
    moment = item.get("listened_at")
    meta = item.get("track_metadata")
    if isinstance(moment, bool) or not isinstance(moment, int) or not isinstance(meta, dict):
        return None
    if not EARLIEST_PLAY <= moment <= time.time() + LATEST_AHEAD:
        return None
    title, artist = _text(meta.get("track_name")), _text(meta.get("artist_name"))
    artists = stats_db.split_artists(artist)
    if not title or not artists:
        return None
    return moment, title, artists, _text(meta.get("release_name")), _duration(meta)


def _album_id(conn, track_id, album, artists):
    """The album this play belongs to. The first credit is often not the album
    artist, so an album the track or its artists already have comes first."""
    if not album:
        return None
    wanted = stats_db.album_key("", album).split("|", 1)[1]
    for row in conn.execute(
        "SELECT DISTINCT al.id, al.key FROM plays p JOIN albums al ON al.id = p.album_id WHERE p.track_id = ?", (track_id,)
    ).fetchall():
        if row["key"].split("|", 1)[1] == wanted:
            return row["id"]
    for name in artists:
        row = conn.execute("SELECT id FROM albums WHERE key = ?", (stats_db.album_key(name, album),)).fetchone()
        if row:
            return row["id"]
    return stats_db.upsert_album(conn, album, artists[0])


def record_listens(payload: list) -> dict:
    """Stores the usable entries of a batch. A database error leaves the whole
    batch unsaved and goes up to the caller, so Navidrome can send it again."""
    result = {"added": 0, "duplicate": 0, "skipped": 0}
    parsed = []
    for item in payload:
        entry = _parse(item)
        if entry is None:
            result["skipped"] += 1
        else:
            parsed.append(entry)
    if not parsed:
        return result

    durations = library_durations()
    conn = stats_db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for moment, title, artists, album, duration in parsed:
                known = durations.get(stats_db.track_key(artists, title))
                track_id = stats_db.upsert_track(
                    conn, title, artists,
                    duration=duration or known,
                    duration_source="navidrome" if duration else "library",
                )
                album_id = _album_id(conn, track_id, album, artists)
                if stats_db.add_play(conn, track_id, album_id, duration or known, moment, "live"):
                    result["added"] += 1
                else:
                    result["duplicate"] += 1
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    return result
