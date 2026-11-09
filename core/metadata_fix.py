"""Fix Missing Metadata: finds the tempo and genre a file lacks, and adds them to its
tags, so Navidrome sees them too and they never have to be found again.

A value already in a file is never replaced. A FLAC with room in its header only has
that header rewritten, in place, after saving it to a journal: its audio is neither
read nor written. Anything else goes on a copy, whose audio must match the original's
before it takes its place. mixes.db keeps every result as well, which is what counts
for a file that cannot take tags (a read-only mount, a format without tags), and it
remembers what was added so it can be taken back.

After a brutal stop a file is either as it was, or complete: recover() puts a saved
header back and clears what the journal names.

Searching Deezer is limited by its request rate, not by this machine, so a file waiting
for a genre steps aside instead of holding a thread: the total time is the longer of
the two jobs instead of their sum."""
import hashlib
import json
import logging
import os
import queue
import shutil
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC

from core import audio_tempo, config, mixes_db, stats_db
from core.utils import FILES_LOCK

logger = logging.getLogger(__name__)

DEFAULT_WORKERS = 4
DAY = 86400
LOOKUP_THREADS = 6      # Enough to use Deezer's whole rate, which _public_api keeps to.
HEADER_COMPARE = 64 * 1024
LOOKUP_RETRY_DAYS = 30
TEMP_SUFFIX = ".d2ntmp"
BYTE_COMPARED = {".flac", ".mp3"}       # Their audio can be compared byte for byte.
DECODE_COMPARED = {".ogg", ".opus"}     # Rewritten pages: compared once decoded.
WRITABLE = BYTE_COMPARED | DECODE_COMPARED
WRITTEN, IN_FILE, UNSUPPORTED, FAILED, OFF = "written", "in_file", "unsupported", "failed", "off"
CHUNK = 1024 * 1024

_running = threading.Lock()
_album_locks = {}
_album_locks_guard = threading.Lock()
_current_task = None
PROGRESS_EVERY_FILES = 25
PROGRESS_EVERY_SECONDS = 5


class WriteRefused(Exception):
    pass


class FileChanged(WriteRefused):
    """Something else changed or moved the file during the write."""


class NoRoom(Exception):
    """The new tags do not fit in the free space of the header."""


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


def _id3_size(handle) -> int:
    """Bytes taken by an ID3v2 tag at the start of a file."""
    handle.seek(0)
    head = handle.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return 0
    size = (head[6] & 127) << 21 | (head[7] & 127) << 14 | (head[8] & 127) << 7 | (head[9] & 127)
    return size + (20 if head[5] & 0x10 else 10)


def _flac_audio_start(handle) -> int:
    start = _id3_size(handle)
    handle.seek(start)
    if handle.read(4) != b"fLaC":
        raise WriteRefused("Not a FLAC file")
    while True:
        header = handle.read(4)
        if len(header) < 4:
            raise WriteRefused("Damaged FLAC metadata")
        handle.seek(int.from_bytes(header[1:4], "big"), 1)
        if header[0] & 0x80:
            return handle.tell()


def _hash_range(handle, start, end) -> str:
    digest = hashlib.md5()
    handle.seek(start)
    left = end - start
    while left > 0:
        chunk = handle.read(min(CHUNK, left))
        if not chunk:
            break
        digest.update(chunk)
        left -= len(chunk)
    return digest.hexdigest()


def _audio_range(handle, suffix) -> tuple:
    """Where the audio bytes are, tags set aside."""
    size = handle.seek(0, 2)
    if suffix == "flac":
        return _flac_audio_start(handle), size
    start = _id3_size(handle)
    handle.seek(max(0, size - 128))
    # An ID3v1 tag at the very end is a tag too, not audio.
    end = size - 128 if size >= 128 and handle.read(3) == b"TAG" else size
    return start, end


def _suffix(path) -> str:
    return Path(path).name.removesuffix(TEMP_SUFFIX).rsplit(".", 1)[-1].lower()


