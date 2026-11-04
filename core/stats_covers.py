"""Covers for the Stats tab, kept in the data folder: art from your own files
first, Deezer for the rest. Shrunk and stored once per image, so an album's
tracks share a file. Entries follow the track, album or artist key, not its row
id, because Start clean renumbers rows."""
import base64
import hashlib
import io
import logging
import time
from contextlib import closing
from pathlib import Path

import requests
from mutagen import File as MutagenFile
from mutagen.flac import Picture
from mutagen.id3 import ID3
from PIL import Image

from core import config, stats_db
from core.stats_db import name_key
from core.stats_files import inside_music_folders, local_file, music_root

logger = logging.getLogger(__name__)

MAX_SIZE = 600
DOWNLOAD_TIMEOUT = 5
RETRY_NO_ART = 7 * 86400
RETRY_ERROR = 3600
KINDS = ("track", "album", "artist")
ALBUM_IMAGES = ("cover", "folder", "front")
ARTIST_IMAGES = ("artist", "folder")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")

_ROW = {
    "track": "SELECT id, key, file_path, cover_url FROM tracks WHERE id = ?",
    "album": "SELECT id, key, file_path, cover_url FROM albums WHERE id = ?",
    "artist": "SELECT id, key, picture_url FROM artists WHERE id = ?",
}


def covers_dir() -> Path:
    return Path(config.DATA_DIR) / "stats_covers"


# ── Reading art ───────────────────────────────────────────────────────────────

def _embedded(tags):
    """Art from MP4 or Ogg tags."""
    covers = tags.get("covr")
    if covers:
        return bytes(covers[0])
    for encoded in tags.get("metadata_block_picture") or []:
        try:
            return Picture(base64.b64decode(encoded)).data
        except Exception:
            continue
    return None


def _id3_art(path):
    """Tags alone, for an MP3 whose audio mutagen does not recognise."""
    try:
        frames = ID3(path).getall("APIC")
    except Exception:
        return None
    return max(frames, key=lambda f: f.type == 3).data if frames else None


def _embedded_art(path):
    try:
        audio = MutagenFile(path)
        if audio is None:
            return _id3_art(path)
        pictures = getattr(audio, "pictures", None)
        if pictures:
            return max(pictures, key=lambda p: p.type == 3).data
        tags = audio.tags
        if not tags:
            return None
        if hasattr(tags, "getall"):
            frames = tags.getall("APIC")
            return max(frames, key=lambda f: f.type == 3).data if frames else None
        return _embedded(tags)
    except Exception as e:
        logger.info("Could not read art from %s: %s", path, e)
        return _id3_art(path)


def _image_beside(folder: Path, names):
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return None
    for name in names:
        for entry in entries:
            if entry.stem.casefold() == name and entry.suffix.casefold() in IMAGE_SUFFIXES and inside_music_folders(entry):
                try:
                    return entry.read_bytes()
                except OSError:
                    return None
    return None


def _album_folder_art(path: Path):
    """An image beside loose tracks in an artist folder could belong to any of
    their albums, so the file must sit in a folder of its own."""
    root = music_root(path)
    if root is None or len(path.relative_to(root).parts) < 3:
        return None
    return _image_beside(path.parent, ALBUM_IMAGES)


def _artist_folder_art(path: Path, artist_key):
    root = music_root(path)
    if root is None:
        return None
    parts = path.relative_to(root).parts
    if len(parts) < 2 or name_key(parts[0]) != artist_key:
        return None
    return _image_beside(root / parts[0], ARTIST_IMAGES)


def _download(url):
    """(image bytes or None, whether the network failed)."""
    if not url or "/artist//" in url or "/cover//" in url:
        return None, False
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    except Exception as e:
        logger.info("Could not download %s: %s", url, e)
        return None, True
    if response.status_code != 200:
        return None, response.status_code >= 500
    return response.content, False


# ── Storing ───────────────────────────────────────────────────────────────────

