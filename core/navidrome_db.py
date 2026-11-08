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
