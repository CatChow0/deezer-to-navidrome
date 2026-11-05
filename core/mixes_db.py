"""The generated playlists' own state, in SQLite: what each mix already proposed
and the tracks on trial. Kept apart from stats.db, since Start clean empties the
listening history and a trial must outlive that."""
import json
import sqlite3
from pathlib import Path

from core import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_tracks (
    deezer_id TEXT PRIMARY KEY,
    track_key TEXT NOT NULL,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    album TEXT NOT NULL DEFAULT '',
    path TEXT,
    size INTEGER NOT NULL DEFAULT 0,
    mix_id TEXT NOT NULL DEFAULT '',
    downloaded_at INTEGER NOT NULL,
    trial_ends_at INTEGER NOT NULL,
    state TEXT NOT NULL,
    state_at INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS trial_state ON trial_tracks(state);
CREATE INDEX IF NOT EXISTS trial_key ON trial_tracks(track_key);
CREATE TABLE IF NOT EXISTS mix_history (
    mix_id TEXT NOT NULL,
    track_key TEXT NOT NULL,
    used_at INTEGER NOT NULL,
    PRIMARY KEY (mix_id, track_key)
);
CREATE TABLE IF NOT EXISTS related_cache (
    artist_id TEXT PRIMARY KEY,
    related TEXT NOT NULL,
    fetched_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS track_features (
    path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    bpm REAL,
    genre TEXT,
    analyzed_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def db_path() -> Path:
    return Path(config.DATA_DIR) / "mixes.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(conn, key, value) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, json.dumps(value)))
    conn.commit()


def remember(conn, mix_id, keys, when) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO mix_history(mix_id, track_key, used_at) VALUES (?, ?, ?)",
        [(mix_id, key, int(when)) for key in keys],
    )
    conn.commit()


def recent_keys(conn, mix_id, since) -> set:
    rows = conn.execute("SELECT track_key FROM mix_history WHERE mix_id=? AND used_at>=?", (mix_id, int(since)))
    return {row[0] for row in rows}
