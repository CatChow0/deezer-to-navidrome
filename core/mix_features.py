"""Tempo and genre of the files in the library, measured once and kept in mixes.db.
Files are only read: nothing is ever written to a tag."""
import logging
import threading
import time
from pathlib import Path

from mutagen import File as MutagenFile

from core import audio_tempo, mixes_db

logger = logging.getLogger(__name__)

PAUSE_SECONDS = 0.05    # Leaves room for the rest of the app on a small server.
COMMIT_EVERY = 25

_running = threading.Lock()


def available() -> bool:
    try:
        audio_tempo._libraries()
        return True
    except (ImportError, OSError) as e:
        logger.warning("Tempo analysis is not available: %s", e)
        return False


def read_genre(path):
    try:
        audio = MutagenFile(path, easy=True)
        values = (audio.tags or {}).get("genre") if audio is not None else None
        return str(values[0]).strip() or None if values else None
    except Exception:
        return None


def pending(conn, entries) -> list:
    known = {r["path"]: r["mtime_ns"] for r in conn.execute("SELECT path, mtime_ns FROM track_features")}
    return [e for e in entries if e.get("path") and known.get(e["path"], -1) != e.get("mtime_ns", 0)]


def analyze(conn, entries, should_stop=None, pause=0) -> int:
    done = 0
    for entry in entries:
        if should_stop and should_stop():
            break
        path = entry["path"]
        conn.execute(
            "INSERT OR REPLACE INTO track_features(path, mtime_ns, bpm, genre, analyzed_at) VALUES (?,?,?,?,?)",
            (path, entry.get("mtime_ns", 0), audio_tempo.file_tempo(path), read_genre(path), int(time.time())),
        )
        done += 1
        if done % COMMIT_EVERY == 0:
            conn.commit()
        if pause:
            time.sleep(pause)
    conn.commit()
    return done


def features_map(conn) -> dict:
    """path -> (bpm, genre)"""
    return {r["path"]: (r["bpm"], r["genre"]) for r in conn.execute("SELECT path, bpm, genre FROM track_features")}


def status(conn, entries) -> dict:
    return {"total": len(entries), "left": len(pending(conn, entries))}


def start_background(load_entries) -> bool:
    """Measures what is new, one file at a time. Survives a restart: what was
    measured stays, and the next start goes on from there."""
    if not _running.acquire(blocking=False):
        return False

    def runner():
        conn = mixes_db.connect()
        try:
            if available():
                analyze(conn, pending(conn, load_entries()), pause=PAUSE_SECONDS)
        except Exception as e:
            logger.error("Tempo analysis stopped: %s", e)
        finally:
            conn.close()
            _running.release()

    threading.Thread(target=runner, daemon=True, name="tempo-analysis").start()
    return True


def is_running() -> bool:
    return _running.locked()
