"""Downloading music from Deezer.

Deezer serves its files encrypted: the URL is signed with the account's
license token, and every third 2048-byte block of the file is encrypted with
Blowfish. Both the cipher and the metadata writing are adapted from
deezer-downloader by kmille (MIT licence, see LICENSE).

The track tokens come from Deezer's private gateway, so the whole flow needs
a valid ARL and the account's rights: a free account only gets MP3_128.
"""
import hashlib
import os
import re
import threading
from binascii import a2b_hex, b2a_hex
from pathlib import Path

import requests
from Crypto.Cipher import Blowfish
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, PictureType
from mutagen.mp3 import MP3

from core.config import load_secret
from core.deezer_account import API_URL, USER_AGENT, DeezerAccountError, DeezerSession

MEDIA_URL = "https://media.deezer.com/v1/get_url"
COVER_URL = "https://e-cdns-images.dzcdn.net/images/cover/{md5}/1200x1200.jpg"

# Blowfish key material used by Deezer's BF_CBC_STRIPE cipher.
CIPHER_KEY = b"g4el58wc0zvf9na1"
CIPHER_IV = a2b_hex("0001020304050607")
BLOCK_SIZE = 2048

_session = DeezerSession()
_session_lock = threading.Lock()


class DeezerDownloadError(RuntimeError):
    pass


def _log(message):
    print(f"[deezer-dl] {message}", flush=True)


# ── Session ───────────────────────────────────────────────────────────────────

def download_arl():
    """The ARL used for downloads: the premium one when there is one."""
    return load_secret("deezer_arl_premium") or load_secret("deezer_arl")


def session():
    """A logged-in session for the download account."""
    arl = download_arl()
    if not arl:
        raise DeezerDownloadError(
            "No Deezer account connected. Add your ARL in Settings, or a premium one for the downloads."
        )
    with _session_lock:
        if _session.arl != arl or _session.http is None:
            _session.login(arl)
        return _session


def account_info():
    """What the download account can do, without raising."""
    try:
        s = session()
        return {
            "connected": True,
            "premium": s.is_premium(),
            "quality": s.quality,
            "format": s.sound_format(),
            "error": None,
        }
    except DeezerAccountError as e:
        return {"connected": False, "premium": False, "quality": {}, "format": None, "error": str(e)}
    except Exception as e:
        return {"connected": False, "premium": False, "quality": {}, "format": None, "error": str(e)}


def forget_sessions():
    with _session_lock:
        _session.reset()


# ── Metadata ──────────────────────────────────────────────────────────────────

def _clean_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return re.sub(r"\s+", " ", name).strip()


def track_filename(song, extension, with_number=False):
    artist = _clean_filename(song.get("ART_NAME") or "Unknown artist")
    title = _clean_filename(song.get("SNG_TITLE") or "Unknown title")
    if with_number:
        number = int(song.get("TRACK_NUMBER") or 0)
        return f"{number:02d} - {artist} {title}.{extension}"
    return f"{artist} - {title}.{extension}"


def album_folder(song):
    artist = _clean_filename(song.get("ALB_ART_NAME") or song.get("ART_NAME") or "Unknown artist")
    album = _clean_filename(song.get("ALB_TITLE") or "Unknown album")
    return f"{artist} - {album}"


# ── Cipher ────────────────────────────────────────────────────────────────────

def _cipher_key(song_id):
    digest = b2a_hex(hashlib.md5(str(song_id).encode()).digest())
    return "".join(chr(digest[i] ^ digest[i + 16] ^ CIPHER_KEY[i]) for i in range(16))