def audio_fingerprint(path) -> str:
    """Identifies a file's audio whatever its tags say. FLAC's own checksum would not
    do: it sits in the header and is merely copied, so it stays the same even if the
    audio is damaged. These are the actual bytes."""
    path = Path(path)
    suffix = _suffix(path)
    if f".{suffix}" in DECODE_COMPARED:
        np, soundfile = audio_tempo._libraries()
        samples, _ = soundfile.read(str(path), dtype="float32")
        return hashlib.md5(np.asarray(samples).tobytes()).hexdigest()
    if f".{suffix}" not in BYTE_COMPARED:
        raise WriteRefused(f"Cannot compare the audio of a {suffix} file")
    with open(path, "rb") as handle:
        start, end = _audio_range(handle, suffix)
        return _hash_range(handle, start, end)


def _same_audio(original, copy) -> bool:
    """Byte for byte, with no hash to compute. Formats rewritten when tagged are
    compared once decoded."""
    suffix = _suffix(original)
    if f".{suffix}" in DECODE_COMPARED:
        return audio_fingerprint(original) == audio_fingerprint(copy)
    with open(original, "rb") as a, open(copy, "rb") as b:
        start_a, end_a = _audio_range(a, suffix)
        start_b, end_b = _audio_range(b, suffix)
        if end_a - start_a != end_b - start_b:
            return False
        a.seek(start_a)
        b.seek(start_b)
        left = end_a - start_a
        while left > 0:
            chunk = a.read(min(CHUNK, left))
            if not chunk or chunk != b.read(len(chunk)):
                return False
            left -= len(chunk)
    return True


def _kept_all_tags(original, copy, changed) -> bool:
    before, after = MutagenFile(original, easy=True), MutagenFile(copy, easy=True)
    for key in (before.tags or {}).keys():
        if key not in changed and list(before.tags[key]) != list(after.tags.get(key) or []):
            return False
    pictures = lambda f: len(getattr(MutagenFile(f), "pictures", []) or [])
    return pictures(original) == pictures(copy)


def _sync(path) -> None:
    """To the disk, not just the system's cache: a power cut must not leave a file
    that was renamed but never written."""
    handle = os.open(path, os.O_RDONLY)
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def _sync_folder(folder) -> None:
    try:
        _sync(folder)
    except OSError:
        pass    # Folders cannot be opened this way everywhere; the file itself is safe.


def _signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _journal(conn, temp, path) -> None:
    if conn is not None:
        conn.execute("INSERT OR REPLACE INTO write_journal(temp, path, started_at) VALUES (?,?,?)",
                     (str(temp), str(path), int(time.time())))
        conn.commit()


def _journal_done(conn, temp) -> None:
    if conn is not None:
        conn.execute("DELETE FROM write_journal WHERE temp=?", (str(temp),))
        conn.commit()


def _journal_dir() -> Path:
    return Path(config.DATA_DIR) / "metadata_journal"


def _save_header(path, size, header) -> Path:
    """A header about to be rewritten, on the disk before anything happens to the file.
    It says itself which file it belongs to: it must not depend on another write."""
    folder = _journal_dir()
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.md5(str(path).encode()).hexdigest()
    partial, backup = folder / f"{name}.part", folder / f"{name}.hdr"
    with open(partial, "wb") as handle:
        handle.write(json.dumps({"path": str(path), "size": size}).encode() + b"\n")
        handle.write(header)
        handle.flush()
        os.fsync(handle.fileno())
    # A stop can come at any time, here too: a .hdr is only ever a complete one.
    os.replace(partial, backup)
    _sync_folder(folder)
    return backup


def _restore_header(path, header) -> None:
    with open(path, "r+b") as handle:
        handle.write(header)
        handle.flush()
        os.fsync(handle.fileno())


def recover(conn) -> int:
    """After a brutal stop: puts back the headers being rewritten, and clears the
    temporary copies the journal names. Nothing else is ever touched. Returns how many
    were dealt with."""
    cleared = 0
    for row in conn.execute("SELECT temp FROM write_journal").fetchall():
        temp = Path(row["temp"])
        if temp.name.endswith(TEMP_SUFFIX):
            try:
                if temp.exists():
                    temp.unlink()
                    cleared += 1
            except OSError as e:
                logger.warning("Could not clear %s: %s", temp, e)
                continue
        conn.execute("DELETE FROM write_journal WHERE temp=?", (row["temp"],))
    conn.commit()
    folder = _journal_dir()
    if folder.is_dir():
        # Stopped while saving a header: the file itself had not been touched yet.
        for partial in folder.glob("*.part"):
            partial.unlink(missing_ok=True)
        for backup in folder.glob("*.hdr"):
            try:
                with open(backup, "rb") as handle:
                    info = json.loads(handle.readline())
                    header = handle.read()
                path = Path(info["path"])
                # Another size: the file was replaced since. It is not ours to change.
                if path.exists() and path.stat().st_size == info["size"] and len(header) <= info["size"]:
                    _restore_header(path, header)
                    cleared += 1
                backup.unlink()
            except (OSError, ValueError, KeyError) as e:
                logger.warning("Could not restore from %s: %s", backup, e)
    return cleared


