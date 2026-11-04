"""The listening history: plays, the tracks and artists they point to, in SQLite.

Each play keeps the album and length of what was actually played, since one
track can appear on several albums, in versions of different lengths."""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from core import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    deezer_id TEXT,
    picture_url TEXT
);
CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    album_artist TEXT NOT NULL DEFAULT '',
    cover_url TEXT
);
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    artist_display TEXT NOT NULL DEFAULT '',
    duration_sec REAL,
    duration_source TEXT,
    genre TEXT,
    genre_source TEXT,
    deezer_track_id TEXT,
    deezer_album_id TEXT,
    cover_url TEXT,
    lookup_at INTEGER
);
CREATE TABLE IF NOT EXISTS track_artists (
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (track_id, artist_id)
);
CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    album_id INTEGER REFERENCES albums(id),
    duration_sec REAL,
    listened_at INTEGER NOT NULL,
    source TEXT NOT NULL,
    UNIQUE (track_id, listened_at)
);
CREATE INDEX IF NOT EXISTS plays_listened_at ON plays(listened_at);
CREATE INDEX IF NOT EXISTS plays_album ON plays(album_id);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_FEAT_BRACKET = re.compile(r"[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\b[^\)\]]*[\)\]]", re.I)
_FEAT_INLINE = re.compile(r"\s(?:feat\.?|ft\.?|featuring)\s.*$", re.I)


def db_path() -> Path:
    return Path(config.DATA_DIR) / "stats.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


def fold(text) -> str:
    """Accents and case removed, for comparing and searching names."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _clean(text) -> str:
    """fold() without punctuation; falls back on the folded text, so a name
    made only of punctuation still has a usable, distinct form."""
    folded = fold(text)
    cleaned = " ".join(re.sub(r"[^\w]+", " ", folded.replace("&", " and ")).split())
    return cleaned or " ".join(folded.split())


def name_key(name) -> str:
    return _clean(name)


def clean_title(title) -> str:
    """The title without its featured artists; version markers stay."""
    return _FEAT_INLINE.sub("", _FEAT_BRACKET.sub(" ", str(title or "")))


def title_key(title) -> str:
    return _clean(clean_title(title)) or _clean(title)


def split_artists(value) -> list:
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(" • ")
    return [str(item).strip() for item in items if item and str(item).strip()]


def track_key(artists, title) -> str:
    """First credited artist + title. Only the first artist: sources credit
    featured artists differently, and that must not make it a new track."""
    names = split_artists(artists)
    return f"{name_key(names[0]) if names else ''}|{title_key(title)}"


def upsert_artist(conn, name) -> int:
    key = name_key(name)
    row = conn.execute("SELECT id FROM artists WHERE key=?", (key,)).fetchone()
    if row:
        return row[0]
    return conn.execute("INSERT INTO artists(key, name) VALUES (?, ?)", (key, name)).lastrowid


def set_track_artists(conn, track_id, artists) -> None:
    conn.execute("DELETE FROM track_artists WHERE track_id=?", (track_id,))
    for position, name in enumerate(split_artists(artists)):
        conn.execute(
            "INSERT OR IGNORE INTO track_artists(track_id, artist_id, position) VALUES (?, ?, ?)",
            (track_id, upsert_artist(conn, name), position),
        )


def upsert_track(conn, title, artists, *, duration=None, duration_source=None, genre=None, genre_source=None) -> int:
    names = split_artists(artists)
    key = track_key(names, title)
    row = conn.execute("SELECT id, duration_sec, genre FROM tracks WHERE key=?", (key,)).fetchone()
    if row is None:
        track_id = conn.execute(
            "INSERT INTO tracks(key, title, artist_display, duration_sec, duration_source, genre, genre_source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, title, " • ".join(dict.fromkeys(names)), duration, duration_source if duration else None,
             genre, genre_source if genre else None),
        ).lastrowid
        set_track_artists(conn, track_id, names)
        return track_id
    track_id = row["id"]
    if duration and not row["duration_sec"]:
        conn.execute("UPDATE tracks SET duration_sec=?, duration_source=? WHERE id=?", (duration, duration_source, track_id))
    if genre and not row["genre"]:
        conn.execute("UPDATE tracks SET genre=?, genre_source=? WHERE id=?", (genre, genre_source, track_id))
    return track_id


def upsert_album(conn, title, album_artist):
    title = str(title or "").strip()
    if not title:
        return None
    album_artist = str(album_artist or "").strip()
    key = f"{name_key(album_artist)}|{_clean(title)}"
    row = conn.execute("SELECT id FROM albums WHERE key=?", (key,)).fetchone()
    if row:
        return row[0]
    return conn.execute("INSERT INTO albums(key, title, album_artist) VALUES (?, ?, ?)", (key, title, album_artist)).lastrowid


def add_play(conn, track_id, album_id, duration_sec, listened_at, source) -> bool:
    """Commits are the caller's: a batch or an import is one transaction."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO plays(track_id, album_id, duration_sec, listened_at, source) VALUES (?, ?, ?, ?, ?)",
        (track_id, album_id, duration_sec, int(listened_at), source),
    )
    return cursor.rowcount > 0


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(conn, key, value) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, json.dumps(value)))


def play_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
