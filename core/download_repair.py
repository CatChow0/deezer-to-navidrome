"""Repairing the files saved by the built-in downloader of 1.10.0 to 1.11.0.

Those versions decrypted every Deezer file with one Blowfish cipher for the
whole file, so the first 8 bytes of every encrypted block after the first came
out wrong: the files play with noise and skips, or not at all.

Nothing in those files says which Deezer track they come from, so each one is
looked up from its tags, downloaded again, and decrypted both ways. The file is
replaced only when it is byte for byte what the faulty code produced; a file
that matches the correct decryption is left alone, as is anything that cannot
be identified (files from another downloader, for instance).
"""
import os
import threading
import time
from datetime import datetime, timezone

import requests
from Crypto.Cipher import Blowfish
from mutagen import File as MutagenFile

from core import deezer_dl
from core.deezer_account import API_URL
from core.normalization import normalize_text

# The built-in downloader shipped on 2026-10-21; older files cannot be broken.
# A day of margin covers the time zones.
BROKEN_SINCE = datetime(2026, 10, 20, tzinfo=timezone.utc).timestamp()

AUDIO_EXTENSIONS = {".mp3": False, ".flac": True}
# Bytes compared near the end of the file, where only audio frames are (tags
# live at the start). The last bytes are skipped in case of an ID3v1 tag.
WINDOW = 64 * 1024
TRAILER = 128

_running = threading.Lock()


def is_running():
    return _running.locked()