def _pictures(audio) -> list:
    return [hashlib.md5(p.data).hexdigest() for p in audio.pictures]


def _in_place_flac(path, change, keys) -> None:
    """Rewrites only the metadata, in the room the header already has, so the audio is
    neither moved nor read. Raises NoRoom, with the file untouched, when it does not fit."""
    path = Path(path)
    before = _signature(path)
    with open(path, "rb") as handle:
        start = _flac_audio_start(handle)
        handle.seek(start)
        first_audio = handle.read(HEADER_COMPARE)
        handle.seek(0)
        header = handle.read(start)
    audio = FLAC(path)
    tags = {key: list(audio[key]) for key in audio.keys()} if audio.tags else {}
    pictures = _pictures(audio)
    change(audio)

    def exact_fit(info):
        if info.padding < 0:
            raise NoRoom()
        return info.padding

    backup = _save_header(path, before[0], header)
    try:
        with FILES_LOCK:
            try:
                unchanged = _signature(path) == before
            except OSError:
                unchanged = False
            if not unchanged:
                raise FileChanged("The file changed during the write")
            audio.save(padding=exact_fit)
        _sync(path)
        try:
            with open(path, "rb") as handle:
                good = _flac_audio_start(handle) == start and handle.seek(0, 2) == before[0]
                handle.seek(start)
                good = good and handle.read(HEADER_COMPARE) == first_audio
            after = FLAC(path)
            good = good and all(list(after.get(k) or []) == v for k, v in tags.items() if k not in keys)
            good = good and _pictures(after) == pictures
        except WriteRefused:
            raise
        except Exception:
            good = False
        if not good:
            _restore_header(path, header)
            raise WriteRefused("The file differed after writing the tags")
    finally:
        backup.unlink(missing_ok=True)


def _rewrite(path, change, keys, conn=None) -> None:
    """Applies `change(audio)` on a copy, proves the audio and other tags are intact,
    and only then swaps it in, unless the file changed in the meantime."""
    path = Path(path)
    temp = path.with_name(path.name + TEMP_SUFFIX)
    _journal(conn, temp, path)
    try:
        before = _signature(path)
        shutil.copy2(path, temp)
        audio = MutagenFile(temp, easy=True)
        if audio is None:
            raise WriteRefused("Unknown audio format")
        change(audio)
        audio.save()
        if not _same_audio(path, temp):
            raise WriteRefused("The audio differed after writing the tags")
        if not _kept_all_tags(path, temp, keys):
            raise WriteRefused("Other tags changed while writing")
        _sync(temp)
        with FILES_LOCK:
            try:
                unchanged = _signature(path) == before
            except OSError:
                unchanged = False
            if not unchanged:
                raise FileChanged("The file changed during the write")
            stat = path.stat()
            if hasattr(os, "chown"):
                try:
                    os.chown(temp, stat.st_uid, stat.st_gid)
                except OSError:
                    pass
            os.replace(temp, path)
        _sync_folder(path.parent)
    except (WriteRefused, OSError):
        raise
    except Exception as e:
        raise WriteRefused(str(e)) from e
    finally:
        try:
            temp.unlink(missing_ok=True)
        finally:
            _journal_done(conn, temp)


def _apply(path, change, keys, conn) -> None:
    if Path(path).suffix.lower() == ".flac":
        try:
            _in_place_flac(path, change, keys)
            return
        except NoRoom:
            pass    # No room in its header: on a copy, then.
        except (WriteRefused, OSError):
            raise
        except Exception as e:
            raise WriteRefused(str(e)) from e
    _rewrite(path, change, keys, conn)


