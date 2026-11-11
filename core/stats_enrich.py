"""Fills what the sources did not say (length, genre, cover, Deezer ID) from
Deezer, a few tracks at a time, most played first.

A match needs both the title and an artist to agree, as lb-enricher's strict
rule did: a wrong match would put a wrong cover and wrong numbers on screen,
so a doubtful track is left unknown."""
import logging
import re
import sqlite3
import threading
import time
from contextlib import closing

from core import deezer, stats_covers, stats_db, stats_import
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


def _borrowed(account, key):
    """What another account's history already learned from Deezer about the
    same track, as a match: the people of one house share much of their music.
    Only what came from Deezer is taken."""
    for other in stats_db.accounts_with_history():
        if other == account:
            continue
        try:
            with closing(stats_db.connect(other)) as conn:
                row = conn.execute(
                    "SELECT deezer_track_id, deezer_album_id, cover_url, duration_sec, duration_source, genre, genre_source"
                    " FROM tracks WHERE key = ? AND deezer_track_id IS NOT NULL", (key,)).fetchone()
        except sqlite3.Error:
            continue
        if row:
            match = {"id": row["deezer_track_id"], "album": {"id": row["deezer_album_id"], "cover_big": row["cover_url"]},
                     "duration": row["duration_sec"] if row["duration_source"] == "deezer" else None}
            return match, row["genre"] if row["genre_source"] == "deezer" else None
    return None


def _save(account, track_id, key, match, genre) -> None:
    now = int(time.time())
    album = match.get("album") or {}
    artist = match.get("artist") or {}
    with closing(stats_db.connect(account)) as conn:
        # A rebuild during the wait can give this id to another track: the key says.
        saved = conn.execute(
            "UPDATE tracks SET deezer_track_id = ?, deezer_album_id = ?, cover_url = COALESCE(cover_url, ?),"
            " duration_source = CASE WHEN duration_sec IS NULL AND ? IS NOT NULL THEN 'deezer' ELSE duration_source END,"
            " duration_sec = COALESCE(duration_sec, ?),"
            " genre_source = CASE WHEN genre IS NULL AND ? IS NOT NULL THEN 'deezer' ELSE genre_source END,"
            " genre = COALESCE(genre, ?), lookup_at = ? WHERE id = ? AND key = ?",
            (str(match.get("id") or "") or None, str(album.get("id") or "") or None, album.get("cover_big") or album.get("cover_medium"),
             match.get("duration"), match.get("duration"), genre, genre, now + RETRY_INCOMPLETE, track_id, key),
        ).rowcount
        if saved:
            stats_covers.forget(conn, "track", key)
            stats_covers.forget_albums_of(conn, track_id)
        if saved and artist.get("name") and artist.get("id"):
            # The artist of a played track that matched on its title and artist: it wins
            # over a search by name, which homonyms share. The most played track comes
            # first (_pending), so the first track's artist stays. A new artist gets its
            # own picture, looked up again if this answer has none.
            artist_id, artist_key = str(artist["id"]), name_key(artist["name"])
            changed = conn.execute(
                "UPDATE artists SET picture_url = CASE WHEN deezer_id IS ? THEN COALESCE(picture_url, ?) ELSE ? END,"
                " lookup_at = CASE WHEN deezer_id IS ? THEN lookup_at ELSE NULL END,"
                " deezer_id = ?, deezer_source = 'track' WHERE key = ? AND deezer_source IS NOT 'track'",
                (artist_id, artist.get("picture_medium"), artist.get("picture_medium"), artist_id, artist_id, artist_key),
            ).rowcount
            if changed:
                stats_covers.forget(conn, "artist", artist_key)
        conn.commit()


def _retry_later(account, track_id, key, delay) -> None:
    with closing(stats_db.connect(account)) as conn:
        conn.execute("UPDATE tracks SET lookup_at = ? WHERE id = ? AND key = ?", (int(time.time()) + delay, track_id, key))
        conn.commit()


def enrich_batch(account, limit=40) -> int:
    """Looks up up to `limit` tracks of one account's history; the network wait
    holds no database lock."""
    with closing(stats_db.connect(account)) as conn:
        tracks = _pending(conn, limit)
    for track in tracks:
        borrowed = _borrowed(account, track["key"])
        if borrowed:
            _save(account, track["id"], track["key"], *borrowed)
            continue
        try:
            match, genre = _lookup(track)
        except Exception as e:
            logger.info("Deezer lookup failed for %s: %s", track["title"], e)
            _retry_later(account, track["id"], track["key"], RETRY_ERROR)
            continue
        if match:
            _save(account, track["id"], track["key"], match, genre)
        else:
            _retry_later(account, track["id"], track["key"], RETRY_NO_MATCH)
    _look_up_artists(account, limit)
    return len(tracks)


def _borrowed_artist(account, key):
    """What another account's history knows of the same artist, with where its ID
    came from: one a played track gave first."""
    for other in stats_db.accounts_with_history():
        if other == account:
            continue
        try:
            with closing(stats_db.connect(other)) as conn:
                row = conn.execute(
                    "SELECT deezer_id, picture_url, deezer_source FROM artists WHERE key = ? AND deezer_id IS NOT NULL"
                    " AND (deezer_source = 'track' OR picture_url IS NOT NULL)"
                    " ORDER BY deezer_source = 'track' DESC LIMIT 1", (key,)).fetchone()
        except sqlite3.Error:
            continue
        if row:
            return {"id": row["deezer_id"], "picture_big": row["picture_url"]}, row["deezer_source"] or "search"
    return None


