"""The listening history: plays, the tracks and artists they point to, in SQLite.

Each play keeps the album and length of what was actually played, since one
track can appear on several albums, in versions of different lengths.

Each Navidrome account has its own history, in its own database: the first
one, made from the install, keeps stats.db where it always was; the others
have stats/<id>.db. Every caller names the account: there is no default, so
that nothing can read the wrong one by forgetting it."""
import json
import logging
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

from core import config

logger = logging.getLogger(__name__)

FIRST_ACCOUNT = "nd1"
_ACCOUNT_ID = re.compile(r"^nd[1-9][0-9]*$")

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
CREATE TABLE IF NOT EXISTS maloja_pairs (
    maloja_ts INTEGER PRIMARY KEY,
    partner_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS covers (
    kind TEXT NOT NULL,
    item_key TEXT NOT NULL,
    file TEXT,
    color TEXT,
    source TEXT,
    checked_at INTEGER NOT NULL,
    retry_at INTEGER,
    PRIMARY KEY (kind, item_key)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Columns added since the first release. Existing databases get them on opening.
_ADDED_COLUMNS = (
    ("tracks", "file_path", "TEXT"),
    ("albums", "file_path", "TEXT"),
    ("artists", "lookup_at", "INTEGER"),
)
_SCHEMA_VERSION = 2

_FEAT_BRACKET = re.compile(r"[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\b[^\)\]]*[\)\]]", re.I)
_FEAT_INLINE = re.compile(r"\s(?:feat\.?|ft\.?|featuring)\s.*$", re.I)
_FEAT_SPLIT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+", re.I)


def checked_account(account) -> str:
    """The account ID, refused unless it has the shape of one: it names a file."""
    account = str(account or "")
    if not _ACCOUNT_ID.match(account):
        raise ValueError(f"Not a Navidrome account: {account!r}")
    return account


def db_path(account) -> Path:
    account = checked_account(account)
    if account == FIRST_ACCOUNT:
        return Path(config.DATA_DIR) / "stats.db"
    return Path(config.DATA_DIR) / "stats" / f"{account}.db"


def has_history(account) -> bool:
    return db_path(account).exists()


def accounts_with_history() -> list:
    """The accounts whose history exists, in the order of Settings: for what
    reads every history, as the library is shared."""
    from core import nd_accounts

    try:
        ids = [a["id"] for a in nd_accounts.list_accounts()] or [FIRST_ACCOUNT]
    except Exception as e:
        logger.error("Could not read the Navidrome accounts: %s", e)
        ids = [FIRST_ACCOUNT]
    return [account for account in ids if has_history(account)]


def connect(account) -> sqlite3.Connection:
    path = db_path(account)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn) -> None:
    if conn.execute("PRAGMA user_version").fetchone()[0] >= _SCHEMA_VERSION:
        return
    for table, column, kind in _ADDED_COLUMNS:
        present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
            except sqlite3.OperationalError as e:
                # Another thread opening the database at the same moment got there first.
                if "duplicate column" not in str(e):
                    raise
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _is_latin(char) -> bool:
    code = ord(char)
    return code < 0x250 or 0x1E00 <= code <= 0x1EFF


def fold(text) -> str:
    """Case removed, and accents on Latin letters. Marks stay in other scripts,
    where they make a different word (ガラス and カラス)."""
    kept = []
    after_latin = False
    for char in unicodedata.normalize("NFKD", str(text or "")):
        if unicodedata.combining(char):
            if not after_latin:
                kept.append(char)
        else:
            kept.append(char)
            after_latin = _is_latin(char)
    return unicodedata.normalize("NFKC", "".join(kept)).casefold()


def _keeps_name_apart(char) -> bool:
    return char.isalnum() or char == "_" or unicodedata.category(char)[0] == "M" or unicodedata.category(char) == "So"


def _clean(text) -> str:
    """fold() without punctuation; falls back on the folded text, so a name
    made only of punctuation still has a usable, distinct form."""
    folded = fold(text)
    spaced = "".join(c if _keeps_name_apart(c) else " " for c in folded.replace("&", " and "))
    return " ".join(spaced.split()) or " ".join(folded.split())


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
    items = value if isinstance(value, (list, tuple)) else [value]
    # Maloja keeps some "A • B" credits as one artist, in lists too.
    parts = [part for item in items if item for credit in str(item).split(" • ") for part in _FEAT_SPLIT.split(credit)]
    return [part.strip() for part in parts if part.strip() not in ("", "•")]


def usable_genre(value) -> bool:
    """Tags hold junk too: bare ID3 numbers and placeholders."""
    text = str(value or "").strip()
    return bool(text) and not text.isdigit() and text.casefold() not in ("<unknown>", "unknown")


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


def album_key(album_artist, title) -> str:
    return f"{name_key(album_artist)}|{_clean(title)}"


def upsert_album(conn, title, album_artist):
    title = str(title or "").strip()
    if not title:
        return None
    album_artist = str(album_artist or "").strip()
    key = album_key(album_artist, title)
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


def with_account(data, account):
    """Points every cover in an answer at this account's history: its ids are
    its own, so the same address must never show another account's cover."""
    if isinstance(data, list):
        for item in data:
            with_account(item, account)
    elif isinstance(data, dict):
        for key, value in data.items():
            if key == "image" and isinstance(value, str) and value.startswith("/stats/cover/") and "a=" not in value:
                data[key] = f"{value}{'&' if '?' in value else '?'}a={quote(account)}"
            elif isinstance(value, (dict, list)):
                with_account(value, account)
    return data


def archive(account) -> str:
    """Moves the history of a removed account to backups/removed-accounts/, as
    one file, and returns its path; "" when it had none. The original goes only
    once the copy is complete."""
    path = db_path(account)
    if not path.exists():
        return ""
    folder = Path(config.DATA_DIR) / "backups" / "removed-accounts"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{account}-{time.strftime('%Y%m%d-%H%M%S')}.db"
    source = sqlite3.connect(path)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    for old in [path.with_name(path.name + suffix) for suffix in ("", "-wal", "-shm")] + list(path.parent.glob(f"{path.name}.bak-*")):
        try:
            old.unlink(missing_ok=True)
        except OSError as e:
            logger.error("Could not remove %s: %s", old, e)
    return str(target)