def write_tags(path, bpm=None, genre=None, conn=None) -> bool:
    """Adds the values to the file's tags. True when written, False when the format
    is not one this app can verify. Raises WriteRefused or OSError, and the original
    is left as it was."""
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

    def change(audio):
        if audio.tags is None:
            audio.add_tags()
        for key, value in added.items():
            audio[key] = value

    _apply(path, change, added, conn)
    return True


def remove_tags(path, keys, conn=None) -> None:
    def change(audio):
        for key in keys:
            if key in audio:
                del audio[key]

    _apply(path, change, keys, conn)


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


_genre_names = {}


def _genre_name(genre_id, api):
    """A genre's name from Deezer's list, asked once. None when the list has no answer."""
    if not _genre_names:
        for item in (api("/genre") or {}).get("data") or []:
            if item.get("id") and item.get("name"):
                _genre_names[item["id"]] = item["name"]
    return _genre_names.get(genre_id)


def _genre_from(found, api) -> str:
    """Deezer's request limit is what slows this pass down, so each call counts. An
    album found by search already says its genre: compared on 75 real albums, it is
    always the one its own page gives first. -1 means the album has none."""
    genre_id = found.get("genre_id")
    if genre_id == -1:
        return ""
    if genre_id is not None:
        name = _genre_name(genre_id, api)
        if name:
            return name
    return _album_genre(found["id"], api)


def _find_album(artist, title, album, api):
    """The Deezer album, only when its artist and title really are the ones asked:
    a wrong album would give a wrong genre for good."""
    from core.stats_enrich import deezer_match

    wanted = stats_db.name_key(artist)
    if album and stats_db.name_key(album) not in ("unknown album", "unknown"):
        found = api("/search/album", {"q": f'artist:"{artist}" album:"{album}"', "limit": 5}) or {}
        for item in found.get("data") or []:
            same_artist = _close(wanted, stats_db.name_key((item.get("artist") or {}).get("name")))
            if same_artist and _close(stats_db.title_key(album), stats_db.title_key(item.get("title"))):
                return item
    found = api("/search/track", {"q": f"{artist} {stats_db.clean_title(title)}", "limit": 10}) or {}
    for item in found.get("data") or []:
        if deezer_match(title, [artist], item) and (item.get("album") or {}).get("id"):
            return item["album"]
    return None


def _album_key(artist, title, album):
    names = stats_db.split_artists(artist)
    if not names or stats_db.name_key(names[0]) in ("unknown", "unknown artist", "various artists"):
        return None
    return f"{stats_db.name_key(names[0])}|{stats_db.name_key(album) or stats_db.title_key(title)}"


def _known_album(conn, key, now):
    row = conn.execute("SELECT genre, checked_at FROM album_genres WHERE key=?", (key,)).fetchone()
    return row if row and (row["genre"] or now - row["checked_at"] < LOOKUP_RETRY_DAYS * DAY) else None


def _genre_from_history(artist, title):
    """What a listening history already learned about this track, whoever
    played it (the library is shared): no call needed."""
    key = stats_db.track_key(stats_db.split_artists(artist), title)
    for account in stats_db.accounts_with_history():
        try:
            stats = stats_db.connect(account)
            try:
                row = stats.execute("SELECT genre FROM tracks WHERE key=? AND genre IS NOT NULL", (key,)).fetchone()
            finally:
                stats.close()
        except sqlite3.Error:
            continue
        if row and stats_db.usable_genre(row[0]):
            return row[0]
    return None


def lookup_genre(conn, artist, title, album, now, api=_api):
    """One search per album: its tracks share the answer. Not found is remembered for
    a while; a Deezer failure is not, so the next pass tries again."""
    key = _album_key(artist, title, album)
    if key is None:
        return None
    row = _known_album(conn, key, now)
    if row:
        return row["genre"] or None
    # Per album: two threads on tracks of one album must not both search, while
    # different albums search side by side. _public_api keeps to Deezer's limit.
    with _album_locks_guard:
        album_lock = _album_locks.setdefault(key, threading.Lock())
    with album_lock:
        row = _known_album(conn, key, now)
        if row:
            return row["genre"] or None
        genre = _genre_from_history(artist, title)
        if genre is None:
            try:
                names = stats_db.split_artists(artist)
                found = _find_album(names[0], title, album, api)
                genre = _genre_from(found, api) if found else ""
            except Exception as e:
                logger.info("No genre for %s: %s", key, e)
                return None
        conn.execute("INSERT OR REPLACE INTO album_genres(key, genre, checked_at) VALUES (?,?,?)", (key, genre, int(now)))
        conn.commit()
    return genre or None