def _main_color(image) -> str:
    """The most present color that is not close to black, white or grey."""
    small = image.resize((40, 40)).quantize(6)
    palette = small.getpalette()
    best, best_score = "#000000", -1.0
    for count, index in small.getcolors():
        red, green, blue = palette[index * 3:index * 3 + 3]
        saturation = (max(red, green, blue) - min(red, green, blue)) / 255
        score = count * (0.15 + saturation)
        if score > best_score:
            best, best_score = f"#{red:02x}{green:02x}{blue:02x}", score
    return best


def _store(data):
    """(file name, main color), or None if this is not an image."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
    except Exception as e:
        logger.info("Skipping unreadable art: %s", e)
        return None
    image.thumbnail((MAX_SIZE, MAX_SIZE))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    content = out.getvalue()
    name = f"{hashlib.sha256(content).hexdigest()[:32]}.jpg"
    folder = covers_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if not target.exists():
        partial = target.with_suffix(f".{time.time_ns()}.tmp")
        partial.write_bytes(content)
        partial.replace(target)
    return name, _main_color(image)


# ── Finding ───────────────────────────────────────────────────────────────────

def _top_track(conn, artist_id):
    return conn.execute(
        "SELECT t.key, t.file_path FROM plays p JOIN track_artists ta ON ta.track_id = p.track_id"
        " JOIN tracks t ON t.id = p.track_id WHERE ta.artist_id = ? GROUP BY t.id ORDER BY COUNT(*) DESC LIMIT 1",
        (artist_id,),
    ).fetchone()


def _sources(conn, kind, row):
    """Each candidate as (source name, function giving image bytes or None and
    whether the network failed)."""
    local = lambda read: (lambda: (read(), False))  # noqa: E731
    candidates = []
    if kind == "artist":
        track = _top_track(conn, row["id"])
        path = local_file(track) if track else None
        if path:
            candidates.append(("folder", local(lambda: _artist_folder_art(path, row["key"]))))
        candidates.append(("deezer", lambda: _download(row["picture_url"])))
        return candidates

    if kind == "track":
        path = local_file(row)
    else:
        path = inside_music_folders(row["file_path"]) if row["file_path"] else None
    if path:
        candidates.append(("embedded", local(lambda: _embedded_art(path))))
        candidates.append(("folder", local(lambda: _album_folder_art(path))))
    url = row["cover_url"]
    if kind == "album" and not url:
        found = conn.execute(
            "SELECT MAX(t.cover_url) FROM plays p JOIN tracks t ON t.id = p.track_id WHERE p.album_id = ?", (row["id"],)
        ).fetchone()
        url = found[0] if found else None
    candidates.append(("deezer", lambda: _download(url)))
    return candidates


def _artist_stand_in(conn, artist_id):
    """Their most-played album's cover, while there is no photo."""
    album = conn.execute(
        "SELECT p.album_id FROM plays p JOIN track_artists ta ON ta.track_id = p.track_id"
        " WHERE ta.artist_id = ? AND p.album_id IS NOT NULL GROUP BY p.album_id ORDER BY COUNT(*) DESC LIMIT 1",
        (artist_id,),
    ).fetchone()
    if not album:
        return None
    _cover_with(conn, "album", album[0])
    key = conn.execute("SELECT key FROM albums WHERE id = ?", (album[0],)).fetchone()
    return conn.execute("SELECT file, color FROM covers WHERE kind = 'album' AND item_key = ?", (key[0],)).fetchone() if key else None


def _save(conn, kind, key, file, color, source, retry_at) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO covers(kind, item_key, file, color, source, checked_at, retry_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (kind, key, file, color, source, int(time.time()), retry_at),
    )
    conn.commit()