def _faulty_decrypt(data, key):
    """What 1.10.0 to 1.11.0 wrote: one cipher carried across the blocks."""
    out = bytearray(data)
    cipher = Blowfish.new(key.encode(), Blowfish.MODE_CBC, deezer_dl.CIPHER_IV)
    for index in range(len(out) // deezer_dl.BLOCK_SIZE):
        if index % 3:
            continue
        start = index * deezer_dl.BLOCK_SIZE
        out[start:start + deezer_dl.BLOCK_SIZE] = cipher.decrypt(bytes(out[start:start + deezer_dl.BLOCK_SIZE]))
    return bytes(out)


def _window(data):
    return data[-(WINDOW + TRAILER):-TRAILER]


def _first(tags, key):
    value = (tags or {}).get(key)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _number(value):
    try:
        return int(str(value).split("/")[0])
    except (TypeError, ValueError):
        return None


def _read_tags(path):
    easy = MutagenFile(path, easy=True)
    tags = easy.tags if easy is not None else None
    info = {
        "artist": _first(tags, "artist"),
        "albumartist": _first(tags, "albumartist"),
        "title": _first(tags, "title"),
        "album": _first(tags, "album"),
        "track": _number(_first(tags, "tracknumber")),
        "disc": _number(_first(tags, "discnumber")),
        "deezer_id": "",
    }
    raw = MutagenFile(path)
    if raw is not None and raw.tags is not None:
        if path.suffix.lower() == ".flac":
            info["deezer_id"] = _first(raw.tags, deezer_dl.DEEZER_ID_TAG.lower())
        else:
            frame = raw.tags.get("TXXX:" + deezer_dl.DEEZER_ID_TAG)
            info["deezer_id"] = str(frame.text[0]) if frame and frame.text else ""
    return info


def _search(kind, query, limit=5):
    try:
        data = requests.get(f"{API_URL}/search/{kind}", params={"q": query, "limit": limit}, timeout=30).json()
        return data.get("data") or []
    except Exception:
        return []


def _same(a, b):
    return normalize_text(a or "") == normalize_text(b or "")


class _Finder:
    """Deezer tracks a file may come from, best guesses first."""

    def __init__(self):
        self.albums = {}

    def _album_songs(self, artist, album):
        key = (normalize_text(artist), normalize_text(album))
        if key not in self.albums:
            songs = []
            for item in _search("album", f'artist:"{artist}" album:"{album}"') or _search("album", f"{artist} {album}"):
                if not _same(item.get("title"), album):
                    continue
                try:
                    songs.append(deezer_dl.fetch_album(item["id"]))
                except Exception:
                    continue
            self.albums[key] = songs
        return self.albums[key]

    def candidates(self, tags):
        # The album tag names the exact release, single tracks included: the
        # track search may only find another release of the same title.
        artist = tags["albumartist"] or tags["artist"]
        if tags["album"]:
            for songs in self._album_songs(artist, tags["album"]):
                for song in songs:
                    same_track = tags["track"] and _number(song.get("TRACK_NUMBER")) == tags["track"]
                    same_disc = not tags["disc"] or _number(song.get("DISK_NUMBER")) in (None, tags["disc"])
                    if (same_track and same_disc) or _same(song.get("SNG_TITLE"), tags["title"]):
                        yield song
        if tags["artist"] and tags["title"]:
            found = _search("track", f'artist:"{tags["artist"]}" track:"{tags["title"]}"') \
                or _search("track", f'{tags["artist"]} {tags["title"]}')
            for item in found:
                if not _same(item.get("title"), tags["title"]):
                    continue
                try:
                    yield deezer_dl.fetch_track(item["id"])
                except Exception:
                    continue


def _formats(is_flac):
    if is_flac:
        return ["FLAC"]
    quality = deezer_dl.session().quality or {}
    return ["MP3_320", "MP3_128"] if quality.get("high") or quality.get("lossless") else ["MP3_128"]


def _check(data, song, is_flac):
    """("broken", good payload, source song), ("fine", ...) or None."""
    s = deezer_dl.session()
    for sound_format in _formats(is_flac):
        try:
            url, source = deezer_dl._source(song, sound_format)
        except Exception:
            continue
        resp = s.http.get(url, timeout=120)
        resp.raise_for_status()
        raw = resp.content
        key = deezer_dl._cipher_key(source["SNG_ID"])
        good, faulty = deezer_dl._decrypt(raw, key), _faulty_decrypt(raw, key)
        if _window(data) == _window(good):
            return "fine", None
        if _window(data) == _window(faulty):
            return "broken", good
    return None


def _replace(path, payload, song, is_flac):
    temporary = path.with_name(path.name + ".repair")
    temporary.write_bytes(payload)
    try:
        deezer_dl._write_tags(temporary, song, is_flac)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def suspect_files(root):
    """Audio files the faulty downloader may have written."""
    files = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in AUDIO_EXTENSIONS or not path.is_file():
            continue
        try:
            if path.stat().st_mtime < BROKEN_SINCE:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def repair_downloads(progress=None):
    """Checks every recent file of the downloads folder and repairs the broken
    ones. `progress(message, percent)` follows it. Returns a summary."""
    if not _running.acquire(blocking=False):
        raise RuntimeError("A repair is already running")
    try:
        root = deezer_dl.download_dir()
        files = suspect_files(root)
        summary = {"checked": len(files), "repaired": [], "fine": 0, "unknown": [], "errors": []}
        finder = _Finder()
        say = progress or (lambda message, percent: None)
        say(f"{len(files)} file{'s' if len(files) != 1 else ''} saved since 1.10.0 to check", 0)

        for index, path in enumerate(files, start=1):
            name = path.relative_to(root).as_posix()
            percent = round(index * 100 / len(files)) if files else 100
            is_flac = AUDIO_EXTENSIONS[path.suffix.lower()]
            try:
                tags = _read_tags(path)
                if tags["deezer_id"]:
                    # Only the fixed downloader writes this tag.
                    summary["fine"] += 1
                    say(f"{index}/{len(files)}: {name}: fine", percent)
                    continue
                data = path.read_bytes()
                result = None
                for song in finder.candidates(tags):
                    result = _check(data, song, is_flac)
                    if result:
                        break
                    time.sleep(0.2)
                if result is None:
                    summary["unknown"].append(name)
                    say(f"{index}/{len(files)}: {name}: not found on Deezer, left as it is", percent)
                elif result[0] == "fine":
                    summary["fine"] += 1
                    say(f"{index}/{len(files)}: {name}: fine", percent)
                else:
                    _replace(path, result[1], song, is_flac)
                    summary["repaired"].append(name)
                    say(f"{index}/{len(files)}: {name}: repaired", percent)
            except Exception as e:
                summary["errors"].append(f"{name} ({e})")
                say(f"{index}/{len(files)}: {name}: error: {e}", percent)
        return summary
    finally:
        _running.release()