# --- The pass -----------------------------------------------------------------

def _mtime(path):
    try:
        return Path(path).stat().st_mtime_ns
    except OSError:
        return None


def paused(conn) -> bool:
    """Cancelled by hand: no automatic pass until it is asked for again."""
    return bool(mixes_db.get_meta(conn, "metadata_fix_paused"))


def writing_off(conn) -> bool:
    return bool(mixes_db.get_meta(conn, "metadata_write_off"))


def pending(conn, entries, now=None) -> list:
    """Files never seen or changed since, those without a genre whose lookup is old
    enough to try again, and those a write failed on, once a day. A file this app just
    tagged differs from the index until its next refresh: the file itself says whether
    it really changed."""
    now = now or time.time()
    retry_writes = not writing_off(conn)
    known = {r["path"]: r for r in conn.execute(
        "SELECT path, mtime_ns, genre, analyzed_at, write_state, write_tried_at FROM track_features")}
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
        elif not row["genre"] and now - row["analyzed_at"] > LOOKUP_RETRY_DAYS * DAY:
            result.append(entry)
        elif retry_writes and row["write_state"] == FAILED and now - row["write_tried_at"] >= DAY:
            result.append(entry)
    return result


_NOT_SEARCHED = object()


class _Timing:
    """Thread time per step: says what limits a pass on this machine."""

    def __init__(self):
        self.seconds = {}
        self.lock = threading.Lock()

    def add(self, name, started):
        spent = time.perf_counter() - started
        with self.lock:
            self.seconds[name] = self.seconds.get(name, 0) + spent

    def summary(self):
        return ", ".join(f"{name} {round(value)}s" for name, value in
                         sorted(self.seconds.items(), key=lambda item: -item[1]))


def needed_album(conn, entry, now):
    """The album whose genre this file is waiting for, or None when it can go ahead."""
    path = entry["path"]
    if read_tags(path)[1]:
        return None
    row = conn.execute("SELECT genre, mtime_ns FROM track_features WHERE path=?", (path,)).fetchone()
    if row is not None and row["genre"] and row["mtime_ns"] == _mtime(path):
        return None
    key = _album_key(*_names(entry))
    if key is None or _known_album(conn, key, now):
        return None
    return key


def _names(entry) -> tuple:
    artist = entry.get("tag_artist") or entry.get("parsed_artist") or ""
    title = entry.get("tag_title") or entry.get("parsed_title") or entry.get("parsed_track_title") or ""
    return artist, title, entry.get("tag_album") or ""


