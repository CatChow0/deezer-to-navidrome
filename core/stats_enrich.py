"""Fills what the sources did not say (length, genre, cover, Deezer ID) from
Deezer, a few tracks at a time, most played first.

A match needs both the title and an artist to agree, as lb-enricher's strict
rule did: a wrong match would put a wrong cover and wrong numbers on screen,
so a doubtful track is left unknown."""
import logging
import re
import threading
import time
from contextlib import closing

from core import deezer, stats_db, stats_import
from core.stats_db import clean_title, name_key, split_artists, title_key

logger = logging.getLogger(__name__)

RETRY_NO_MATCH = 7 * 86400
RETRY_ERROR = 3600
RETRY_INCOMPLETE = 30 * 86400
MIN_SCORE = 0.9

_VERSION_MARKER = re.compile(
    r"\b(remix|rmx|live|instrumental|instr|acapella|a cappella|demo|session|radio edit|radio mix|extended|acoustic|sped up|slowed)\b"
)
_busy = threading.Lock()

_MISSING = "(t.deezer_track_id IS NULL OR t.duration_sec IS NULL OR t.genre IS NULL OR t.cover_url IS NULL)"
_DUE = "(t.lookup_at IS NULL OR t.lookup_at <= ?)"


def _score(a, b) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return 0.9 if a in b or b in a else 0.0


def _markers(title) -> set:
    return set(_VERSION_MARKER.findall(stats_db.fold(title)))


def deezer_match(title, artists, item) -> bool:
    found_title = item.get("title") or ""
    found_artist = (item.get("artist") or {}).get("name") or ""
    if _markers(title) != _markers(found_title):
        return False
    artist_score = max((_score(name_key(a), name_key(found_artist)) for a in split_artists(artists)), default=0.0)
    return min(_score(title_key(title), title_key(found_title)), artist_score) >= MIN_SCORE


def _pending(conn, limit) -> list:
    return conn.execute(
        "SELECT t.id, t.key, t.title, t.artist_display, t.genre, COUNT(p.id) plays FROM tracks t JOIN plays p ON p.track_id = t.id"
        f" WHERE {_MISSING} AND {_DUE} GROUP BY t.id ORDER BY plays DESC, t.id LIMIT ?",
        (int(time.time()), limit),
    ).fetchall()


def _lookup(track) -> tuple:
    """(matching Deezer track or None, its album's first genre or None)."""
    artists = split_artists(track["artist_display"])
    query = " ".join(f"{artists[0] if artists else ''} {clean_title(track['title'])}".split())
    found = deezer._public_api("/search/track", {"q": query, "limit": 10})
    match = next((item for item in (found or {}).get("data") or [] if deezer_match(track["title"], artists, item)), None)
    genre = None
    if match and not track["genre"] and (match.get("album") or {}).get("id"):
        album = deezer._public_api(f"/album/{match['album']['id']}")
        genres = ((album or {}).get("genres") or {}).get("data") or []
        genre = genres[0].get("name") if genres else None
    return match, genre


def _save(track_id, key, match, genre) -> None:
    now = int(time.time())
    album = match.get("album") or {}
    artist = match.get("artist") or {}
    with closing(stats_db.connect()) as conn:
        # A rebuild during the wait can give this id to another track: the key says.
        saved = conn.execute(
            "UPDATE tracks SET deezer_track_id = ?, deezer_album_id = ?, cover_url = COALESCE(cover_url, ?),"
            " duration_source = CASE WHEN duration_sec IS NULL AND ? IS NOT NULL THEN 'deezer' ELSE duration_source END,"
            " duration_sec = COALESCE(duration_sec, ?),"
            " genre_source = CASE WHEN genre IS NULL AND ? IS NOT NULL THEN 'deezer' ELSE genre_source END,"
            " genre = COALESCE(genre, ?), lookup_at = ? WHERE id = ? AND key = ?",
            (str(match.get("id") or "") or None, str(album.get("id") or "") or None, album.get("cover_medium"),
             match.get("duration"), match.get("duration"), genre, genre, now + RETRY_INCOMPLETE, track_id, key),
        ).rowcount
        if saved and artist.get("name"):
            conn.execute(
                "UPDATE artists SET deezer_id = COALESCE(deezer_id, ?), picture_url = COALESCE(picture_url, ?) WHERE key = ?",
                (str(artist.get("id") or "") or None, artist.get("picture_medium"), name_key(artist["name"])),
            )
        conn.commit()


def _retry_later(track_id, key, delay) -> None:
    with closing(stats_db.connect()) as conn:
        conn.execute("UPDATE tracks SET lookup_at = ? WHERE id = ? AND key = ?", (int(time.time()) + delay, track_id, key))
        conn.commit()


def enrich_batch(limit=40) -> int:
    """Looks up up to `limit` tracks; the network wait holds no database lock."""
    with closing(stats_db.connect()) as conn:
        tracks = _pending(conn, limit)
    for track in tracks:
        try:
            match, genre = _lookup(track)
        except Exception as e:
            logger.info("Deezer lookup failed for %s: %s", track["title"], e)
            _retry_later(track["id"], track["key"], RETRY_ERROR)
            continue
        if match:
            _save(track["id"], track["key"], match, genre)
        else:
            _retry_later(track["id"], track["key"], RETRY_NO_MATCH)
    return len(tracks)


def progress(conn) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    pending = conn.execute(
        f"SELECT COUNT(*) FROM tracks t WHERE {_MISSING} AND {_DUE}", (int(time.time()),)
    ).fetchone()[0]
    return {"pending": pending, "done": total - pending}


def start_background_batch() -> bool:
    """Starts a batch unless one, or a rebuild, is already running."""
    if stats_import.import_running() or not _busy.acquire(blocking=False):
        return False

    def work():
        try:
            enrich_batch()
        except Exception as e:
            logger.error("Stats lookups failed: %s", e)
        finally:
            _busy.release()

    try:
        threading.Thread(target=work, daemon=True, name="stats-enrich").start()
    except BaseException:
        _busy.release()
        raise
    return True
