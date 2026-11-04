"""Plays Navidrome sends as they happen, in the ListenBrainz format, and the
token that lets it send them (separate from the read-only API token)."""
import hmac
import secrets

from core import stats_db
from core.config import load_secret, save_secret, secret_from_env
from core.stats_import import library_durations


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


def _duration(meta):
    info = meta.get("additional_info")
    if not isinstance(info, dict):
        return None
    value = info.get("duration_ms")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return value / 1000
    value = info.get("duration")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _parse(item):
    """(listened_at, title, artists, album, duration), or None for an unusable entry."""
    if not isinstance(item, dict):
        return None
    moment = item.get("listened_at")
    meta = item.get("track_metadata")
    if isinstance(moment, bool) or not isinstance(moment, int) or moment <= 0 or not isinstance(meta, dict):
        return None
    title, artist = meta.get("track_name"), meta.get("artist_name")
    if not isinstance(title, str) or not title.strip() or not isinstance(artist, str) or not artist.strip():
        return None
    album = meta.get("release_name")
    return moment, title.strip(), stats_db.split_artists(artist), album if isinstance(album, str) else None, _duration(meta)


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
                album_id = stats_db.upsert_album(conn, album, artists[0])
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