def fix_file(conn, entry, now, api=_api, write=write_tags, write_off=False, searched=_NOT_SEARCHED, timing=None) -> dict:
    """Never measures a tempo the file carries or the base knows, so neither a retry
    nor a lost database costs another analysis of a tagged file."""
    path = entry["path"]
    tag_bpm, tag_genre = read_tags(path)
    row = conn.execute("SELECT * FROM track_features WHERE path=?", (path,)).fetchone()
    mtime_before = _mtime(path)
    unchanged = row is not None and row["mtime_ns"] == mtime_before
    started = time.perf_counter()
    bpm = tag_bpm or (row["bpm"] if unchanged and row["bpm"] else None) or audio_tempo.file_tempo(path)
    if timing:
        timing.add("tempo", started)
    artist, title, album = _names(entry)
    genre = tag_genre or (row["genre"] if unchanged and row["genre"] else None)
    if genre is None:
        # The answer is already there when the file was set aside for it.
        genre = lookup_genre(conn, artist, title, album, now, api) if searched is _NOT_SEARCHED else searched

    original = row["original_mtime"] if row is not None and row["original_mtime"] else None
    if original is None:
        try:
            original = Path(path).stat().st_mtime
        except OSError:
            original = None
    added_bpm = row["added_bpm"] if row is not None else None
    added_genre = row["added_genre"] if row is not None else None

    new_bpm, new_genre = (bpm if not tag_bpm else None), (genre if not tag_genre else None)
    state, error = IN_FILE, ""
    if new_bpm or new_genre:
        if write_off:
            state = OFF
        else:
            started = time.perf_counter()
            try:
                state = WRITTEN if write(path, new_bpm, new_genre, conn=conn) else UNSUPPORTED
                if state == WRITTEN:
                    added_bpm = str(int(round(new_bpm))) if new_bpm else added_bpm
                    added_genre = new_genre or added_genre
            except (WriteRefused, OSError) as e:
                state, error = FAILED, str(e)[:200]
                logger.info("Could not tag %s: %s", path, e)
            if timing:
                timing.add("tags", started)
    mtime_after = _mtime(path)
    if mtime_after is None:
        return {"written": False, "error": error or "The file is gone", "state": FAILED, "bpm": bpm, "genre": genre}
    conn.execute(
        "INSERT OR REPLACE INTO track_features(path, mtime_ns, bpm, genre, analyzed_at, write_error, write_state,"
        " write_tried_at, original_mtime, added_bpm, added_genre) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (path, mtime_after, bpm, genre, int(now), error, state, int(now), original, added_bpm, added_genre),
    )
    # Each file on its own: a measure is expensive, and a brutal stop must not lose it.
    conn.commit()
    return {"written": state == WRITTEN, "error": error, "state": state, "bpm": bpm, "genre": genre}


def workers_setting() -> int:
    from core.config import load_config

    try:
        return max(1, int(load_config().get("metadata_workers", DEFAULT_WORKERS)))
    except (TypeError, ValueError):
        return DEFAULT_WORKERS


