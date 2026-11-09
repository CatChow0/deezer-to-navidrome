"""The generated playlists' own state, in SQLite: what each mix already proposed
and the tracks on trial. Kept apart from stats.db, since Start clean empties the
listening history and a trial must outlive that.

Each Navidrome account has its own settings, mixes and quarantine: a track on
trial has a row for each profile that got it (core/trial.py), and meta keys
carry the account (core/mix_builder.py), except the install's, which keeps the
names it always had. What concerns
the library itself is shared: tempo and genres, the related artists, the
publications in Navidrome."""
import json
import sqlite3
from pathlib import Path

from core import config

# One row per track and profile: the profiles share the file, each has its verdict.
_TRIAL_TABLE = """
CREATE TABLE IF NOT EXISTS trial_tracks (
    deezer_id TEXT NOT NULL,
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
    reason TEXT NOT NULL DEFAULT '',
    account_id TEXT NOT NULL DEFAULT 'nd1',
    PRIMARY KEY (deezer_id, account_id)
)"""
_TRIAL_COLUMNS = ("deezer_id, track_key, artist, title, album, path, size, mix_id, downloaded_at, trial_ends_at,"
                  " state, state_at, reason, account_id")

_SCHEMA = _TRIAL_TABLE + """;
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
    analyzed_at INTEGER NOT NULL,
    write_error TEXT NOT NULL DEFAULT '',
    write_state TEXT NOT NULL DEFAULT '',
    write_tried_at INTEGER NOT NULL DEFAULT 0,
    original_mtime REAL,
    added_bpm TEXT,
    added_genre TEXT
);
CREATE TABLE IF NOT EXISTS write_journal (
    temp TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    started_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS repair_checked (
    path TEXT PRIMARY KEY,
    checked_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS album_genres (
    key TEXT PRIMARY KEY,
    genre TEXT NOT NULL DEFAULT '',
    checked_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS publications (
    playlist_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    navidrome_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    song_count INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    published_at INTEGER NOT NULL DEFAULT 0,
    tried_at INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    custom_title TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (playlist_id, account_id)
);
CREATE TABLE IF NOT EXISTS navidrome_playlists (
    account_id TEXT NOT NULL,
    navidrome_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    song_count INTEGER NOT NULL DEFAULT 0,
    duration INTEGER NOT NULL DEFAULT 0,
    cover_art TEXT NOT NULL DEFAULT '',
    changed TEXT NOT NULL DEFAULT '',
    synced_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, navidrome_id)
);
"""

# Columns added after a table was first made: CREATE TABLE IF NOT EXISTS leaves
# an existing table as it is.
_ADDED_COLUMNS = {
    "publications": {"custom_title": "TEXT NOT NULL DEFAULT ''"},
    # Whose quarantine the track is in: the tracks from before profiles are the
    # install's account's.
    "trial_tracks": {"account_id": "TEXT NOT NULL DEFAULT 'nd1'"},
}


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
    for table, columns in _ADDED_COLUMNS.items():
        present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in present:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    _shared_trial(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS trial_account ON trial_tracks(account_id)")
    return conn


def _keyed_by_account(conn) -> bool:
    return bool({row[1]: row[5] for row in conn.execute("PRAGMA table_info(trial_tracks)")}.get("account_id"))


def _shared_trial(conn) -> None:
    """Until the quarantine was shared, a track's Deezer ID was the key: one
    quarantine for each track. The table is rebuilt with the profile in its key,
    once, in one transaction, after a copy of the database."""
    if _keyed_by_account(conn):
        return
    conn.commit()
    backup = Path(config.DATA_DIR) / "backups" / "pre-1.16.0" / "mixes.db"
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        copy = sqlite3.connect(backup)
        try:
            conn.backup(copy)
        finally:
            copy.close()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if not _keyed_by_account(conn):
            conn.execute("ALTER TABLE trial_tracks RENAME TO trial_tracks_single")
            conn.execute("DROP INDEX IF EXISTS trial_state")
            conn.execute("DROP INDEX IF EXISTS trial_key")
            conn.execute(_TRIAL_TABLE)
            conn.execute(f"INSERT INTO trial_tracks({_TRIAL_COLUMNS}) SELECT {_TRIAL_COLUMNS} FROM trial_tracks_single")
            conn.execute("DROP TABLE trial_tracks_single")
            conn.execute("CREATE INDEX IF NOT EXISTS trial_state ON trial_tracks(state)")
            conn.execute("CREATE INDEX IF NOT EXISTS trial_key ON trial_tracks(track_key)")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


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