def _cover_with(conn, kind, item_id):
    row = conn.execute(_ROW[kind], (item_id,)).fetchone()
    if row is None:
        return None
    cached = conn.execute("SELECT file, retry_at FROM covers WHERE kind = ? AND item_key = ?", (kind, row["key"])).fetchone()
    now = int(time.time())
    if cached:
        if cached["file"] and (covers_dir() / cached["file"]).exists():
            return covers_dir() / cached["file"]
        if not cached["file"] and (cached["retry_at"] or 0) > now:
            return None

    network_failed = False
    for source, read in _sources(conn, kind, row):
        data, failed = read()
        network_failed = network_failed or failed
        stored = _store(data) if data else None
        if stored:
            _save(conn, kind, row["key"], stored[0], stored[1], source, None)
            return covers_dir() / stored[0]

    if kind == "artist":
        stand_in = _artist_stand_in(conn, item_id)
        if stand_in and stand_in["file"]:
            _save(conn, kind, row["key"], stand_in["file"], stand_in["color"], "album", None)
            return covers_dir() / stand_in["file"]

    _save(conn, kind, row["key"], None, None, None, now + (RETRY_ERROR if network_failed else RETRY_NO_ART))
    return None


def cover_for(kind, item_id):
    """The cached file for this item, finding the art first if need be."""
    if kind not in KINDS:
        return None
    with closing(stats_db.connect()) as conn:
        return _cover_with(conn, kind, item_id)


def forget(conn, kind, key) -> None:
    """Better art may now exist: look again instead of keeping a stand-in or a gap."""
    conn.execute(
        "DELETE FROM covers WHERE kind = ? AND item_key = ? AND (file IS NULL OR source = 'album')", (kind, key),
    )


def forget_albums_of(conn, track_id) -> None:
    """A track found its cover: an album with none so far may now have one."""
    conn.execute(
        "DELETE FROM covers WHERE kind = 'album' AND file IS NULL AND item_key IN"
        " (SELECT al.key FROM plays p JOIN albums al ON al.id = p.album_id WHERE p.track_id = ?)", (track_id,),
    )


def refresh_after_merge(conn) -> None:
    """Merge just learned where files are: gaps and Deezer covers look again,
    since art from those files comes first."""
    for kind, table in (("track", "tracks"), ("album", "albums")):
        conn.execute(
            f"DELETE FROM covers WHERE kind = ? AND (file IS NULL OR source = 'deezer')"
            f" AND item_key IN (SELECT key FROM {table} WHERE file_path IS NOT NULL)", (kind,),
        )


_UNRESOLVED = "(c.item_key IS NULL OR (c.file IS NULL AND COALESCE(c.retry_at, 0) <= ?))"
_BATCH = {
    "track": "SELECT t.id FROM tracks t JOIN plays p ON p.track_id = t.id"
             " LEFT JOIN covers c ON c.kind = 'track' AND c.item_key = t.key"
             f" WHERE {_UNRESOLVED} GROUP BY t.id ORDER BY COUNT(*) DESC, t.id LIMIT ?",
    "album": "SELECT al.id FROM albums al JOIN plays p ON p.album_id = al.id"
             " LEFT JOIN covers c ON c.kind = 'album' AND c.item_key = al.key"
             f" WHERE {_UNRESOLVED} GROUP BY al.id ORDER BY COUNT(*) DESC, al.id LIMIT ?",
    "artist": "SELECT a.id FROM artists a JOIN track_artists ta ON ta.artist_id = a.id JOIN plays p ON p.track_id = ta.track_id"
              " LEFT JOIN covers c ON c.kind = 'artist' AND c.item_key = a.key"
              f" WHERE {_UNRESOLVED} GROUP BY a.id ORDER BY COUNT(*) DESC, a.id LIMIT ?",
}


def resolve_batch(limit=40) -> int:
    """Fills the cache ahead of time, most played first."""
    done = 0
    with closing(stats_db.connect()) as conn:
        for kind in KINDS:
            for (item_id,) in conn.execute(_BATCH[kind], (int(time.time()), limit)).fetchall():
                _cover_with(conn, kind, item_id)
                done += 1
    return done