def _decrypt(data, key):
    """Deezer encrypts every third block of 2048 bytes; the rest is plain."""
    out = bytearray(data)
    cipher = Blowfish.new(key.encode(), Blowfish.MODE_CBC, CIPHER_IV)
    for index in range(len(out) // BLOCK_SIZE):
        if index % 3:
            continue
        start = index * BLOCK_SIZE
        out[start:start + BLOCK_SIZE] = cipher.decrypt(bytes(out[start:start + BLOCK_SIZE]))
    return bytes(out)


# ── Tags ──────────────────────────────────────────────────────────────────────

def _cover(song):
    picture = song.get("ALB_PICTURE")
    if not picture:
        return None
    try:
        resp = requests.get(COVER_URL.format(md5=picture), timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _write_tags(path, song, is_flac):
    cover = _cover(song)
    artist = song.get("ART_NAME")
    title = song.get("SNG_TITLE")
    album = song.get("ALB_TITLE")
    album_artist = song.get("ALB_ART_NAME") or artist
    track_number = song.get("TRACK_NUMBER")
    disc_number = song.get("DISK_NUMBER")
    released = song.get("PHYSICAL_RELEASE_DATE") or song.get("DIGITAL_RELEASE_DATE")

    if is_flac:
        audio = FLAC(path)
        for key, value in (("artist", artist), ("albumartist", album_artist), ("title", title), ("album", album)):
            if value:
                audio[key] = value
        if track_number:
            audio["tracknumber"] = str(track_number)
        if disc_number:
            audio["discnumber"] = str(disc_number)
        if released:
            audio["date"] = str(released)[:4]
        if cover:
            picture = Picture()
            picture.mime = "image/jpeg"
            picture.type = PictureType.COVER_FRONT
            picture.desc = "Cover"
            picture.data = cover
            audio.add_picture(picture)
        audio.save()
        return

    audio = MP3(path)
    if artist:
        audio["TPE1"] = TPE1(encoding=3, text=artist)
    if album_artist:
        audio["TPE2"] = TPE2(encoding=3, text=album_artist)
    if title:
        audio["TIT2"] = TIT2(encoding=3, text=title)
    if album:
        audio["TALB"] = TALB(encoding=3, text=album)
    if track_number:
        audio["TRCK"] = TRCK(encoding=3, text=str(track_number))
    if disc_number:
        audio["TPOS"] = TPOS(encoding=3, text=str(disc_number))
    if released:
        audio["TDRC"] = TDRC(encoding=3, text=str(released)[:4])
    if cover:
        audio["APIC"] = APIC(encoding=3, mime="image/jpeg", type=PictureType.COVER_FRONT, desc="Cover", data=cover)
    audio.save(v2_version=3)


# ── Files ─────────────────────────────────────────────────────────────────────

def configured_download_dir(cfg=None):
    """The folder set in Settings, or "" when none is set.

    The setting replaced the address of the separate downloader: a URL left
    there (an old value, or a browser restoring the form) is not a folder."""
    from core.config import load_config

    value = ((cfg or load_config()).get("deezer_dl_dir") or "").strip()
    return "" if "://" in value else value


def download_dir():
    """Where the downloaded files go: the same layout as before."""
    from core.config import load_config

    cfg = load_config()
    configured = configured_download_dir(cfg)
    if configured:
        return Path(configured)
    # /music/deezer-dl is the default; it is one of the scanned folders.
    for folder in cfg.get("scan_dirs") or []:
        if Path(folder).name == "deezer-dl":
            return Path(folder)
    return Path("/music/deezer-dl")


def download_dir_status():
    """The folder the downloads go to, and whether they can be written there."""
    folder = download_dir()
    exists = folder.is_dir()
    return {
        "path": str(folder),
        "configured": configured_download_dir(),
        "exists": exists,
        "writable": exists and os.access(folder, os.W_OK),
    }


# ── Downloading ────────────────────────────────────────────────────────────────

def _media_url(track_token, sound_format):
    s = session()
    resp = requests.post(
        MEDIA_URL,
        json={
            "license_token": s.license_token,
            "media": [{"type": "FULL", "formats": [{"cipher": "BF_CBC_STRIPE", "format": sound_format}]}],
            "track_tokens": [track_token],
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("data") or "errors" in data["data"][0]:
        errors = (data.get("data") or [{}])[0].get("errors") or [{"message": "unknown error"}]
        raise DeezerDownloadError(errors[0].get("message", "Deezer refused the download"))
    sources = (data["data"][0].get("media") or [{}])[0].get("sources") or []
    if not sources:
        raise DeezerDownloadError("Deezer returned no download link for this track")
    return sources[0]["url"]


def download_song(song, target, on_bytes=None):
    """Downloads one track to `target` and writes its tags.

    `on_bytes(received, total)` follows the transfer; `total` is 0 when Deezer
    does not say the size. Returns the path."""
    s = session()
    sound_format = s.sound_format()
    track_token = song.get("TRACK_TOKEN")
    if not track_token:
        raise DeezerDownloadError("Deezer did not give a download token for this track")

    url = _media_url(track_token, sound_format)
    resp = s.http.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("Content-Length") or 0)
    chunks, received = [], 0
    for chunk in resp.iter_content(64 * 1024):
        chunks.append(chunk)
        received += len(chunk)
        if on_bytes:
            on_bytes(received, total)
    payload = _decrypt(b"".join(chunks), _cipher_key(song["SNG_ID"]))

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, target)

    try:
        _write_tags(target, song, sound_format == "FLAC")
    except Exception as e:
        _log(f"Could not write the tags of {target.name}: {e}")
    return target


def fetch_track(track_id):
    """The track data of one Deezer track, with its download token."""
    data = session().gw("song.getData", {"SNG_ID": str(track_id)})
    if not data or not data.get("TRACK_TOKEN"):
        raise DeezerDownloadError(f"Deezer has no downloadable version of track {track_id}")
    return data


def fetch_album(album_id):
    """Every track of an album, with their download tokens."""
    results = session().gw(
        "deezer.pageAlbum", {"ALB_ID": str(album_id), "start": 0, "nb": 300, "lang": "en"}
    ) or {}
    songs = (results.get("SONGS") or {}).get("data") or []
    if not songs:
        raise DeezerDownloadError(f"Deezer has no track for album {album_id}")
    album = results.get("DATA") or {}
    for song in songs:
        song.setdefault("ALB_ART_NAME", album.get("ART_NAME"))
        song.setdefault("ALB_TITLE", album.get("TITLE"))
    return songs


def fetch_playlist(playlist_id):
    """Every track of a Deezer playlist, with their download tokens."""
    results = session().gw(
        "deezer.pagePlaylist",
        {"playlist_id": int(playlist_id), "start": 0, "tab": 0, "header": True, "lang": "en", "nb": 100000},
    ) or {}
    songs = (results.get("SONGS") or {}).get("data") or []
    if not songs:
        raise DeezerDownloadError(f"Deezer has no track for playlist {playlist_id}")
    album = results.get("DATA") or {}
    for song in songs:
        song.setdefault("ALB_ART_NAME", song.get("ART_NAME"))
        song.setdefault("ALB_TITLE", song.get("ALB_TITLE") or album.get("TITLE"))
    return songs


def song_label(song):
    return f"{song.get('ART_NAME') or 'Unknown artist'} - {song.get('SNG_TITLE') or 'Unknown title'}"


def download_track(track_id, base_dir=None, on_start=None, on_bytes=None):
    """Downloads one track into the songs folder.

    `on_start(song, already_there)` is called once the track is known.
    Returns the path."""
    song = fetch_track(track_id)
    extension = "flac" if session().sound_format() == "FLAC" else "mp3"
    base = Path(base_dir) if base_dir else download_dir() / "songs"
    target = base / track_filename(song, extension)
    already = target.exists()
    if on_start:
        on_start(song, already)
    if already:
        _log(f"Already there: {target.name}")
        return target
    return download_song(song, target, on_bytes=on_bytes)


def download_album(album_id, base_dir=None, on_track=None, on_start=None):
    """Downloads every track of an album into its own folder.

    `on_start(songs)` is called once the track list is known; `on_track` with
    (song, path_or_None, error) after each track, so the caller can follow the
    progress and collect the tracks that failed. Tracks already on disk are
    kept, so downloading an album again only fetches what is missing."""
    songs = fetch_album(album_id)
    if on_start:
        on_start(songs)
    extension = "flac" if session().sound_format() == "FLAC" else "mp3"
    root = Path(base_dir) if base_dir else download_dir() / "albums"
    folder = root / album_folder(songs[0])
    folder.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for song in songs:
        target = folder / track_filename(song, extension, with_number=True)
        try:
            if target.exists():
                _log(f"Already there: {target.name}")
            else:
                download_song(song, target)
            downloaded.append(target)
            if on_track:
                on_track(song, target, None)
        except Exception as e:
            _log(f"Could not download {song.get('SNG_TITLE')}: {e}")
            if on_track:
                on_track(song, None, e)
    return downloaded


def artist_albums(artist_id):
    """[{id, title}] of every release of an artist, from the public API."""
    albums, index = [], 0
    while True:
        page = requests.get(
            f"{API_URL}/artist/{artist_id}/albums", params={"limit": 100, "index": index}, timeout=30
        ).json()
        if "error" in page:
            raise DeezerDownloadError(f"Deezer has no release for artist {artist_id}")
        data = page.get("data") or []
        albums += [{"id": str(a["id"]), "title": a.get("title") or ""} for a in data]
        index += len(data)
        if not data or index >= int(page.get("total") or 0):
            return albums
