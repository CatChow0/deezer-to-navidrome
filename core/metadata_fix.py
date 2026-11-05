"""Fix Missing Metadata: finds the tempo and genre a file lacks, and adds them to its
tags, so Navidrome sees them too and they never have to be found again.

A value already in a file is never replaced. A file is never written directly: the
tags go on a copy, which replaces the original only once its audio is proven the
same. Results are also kept in mixes.db, so a file that cannot be written (a
read-only mount) still counts for the mixes."""
import logging
import os
import shutil
import threading
import time
from pathlib import Path

from mutagen import File as MutagenFile

from core import audio_tempo, mixes_db, stats_db

logger = logging.getLogger(__name__)

PAUSE_SECONDS = 0.05    # Leaves room for the rest of the app on a small server.
COMMIT_EVERY = 25
LOOKUP_RETRY_DAYS = 30
TEMP_SUFFIX = ".d2ntmp"
WRITABLE = {".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".opus"}
DURATION_TOLERANCE = 0.2

_running = threading.Lock()


class WriteRefused(Exception):
    pass


def available() -> bool:
    try:
        audio_tempo._libraries()
        return True
    except (ImportError, OSError) as e:
        logger.warning("Tempo analysis is not available: %s", e)
        return False


# --- Tags ---------------------------------------------------------------------

def _first(values):
    if not values:
        return None
    value = values[0] if isinstance(values, (list, tuple)) else values
    return str(value).strip() or None


def read_tags(path) -> tuple:
    """(tempo, genre) a file already carries, each None when absent or unusable."""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return None, None
    if audio is None or audio.tags is None:
        return None, None
    genre = _first(audio.tags.get("genre"))
    try:
        bpm = float(_first(audio.tags.get("bpm")) or 0)
    except ValueError:
        bpm = 0
    return (bpm if bpm > 0 else None), (genre if stats_db.usable_genre(genre) else None)


def _same_audio(original, copy) -> bool:
    """FLAC stores a checksum of its audio. Other formats are compared on what is
    left once the tags are set aside: the same length and audio properties."""
    a, b = MutagenFile(original), MutagenFile(copy)
    if a is None or b is None or a.info is None or b.info is None:
        return False
    if abs(a.info.length - b.info.length) > DURATION_TOLERANCE:
        return False
    if hasattr(a.info, "md5_signature") and a.info.md5_signature != b.info.md5_signature:
        return False
    return getattr(a.info, "sample_rate", 0) == getattr(b.info, "sample_rate", 0)


def _kept_all_tags(original, copy, added) -> bool:
    before, after = MutagenFile(original, easy=True), MutagenFile(copy, easy=True)
    for key in (before.tags or {}).keys():
        if key not in added and list(before.tags[key]) != list(after.tags.get(key) or []):
            return False
    pictures = lambda f: len(getattr(MutagenFile(f), "pictures", []) or [])
    return pictures(original) == pictures(copy)


def write_tags(path, bpm=None, genre=None) -> bool:
    """Adds the values to the file's tags. True when written, False when the format
    takes no tags. Raises WriteRefused or OSError, and the original is left as it was."""
    path = Path(path)
    if path.suffix.lower() not in WRITABLE:
        return False
    added = {}
    if bpm:
        added["bpm"] = str(int(round(bpm)))
    if genre:
        added["genre"] = genre
    if not added:
        return False
    temp = path.with_name(path.name + TEMP_SUFFIX)
    try:
        shutil.copy2(path, temp)
        audio = MutagenFile(temp, easy=True)
        if audio is None:
            raise WriteRefused("Unknown audio format")
        if audio.tags is None:
            audio.add_tags()
        for key, value in added.items():
            audio[key] = value
        audio.save()
        if not _same_audio(path, temp):
            raise WriteRefused("The audio differed after writing the tags")
        if not _kept_all_tags(path, temp, added):
            raise WriteRefused("Other tags changed while writing")
        stat = path.stat()
        if hasattr(os, "chown"):
            try:
                os.chown(temp, stat.st_uid, stat.st_gid)
            except OSError:
                pass
        os.replace(temp, path)
        return True
    except (WriteRefused, OSError):
        raise
    except Exception as e:
        raise WriteRefused(str(e)) from e
    finally:
        temp.unlink(missing_ok=True)


# --- Genre from Deezer --------------------------------------------------------

def _api(path, params=None):
    from core.deezer import _public_api

    return _public_api(path, params)


def _close(a, b) -> bool:
    return bool(a and b) and (a == b or a in b or b in a)


def _album_genre(album_id, api) -> str:
    album = api(f"/album/{album_id}") or {}
    genres = (album.get("genres") or {}).get("data") or []
    return (genres[0].get("name") or "") if genres else ""


def _find_album_id(artist, title, album, api):
    """The Deezer album, only when its artist and title really are the ones asked:
    a wrong album would give a wrong genre for good."""
    from core.stats_enrich import deezer_match

    wanted = stats_db.name_key(artist)
    if album and stats_db.name_key(album) not in ("unknown album", "unknown"):
        found = api("/search/album", {"q": f'artist:"{artist}" album:"{album}"', "limit": 5}) or {}
        for item in found.get("data") or []:
            same_artist = _close(wanted, stats_db.name_key((item.get("artist") or {}).get("name")))
            if same_artist and _close(stats_db.title_key(album), stats_db.title_key(item.get("title"))):
                return item["id"]
    found = api("/search/track", {"q": f"{artist} {stats_db.clean_title(title)}", "limit": 10}) or {}
    for item in found.get("data") or []:
        if deezer_match(title, [artist], item) and (item.get("album") or {}).get("id"):
            return item["album"]["id"]
    return None


def lookup_genre(conn, artist, title, album, now, api=_api):
    """One search per album: its tracks share the answer. Not found is remembered for
    a while; a Deezer failure is not, so the next pass tries again."""
    names = stats_db.split_artists(artist)
    if not names or stats_db.name_key(names[0]) in ("unknown", "unknown artist", "various artists"):
        return None
    key = f"{stats_db.name_key(names[0])}|{stats_db.name_key(album) or stats_db.title_key(title)}"
    row = conn.execute("SELECT genre, checked_at FROM album_genres WHERE key=?", (key,)).fetchone()
    if row and (row["genre"] or now - row["checked_at"] < LOOKUP_RETRY_DAYS * 86400):
        return row["genre"] or None
    try:
        album_id = _find_album_id(names[0], title, album, api)
        genre = _album_genre(album_id, api) if album_id else ""
    except Exception as e:
        logger.info("No genre for %s: %s", key, e)
        return None
    conn.execute("INSERT OR REPLACE INTO album_genres(key, genre, checked_at) VALUES (?,?,?)", (key, genre, int(now)))
    return genre or None


# --- The pass -----------------------------------------------------------------

def _mtime(path):
    try:
        return Path(path).stat().st_mtime_ns
    except OSError:
        return None


def pending(conn, entries, now=None) -> list:
    """Files never seen or changed since, and those without a genre whose lookup is
    old enough to try again. A file this app just tagged differs from the index until
    its next refresh: the file itself says whether it really changed."""
    now = now or time.time()
    known = {r["path"]: r for r in conn.execute("SELECT path, mtime_ns, genre, analyzed_at FROM track_features")}
    result = []
    for entry in entries:
        path = entry.get("path")
        if not path:
            continue
        row = known.get(path)
        if row is None:
            result.append(entry)
        elif row["mtime_ns"] != entry.get("mtime_ns", 0) and _mtime(path) != row["mtime_ns"]:
            result.append(entry)
        elif not row["genre"] and now - row["analyzed_at"] > LOOKUP_RETRY_DAYS * 86400:
            result.append(entry)
    return result


def fix_file(conn, entry, now, api=_api, write=write_tags) -> dict:
    """Never measures a tempo the file carries, so a lost database costs little."""
    path = entry["path"]
    tag_bpm, tag_genre = read_tags(path)
    row = conn.execute("SELECT bpm, mtime_ns FROM track_features WHERE path=?", (path,)).fetchone()
    unchanged = row is not None and row["mtime_ns"] == _mtime(path)
    bpm = tag_bpm or (row["bpm"] if unchanged and row["bpm"] else None) or audio_tempo.file_tempo(path)
    artist = entry.get("tag_artist") or entry.get("parsed_artist") or ""
    title = entry.get("tag_title") or entry.get("parsed_title") or entry.get("parsed_track_title") or ""
    genre = tag_genre or lookup_genre(conn, artist, title, entry.get("tag_album") or "", now, api)
    error = ""
    written = False
    new_bpm, new_genre = (bpm if not tag_bpm else None), (genre if not tag_genre else None)
    if new_bpm or new_genre:
        try:
            written = write(path, new_bpm, new_genre)
        except (WriteRefused, OSError) as e:
            error = str(e)[:200]
            logger.info("Could not tag %s: %s", path, e)
    conn.execute(
        "INSERT OR REPLACE INTO track_features(path, mtime_ns, bpm, genre, analyzed_at, write_error) VALUES (?,?,?,?,?,?)",
        (path, _mtime(path) or entry.get("mtime_ns", 0), bpm, genre, int(now), error),
    )
    return {"written": written, "error": error, "bpm": bpm, "genre": genre}


def run(conn, entries, progress=None, should_stop=None, pause=0, api=_api, write=write_tags) -> dict:
    report = {"done": 0, "written": 0, "errors": 0}
    total = len(entries)
    for entry in entries:
        if should_stop and should_stop():
            break
        result = fix_file(conn, entry, time.time(), api, write)
        report["done"] += 1
        report["written"] += 1 if result["written"] else 0
        report["errors"] += 1 if result["error"] else 0
        if report["done"] % COMMIT_EVERY == 0:
            conn.commit()
            if progress:
                progress(report["done"], total)
        if pause:
            time.sleep(pause)
    conn.commit()
    return report


def features_map(conn) -> dict:
    """path -> (bpm, genre)"""
    return {r["path"]: (r["bpm"], r["genre"]) for r in conn.execute("SELECT path, bpm, genre FROM track_features")}


def move_file(conn, old, new) -> None:
    """A file that moves keeps what is known about it, so it is not measured again."""
    conn.execute("UPDATE OR REPLACE track_features SET path=? WHERE path=?", (str(new), str(old)))
    conn.commit()


def status(conn, entries) -> dict:
    return {
        "total": len(entries),
        "left": len(pending(conn, entries)),
        "write_errors": conn.execute("SELECT COUNT(*) FROM track_features WHERE write_error != ''").fetchone()[0],
    }


def is_running() -> bool:
    return _running.locked()


def _refresh_library() -> None:
    from core.library import refresh_library_cache_incremental_with_progress

    refresh_library_cache_incremental_with_progress(progress_cb=lambda **kw: None)


def start_background(load_entries, task_id=None) -> bool:
    """One pass at a time. Survives a restart: what was done stays done."""
    if not _running.acquire(blocking=False):
        return False

    def runner():
        from core.config import push_task_event

        def say(message, **kw):
            if task_id:
                push_task_event(task_id, message, **kw)

        conn = mixes_db.connect()
        try:
            if not available():
                say("Tempo analysis is not available in this install.", stage="error", done=True, error=True)
                return
            todo = pending(conn, load_entries())
            report = run(conn, todo, pause=PAUSE_SECONDS,
                         progress=lambda done, total: say(f"{done}/{total} files", stage="fix", progress=round(done * 100 / total)))
            if report["written"]:
                _refresh_library()
            summary = f"{report['done']} files checked, {report['written']} tagged"
            if report["errors"]:
                summary += f", {report['errors']} could not be written (is the folder mounted read-only?)"
            say(summary, stage="done", progress=100, done=True)
        except Exception as e:
            logger.error("Fix Missing Metadata stopped: %s", e)
            say(f"Stopped: {e}", stage="error", done=True, error=True)
        finally:
            conn.close()
            _running.release()

    threading.Thread(target=runner, daemon=True, name="metadata-fix").start()
    return True