def run(conn, entries, progress=None, should_stop=None, api=_api, write=write_tags, workers=1) -> dict:
    """Files are independent, so several are handled at once, each by one thread with
    its own database connection. A file waiting for a genre steps aside: threads of
    its own search for it, and the workers go on with the next file meanwhile."""
    report = {"done": 0, "written": 0, "errors": 0}
    total = len(entries)
    write_off = writing_off(conn)
    timing = _Timing()
    ready = deque((entry, _NOT_SEARCHED) for entry in entries)
    parked = {}             # album -> files waiting for its genre
    searches = queue.Queue()
    closing = threading.Event()
    searchers = []
    cond = threading.Condition()
    busy = [0]
    last_report = [time.monotonic()]

    def stopped():
        return bool(should_stop and should_stop())

    def search_body():
        search_conn = mixes_db.connect()
        try:
            while not closing.is_set():
                try:
                    key, entry = searches.get(timeout=0.2)
                except queue.Empty:
                    continue
                if stopped():
                    continue
                started = time.perf_counter()
                try:
                    genre = lookup_genre(search_conn, *_names(entry), time.time(), api)
                except Exception as e:
                    logger.info("No genre for %s: %s", key, e)
                    genre = None
                timing.add("deezer", started)
                with cond:
                    ready.extend((waiting, genre) for waiting in parked.pop(key, []))
                    cond.notify_all()
        finally:
            search_conn.close()

    def step_aside(key, entry) -> None:
        """Called with the lock held."""
        first = key not in parked
        parked.setdefault(key, []).append(entry)
        if first:
            searches.put((key, entry))
            if not searchers:
                for index in range(LOOKUP_THREADS):
                    thread = threading.Thread(target=search_body, daemon=True, name=f"metadata-search-{index}")
                    thread.start()
                    searchers.append(thread)

    def work(thread_conn):
        while True:
            with cond:
                while True:
                    if stopped():
                        cond.notify_all()
                        return
                    if ready:
                        entry, searched = ready.popleft()
                        busy[0] += 1
                        break
                    if not parked and not busy[0]:
                        cond.notify_all()
                        return
                    cond.wait(0.2)
            result = None
            try:
                key = None
                if searched is _NOT_SEARCHED:
                    key = needed_album(thread_conn, entry, time.time())
                if key is not None:
                    with cond:
                        step_aside(key, entry)
                else:
                    result = fix_file(thread_conn, entry, time.time(), api, write, write_off, searched, timing)
            except Exception as e:
                # One bad file must not stop the rest, nor be mistaken for done.
                logger.warning("Could not process %s: %s", entry.get("path"), e)
                result = {"written": False, "error": str(e)[:200]}
            due = False
            with cond:
                busy[0] -= 1
                if result is not None:
                    report["done"] += 1
                    report["written"] += 1 if result["written"] else 0
                    report["errors"] += 1 if result["error"] else 0
                    due = report["done"] % PROGRESS_EVERY_FILES == 0 or time.monotonic() - last_report[0] >= PROGRESS_EVERY_SECONDS
                    if due:
                        last_report[0] = time.monotonic()
                snapshot = dict(report)
                cond.notify_all()
            if progress and due:
                progress(snapshot["done"], total, snapshot["written"], snapshot["errors"])

    def thread_body():
        thread_conn = mixes_db.connect()
        try:
            work(thread_conn)
        finally:
            thread_conn.close()

    try:
        if workers <= 1:
            work(conn)
        else:
            threads = [threading.Thread(target=thread_body, daemon=True, name=f"metadata-fix-{i}") for i in range(workers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
    finally:
        closing.set()
        for thread in searchers:
            thread.join()
    conn.commit()
    report["timing"] = timing.summary()
    report["workers"] = workers
    return report


def undo(conn, progress=None, should_stop=None) -> dict:
    """Takes back what this app added, and stops adding: the results stay in mixes.db,
    so the mixes carry on. A value someone changed since is yours, and stays."""
    mixes_db.set_meta(conn, "metadata_write_off", True)
    report = {"undone": 0, "kept": 0, "errors": 0}
    rows = conn.execute("SELECT * FROM track_features WHERE added_bpm IS NOT NULL OR added_genre IS NOT NULL").fetchall()
    for index, row in enumerate(rows, start=1):
        if should_stop and should_stop():
            break
        path = row["path"]
        try:
            audio = MutagenFile(path, easy=True)
            keys = []
            if row["added_bpm"] and _first((audio.tags or {}).get("bpm")) == row["added_bpm"]:
                keys.append("bpm")
            if row["added_genre"] and _first((audio.tags or {}).get("genre")) == row["added_genre"]:
                keys.append("genre")
            if keys:
                remove_tags(path, keys, conn)
                report["undone"] += 1
            else:
                report["kept"] += 1
        except Exception as e:
            report["errors"] += 1
            logger.info("Could not undo %s: %s", path, e)
            continue
        conn.execute("UPDATE track_features SET added_bpm=NULL, added_genre=NULL, write_state=?, mtime_ns=? WHERE path=?",
                     (OFF, _mtime(path) or row["mtime_ns"], path))
        conn.commit()
        if progress and index % 25 == 0:
            progress(index, len(rows))
    return report


def features_map(conn) -> dict:
    """path -> (bpm, genre)"""
    return {r["path"]: (r["bpm"], r["genre"]) for r in conn.execute("SELECT path, bpm, genre FROM track_features")}


def move_file(conn, old, new) -> None:
    """A file that moves keeps what is known about it, so it is not measured again."""
    conn.execute("UPDATE OR REPLACE track_features SET path=? WHERE path=?", (str(new), str(old)))
    conn.execute("UPDATE OR REPLACE repair_checked SET path=? WHERE path=?", (str(new), str(old)))
    conn.commit()


def status(conn, entries) -> dict:
    states = dict(conn.execute("SELECT write_state, COUNT(*) FROM track_features GROUP BY write_state").fetchall())
    return {
        "total": len(entries),
        "left": len(pending(conn, entries)),
        "tagged": states.get(WRITTEN, 0),
        "only_in_app": states.get(UNSUPPORTED, 0) + states.get(OFF, 0),
        "write_errors": states.get(FAILED, 0),
        "can_undo": conn.execute(
            "SELECT COUNT(*) FROM track_features WHERE added_bpm IS NOT NULL OR added_genre IS NOT NULL").fetchone()[0],
        "write_off": writing_off(conn),
        "paused": paused(conn),
    }


# --- What Repair downloads needs to know --------------------------------------

def original_mtimes(conn) -> dict:
    """path -> the file's date before this app first tagged it."""
    return {r["path"]: r["original_mtime"] for r in conn.execute(
        "SELECT path, original_mtime FROM track_features WHERE original_mtime IS NOT NULL")}


def repair_checked(conn) -> set:
    return {r["path"] for r in conn.execute("SELECT path FROM repair_checked")}


def mark_repair_checked(conn, path) -> None:
    conn.execute("INSERT OR REPLACE INTO repair_checked(path, checked_at) VALUES (?,?)", (str(path), int(time.time())))
    conn.commit()


# --- Running it ---------------------------------------------------------------

def is_running() -> bool:
    return _running.locked()


def _refresh_library() -> None:
    from core.library import refresh_library_cache_incremental_with_progress

    refresh_library_cache_incremental_with_progress(progress_cb=lambda **kw: None)


def current_task():
    return _current_task


def _background(work, task_id):
    """One job at a time, in the background, always visible in Activity once it has
    something to do: nothing should write to your files out of sight."""
    global _current_task
    if not _running.acquire(blocking=False):
        return False
    _current_task = task_id

    def runner():
        global _current_task
        conn = mixes_db.connect()
        try:
            recover(conn)
            work(conn)
        except Exception as e:
            logger.error("Fix Missing Metadata stopped: %s", e)
            if _current_task:
                config.push_task_event(_current_task, f"Stopped: {e}", stage="error", done=True, error=True)
        finally:
            conn.close()
            _current_task = None
            _running.release()

    threading.Thread(target=runner, daemon=True, name="metadata-fix").start()
    return True


def _say(message, **kw):
    if _current_task:
        config.push_task_event(_current_task, message, check_cancel=False, **kw)


def _cancelled() -> bool:
    return bool(_current_task and config.cancel_requested(_current_task))


def start_background(load_entries, task_id=None) -> bool:
    """Survives a restart: what was done stays done. Waits for a running repair, which
    needs the files to itself; the next check picks up from there."""

    def work(conn):
        global _current_task
        from core.download_repair import is_running as repairing

        if not available():
            _say("Tempo analysis is not available in this install.", stage="error", done=True, error=True)
            return
        todo = pending(conn, load_entries())
        if not todo:
            _say("Nothing to do: every file is up to date", stage="done", progress=100, done=True)
            return
        if not _current_task:
            _current_task = config.create_task("Fix missing metadata", kind="metadata", cancellable=True)

        def progress(done, total, written, errors):
            _say(f"{done}/{total} files, {written} tagged, {errors} errors", stage="fix", progress=round(done * 100 / total))

        report = run(conn, todo, should_stop=lambda: repairing() or _cancelled(),
                     workers=workers_setting(), progress=progress)
        if report["written"]:
            _refresh_library()
        summary = f"{report['done']} files checked, {report['written']} tagged"
        if report["errors"]:
            summary += f", {report['errors']} could not be written: kept in the app, tried again tomorrow"
        summary += f" ({report['workers']} thread{'s' if report['workers'] != 1 else ''}. Thread time: {report['timing'] or 'none'})"
        if _cancelled():
            mixes_db.set_meta(conn, "metadata_fix_paused", True)
            config.finish_cancelled(_current_task, f"Cancelled: {summary}. Those stay done, and it goes on from there when you ask again")
            return
        _say(summary, stage="done", progress=100, done=True)

    return _background(work, task_id)


def start_undo(task_id) -> bool:
    def work(conn):
        report = undo(conn, should_stop=_cancelled,
                      progress=lambda done, total: _say(f"{done}/{total} files", stage="undo", progress=round(done * 100 / total)))
        if report["undone"]:
            _refresh_library()
        summary = f"Removed from {report['undone']} files"
        if report["kept"]:
            summary += f", {report['kept']} left as they had changed since"
        if report["errors"]:
            summary += f", {report['errors']} could not be changed"
        if _cancelled():
            config.finish_cancelled(_current_task, f"Cancelled: {summary}. Undo again to finish")
            return
        _say(summary, stage="done", progress=100, done=True)

    return _background(work, task_id)


def recover_at_start() -> None:
    conn = mixes_db.connect()
    try:
        cleared = recover(conn)
        if cleared:
            logger.info("Cleared %s temporary files left by a brutal stop", cleared)
    finally:
        conn.close()
