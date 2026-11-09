"""Read-only look at Navidrome's own database, when it is mounted (the same file
the history import reads, see core/stats_import.py). Always on a copy, so the
live file is never locked or touched.

Used to tie a Navidrome account to its user: its internal ID is what the plays
(scrobbles.user_id) and the stars (annotation.user_id) carry."""
import tempfile
import threading
import time
from pathlib import Path

from core import config

USERS_FOR = 600  # seconds a read of the users stays good
_cache = {}
_lock = threading.Lock()


def _source() -> Path:
    from core import stats_import

    return stats_import._navidrome_path()


def mounted() -> bool:
    return _source().is_file()


def users(now=None):
    """[{id, user_name, name, is_admin}], or None when the database is not mounted
    or cannot be read."""
    from core import stats_import

    source = _source()
    if not source.is_file():
        return None
    now = time.time() if now is None else now
    with _lock:
        read_at, found = _cache.get(str(source), (None, None))
        if read_at is not None and now - read_at < USERS_FOR:
            return [dict(u) for u in found]
    try:
        with tempfile.TemporaryDirectory(dir=config.DATA_DIR) as folder:
            conn = stats_import._open_copy(source, Path(folder), "navidrome.db",
                                           {"user": {"id", "user_name", "is_admin"}}, "Navidrome")
            try:
                found = [{"id": r["id"], "user_name": r["user_name"], "name": r["name"] if "name" in r.keys() else "",
                          "is_admin": bool(r["is_admin"])}
                         for r in conn.execute("SELECT * FROM user ORDER BY user_name")]
            finally:
                conn.close()
    except stats_import.ImportRefused:
        return None
    with _lock:
        _cache[str(source)] = (now, found)
    return [dict(u) for u in found]


def find_user(username):
    """The Navidrome user with this name (case-insensitive, as Navidrome compares
    them), or None."""
    wanted = (username or "").strip().lower()
    for user in users() or []:
        if user["user_name"].lower() == wanted:
            return user
    return None


def forget() -> None:
    with _lock:
        _cache.clear()


# --- Songs, for publishing playlists -------------------------------------------

SONGS_FOR = 300     # seconds a read of the songs stays good
MISS_REFRESH = 60   # a song not found is looked for again in a fresh read after this
_songs = {}


def norm_path(path) -> str:
    import os

    return os.path.normcase(os.path.normpath(str(path)))


def _read_songs(source):
    from core import stats_files, stats_import

    _, _, _, mappings = config.get_paths_from_config()
    with tempfile.TemporaryDirectory(dir=config.DATA_DIR) as folder:
        conn = stats_import._open_copy(source, Path(folder), "navidrome.db", {"media_file": {"id", "path"}}, "Navidrome")
        try:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(media_file)")}
            library = {r[1] for r in conn.execute("PRAGMA table_info(library)")}
            present = "WHERE f.missing = 0" if "missing" in columns else ""
            if {"path", "library_id"} <= columns and {"id", "path"} <= library:
                rows = conn.execute("SELECT f.id, f.path, f.library_id, l.path AS root FROM media_file f"
                                    f" JOIN library l ON l.id = f.library_id {present}").fetchall()
            else:
                rows = conn.execute(f"SELECT f.id, f.path, NULL AS library_id, '/' AS root FROM media_file f {present}").fetchall()
            index = {}
            for row in rows:
                relative = row["path"].lstrip("/") if row["root"] == "/" else row["path"]
                path = stats_files.container_path(row["root"], relative, mappings)
                if path:
                    index[norm_path(path)] = (row["id"], row["library_id"])
            rights = None
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_library'").fetchone():
                rights = {}
                for row in conn.execute("SELECT user_id, library_id FROM user_library"):
                    rights.setdefault(row["user_id"], set()).add(row["library_id"])
            return index, rights
        finally:
            conn.close()


def songs(now=None, fresh_after=SONGS_FOR):
    """(index, rights): the path of each song as this container sees it ->
    (Navidrome song ID, library ID), and Navidrome user ID -> libraries it may
    see (None when this Navidrome has no per-library rights). (None, None) when
    the database is not mounted."""
    from core import stats_import

    source = _source()
    if not source.is_file():
        return None, None
    now = time.time() if now is None else now
    with _lock:
        read_at, index, rights = _songs.get(str(source), (None, None, None))
        if read_at is not None and now - read_at < fresh_after:
            return index, rights
    try:
        index, rights = _read_songs(source)
    except stats_import.ImportRefused:
        return None, None
    with _lock:
        _songs[str(source)] = (now, index, rights)
    return index, rights


def songs_read_at():
    with _lock:
        read_at, _, _ = _songs.get(str(_source()), (None, None, None))
    return read_at


def file_playlists(navidrome_folder):
    """Playlists Navidrome imported from files in this folder (its own path for
    it): [{id, name, path, owner}], or None when the database is not mounted."""
    from core import stats_import

    source = _source()
    if not source.is_file():
        return None
    root = str(navidrome_folder).rstrip("/") + "/"
    with tempfile.TemporaryDirectory(dir=config.DATA_DIR) as folder:
        conn = stats_import._open_copy(source, Path(folder), "navidrome.db",
                                       {"playlist": {"id", "name", "path", "owner_id"}}, "Navidrome")
        try:
            users = {r["id"]: r["user_name"] for r in conn.execute("SELECT id, user_name FROM user")}
            return [{"id": r["id"], "name": r["name"], "path": r["path"], "owner_id": r["owner_id"],
                     "owner": users.get(r["owner_id"], "")}
                    for r in conn.execute("SELECT id, name, path, owner_id FROM playlist WHERE path != '' ORDER BY name")
                    if str(r["path"]).replace("\\", "/").startswith(root)]
        finally:
            conn.close()


def forget_songs() -> None:
    with _lock:
        _songs.clear()
