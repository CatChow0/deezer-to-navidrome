"""Sorting the album folders where two releases with one name were mixed.

Before 1.21.1 an album went to "Artist - Album", from its title alone, and a
track already on disk was skipped. The explicit and clean versions of an album
(or two albums with one title) ended up in one folder, each with the tracks the
other did not have. Every file says which Deezer track it is (DEEZER_TRACK_ID),
so its album is known: the files of each release go to the folder a download
gives it now, and the albums are queued again for the tracks they miss.

Clean albums that were not mixed also get their album version, so Navidrome
does not merge them with an explicit one downloaded later. Nothing is deleted;
files without the tag (saved before 1.11.1, or added by hand) and tracks Deezer
no longer knows stay where they are.
"""
import os
import threading
import time

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3

from core import deezer_dl, metadata_fix, mixes_db
from core.utils import FILES_LOCK

# What the downloader writes in a clean album's tags (TXXX:ALBUMVERSION in MP3).
EasyID3.RegisterTXXXKey("albumversion", "ALBUMVERSION")
CLEAN = "Clean"

# Between two albums read from Deezer's gateway: a whole library is read at once.
PAUSE = 0.2

_running = threading.Lock()


def is_running():
    return _running.locked()


def _track_album(track_id):
    """The Deezer ID of a track's album, from the public API; None when unknown."""
    from core.deezer import _public_api

    try:
        album = ((_public_api(f"/track/{int(track_id)}") or {}).get("album") or {}).get("id")
    except Exception:
        return None
    return str(album) if album else None


def _tagged_files(folder):
    """{path: Deezer track ID} of the downloaded files that carry one."""
    found = {}
    for entry in sorted(folder.iterdir()):
        if entry.is_file() and entry.suffix.lower() in deezer_dl.AUDIO_SUFFIXES and not entry.name.startswith("."):
            track_id = deezer_dl.file_deezer_id(entry)
            if track_id:
                found[entry] = track_id
    return found


def _releases(files, lookup_album, album_songs):
    """[(songs, [paths])], one per release in the folder, and the paths whose
    release is not known. One file finds its album, whose track list then
    claims every other file of it: one lookup per release, not per file."""
    remaining = dict(files)
    releases, unknown = [], []
    while remaining:
        path, track_id = next(iter(remaining.items()))
        album_id = lookup_album(track_id)
        songs = album_songs(album_id) if album_id else None
        ids = {str(song.get("SNG_ID")) for song in songs or []}
        members = [p for p, i in remaining.items() if i in ids]
        if not members:
            unknown.append(path)
            members = [path]
        else:
            releases.append((songs, members))
        for member in members:
            del remaining[member]
    return releases, unknown


def _needs_version(path):
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return False
    return audio is not None and CLEAN not in list((audio.tags or {}).get("albumversion") or [])


def _tag_clean(path, conn):
    def change(audio):
        if audio.tags is None:
            audio.add_tags()
        audio["albumversion"] = CLEAN

    metadata_fix._apply(path, change, ["albumversion"], conn)


def _label(songs):
    first = songs[0]
    clean = " (Clean)" if first.get("ALB_CENSORED") else ""
    return f"{first.get('ALB_ART_NAME') or 'Unknown artist'} - {first.get('ALB_TITLE') or 'Unknown album'}{clean}"


def _sort_folder(folder, root, summary, lookup_album, album_songs, conn):
    files = _tagged_files(folder)
    if not files:
        return
    releases, unknown = _releases(files, lookup_album, album_songs)
    summary["unknown"] += [p.relative_to(root).as_posix() for p in unknown]

    if len(releases) > 1:
        # The explicit release with the most files keeps the folder; the
        # others go where a download puts them now.
        stays = max((r for r in releases if not r[0][0].get("ALB_CENSORED")), key=lambda r: len(r[1]), default=None)
        for index, release in enumerate(releases):
            songs, paths = release
            if release is not stays:
                releases[index] = (songs, _move(songs, paths, folder, root, summary))
            summary["refill"].append({"id": str(songs[0].get("ALB_ID")), "label": _label(songs)})
        summary["sorted"].append(folder.name)
        try:
            folder.rmdir()  # only when nothing at all is left in it
        except OSError:
            pass

    for songs, paths in releases:
        if songs[0].get("ALB_CENSORED"):
            for path in paths:
                if path.exists() and _needs_version(path):
                    _tag_clean(path, conn)
                    summary["tagged"] += 1


def _move(songs, paths, folder, root, summary):
    """Moves a release's files to its own folder; returns where they are now."""
    ids = {str(song.get("SNG_ID")) for song in songs}
    target = root / deezer_dl.album_folder(songs[0])
    if target == folder or deezer_dl._holds_other_tracks(target, ids):
        target = root / deezer_dl.album_folder(songs[0], with_id=True)
    target.mkdir(parents=True, exist_ok=True)
    where = []
    for path in paths:
        destination = target / path.name
        if destination.exists():
            # Most likely the same track, downloaded again since: never overwritten.
            summary["left"].append(path.relative_to(root).as_posix())
            where.append(path)
            continue
        with FILES_LOCK:
            os.replace(path, destination)
        summary["moved"] += 1
        where.append(destination)
    return where


def sort_albums(progress=None, should_stop=None, lookup_album=None, fetch_album=None):
    """Sorts every folder of the downloads' albums. `progress(message, percent)`
    follows it. Returns a summary; `refill` lists the albums to download again."""
    lookup_album = lookup_album or _track_album
    fetch_album = fetch_album or deezer_dl.fetch_album
    say = progress or (lambda message, percent: None)
    summary = {"folders": 0, "sorted": [], "moved": 0, "tagged": 0, "unknown": [], "left": [], "errors": [],
               "refill": [], "cancelled": False}
    root = deezer_dl.download_dir() / "albums"
    try:
        folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return summary
    summary["folders"] = len(folders)

    known = {}

    def album_songs(album_id):
        if album_id not in known:
            try:
                known[album_id] = fetch_album(album_id)
            except Exception:
                known[album_id] = None
            time.sleep(PAUSE)
        return known[album_id]

    if not _running.acquire(blocking=False):
        raise RuntimeError("A repair is already running")
    conn = mixes_db.connect()
    try:
        for index, folder in enumerate(folders, start=1):
            if should_stop and should_stop():
                summary["cancelled"] = True
                break
            say(f"Albums {index}/{len(folders)}: {folder.name}", round(index * 100 / len(folders)))
            try:
                _sort_folder(folder, root, summary, lookup_album, album_songs, conn)
            except Exception as e:
                summary["errors"].append(f"{folder.name} ({e})")
        return summary
    finally:
        conn.close()
        _running.release()