def _played_track_id(account, artist_id):
    """The Deezer ID of this artist's most played track that matched, the ones
    where it comes first before those where it is featured."""
    with closing(stats_db.connect(account)) as conn:
        row = conn.execute(
            "SELECT t.deezer_track_id FROM tracks t JOIN track_artists ta ON ta.track_id = t.id"
            " JOIN plays p ON p.track_id = t.id WHERE ta.artist_id = ? AND t.deezer_track_id IS NOT NULL"
            " GROUP BY t.id ORDER BY MIN(ta.position), COUNT(*) DESC LIMIT 1", (artist_id,)).fetchone()
    return row["deezer_track_id"] if row else None


def _identify(account, artist):
    """(Deezer artist, "track" | "search") or (None, None). Homonyms share a name
    (Deezer lists four "PLK"), so a name is the last resort."""
    key = artist["key"]
    if artist["deezer_source"] == "track" and artist["deezer_id"]:
        # Known from a played track: only its photo may be missing.
        if artist["picture_url"]:
            return {"id": artist["deezer_id"]}, "track"
        found = deezer._public_api(f"/artist/{artist['deezer_id']}")
        return {**(found or {}), "id": artist["deezer_id"]}, "track"
    borrowed = _borrowed_artist(account, key)
    if borrowed and borrowed[1] == "track":
        return borrowed
    track_id = _played_track_id(account, artist["id"])
    if track_id:
        # The artist credited on a track this profile played: the right one.
        track = deezer._public_api(f"/track/{track_id}") or {}
        credited = [track.get("artist") or {}, *(track.get("contributors") or [])]
        same = next((a for a in credited if a.get("id") and name_key(a.get("name") or "") == key), None)
        if same:
            return same, "track"
    if borrowed:
        return borrowed
    found = deezer._public_api("/search/artist", {"q": artist["name"], "limit": 10})
    named = [i for i in (found or {}).get("data") or [] if i.get("id") and name_key(i.get("name") or "") == key]
    if not named:
        return None, None
    # Of the artists with this name, the one most people follow; only for its photo.
    return max(named, key=lambda i: int(i.get("nb_fan") or 0)), "search"


def _look_up_artists(account, limit) -> None:
    """Finds each artist on Deezer, for its photo and for the mixes: through a
    track this profile played when it can, by its name otherwise."""
    with closing(stats_db.connect(account)) as conn:
        artists = conn.execute(
            "SELECT a.id, a.key, a.name, a.deezer_id, a.deezer_source, a.picture_url FROM artists a"
            " JOIN track_artists ta ON ta.artist_id = a.id"
            " JOIN plays p ON p.track_id = ta.track_id WHERE a.lookup_at IS NULL OR a.lookup_at <= ?"
            " GROUP BY a.id ORDER BY COUNT(*) DESC, a.id LIMIT ?",
            (int(time.time()), limit),
        ).fetchall()
    for artist in artists:
        match, source, delay = None, None, RETRY_NO_MATCH
        try:
            match, source = _identify(account, artist)
        except Exception as e:
            logger.info("Deezer lookup failed for %s: %s", artist["name"], e)
            delay = RETRY_ERROR
        picture = (match or {}).get("picture_big") or (match or {}).get("picture_medium")
        found_id = str((match or {}).get("id") or "") or None
        with closing(stats_db.connect(account)) as conn:
            if found_id:
                # A search by name never replaces an artist a played track gave.
                # Another artist than before drops the old one's photo.
                conn.execute(
                    "UPDATE artists SET picture_url = CASE WHEN deezer_id IS ? THEN COALESCE(?, picture_url) ELSE ? END,"
                    " deezer_id = ?, deezer_source = ?, lookup_at = ?"
                    " WHERE id = ? AND key = ? AND (deezer_source IS NOT 'track' OR ? = 'track')",
                    (found_id, picture, picture, found_id, source, int(time.time()) + RETRY_INCOMPLETE,
                     artist["id"], artist["key"], source),
                )
                stats_covers.forget(conn, "artist", artist["key"])
            else:
                conn.execute("UPDATE artists SET lookup_at = ? WHERE id = ? AND key = ?",
                             (int(time.time()) + delay, artist["id"], artist["key"]))
            conn.commit()


def progress(conn) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    pending = conn.execute(
        f"SELECT COUNT(*) FROM tracks t WHERE {_MISSING} AND {_DUE}", (int(time.time()),)
    ).fetchone()[0]
    return {"pending": pending, "done": total - pending}


def start_background_batch() -> bool:
    """Starts a batch unless one, or a rebuild, is already running. It also waits for
    Fix Missing Metadata: both use the same Deezer quota, per address."""
    from core.metadata_fix import is_running as fixing_metadata

    if stats_import.import_running() or fixing_metadata() or not _busy.acquire(blocking=False):
        return False

    def work():
        try:
            # Each history in turn: the Deezer quota is the same for all.
            for account in stats_db.accounts_with_history():
                enrich_batch(account)
                stats_covers.resolve_batch(account)
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
