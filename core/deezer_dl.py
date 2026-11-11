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
import tempfile
import threading
from binascii import a2b_hex, b2a_hex
from pathlib import Path

import requests
from Crypto.Cipher import Blowfish
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, TXXX, PictureType
from mutagen.mp3 import MP3

from core.deezer_account import USER_AGENT, DeezerSession

MEDIA_URL = "https://media.deezer.com/v1/get_url"
COVER_URL = "https://e-cdns-images.dzcdn.net/images/cover/{md5}/1200x1200.jpg"

# Blowfish key material used by Deezer's BF_CBC_STRIPE cipher.
CIPHER_KEY = b"g4el58wc0zvf9na1"
CIPHER_IV = a2b_hex("0001020304050607")
BLOCK_SIZE = 2048

# Tag holding the Deezer id of the track a file was downloaded for (TXXX
# description in MP3, field name in FLAC), so a file can be traced back.
DEEZER_ID_TAG = "DEEZER_TRACK_ID"

_session = DeezerSession()
_session_lock = threading.Lock()


class DeezerDownloadError(RuntimeError):
    pass


NO_LINK = "Deezer returned no download link for this track"


def _log(message):
    print(f"[deezer-dl] {message}", flush=True)


# ── Session ───────────────────────────────────────────────────────────────────

def download_arl():
    """The ARL of the account marked "Use for download", else of the default one."""
    from core import deezer_accounts

    account_id = deezer_accounts.download_id()
    return deezer_accounts.arl(account_id) if account_id else ""


def session():
    """A logged-in session for the download account."""
    arl = download_arl()
    if not arl:
        raise DeezerDownloadError("No Deezer account for the downloads: add one in Settings → Deezer accounts.")
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
            "country": s.country,
            "error": None,
        }
    except Exception as e:
        return {"connected": False, "premium": False, "quality": {}, "format": None, "error": str(e)}


def forget_sessions():
    with _session_lock:
        _session.reset()


# ── Metadata ──────────────────────────────────────────────────────────────────

def _clean_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return re.sub(r"\s+", " ", name).strip()


# Below the 255 bytes most file systems allow for a name, with room for the
# extension and a temporary suffix.
MAX_NAME_BYTES = 200


def _fit(name: str) -> str:
    data = name.encode("utf-8")
    if len(data) <= MAX_NAME_BYTES:
        return name
    return data[:MAX_NAME_BYTES].decode("utf-8", "ignore").rstrip(" .")


def song_title(song) -> str:
    """The title with its version, as Deezer shows it: "Song (Remix)". Without
    it, the remix and the original share a file name, and the second is never
    downloaded ("Already there")."""
    title = (song.get("SNG_TITLE") or "").strip()
    version = (song.get("VERSION") or "").strip()
    if version and version.casefold() not in title.casefold():
        title = f"{title} {version}"
    return title


def track_filename(song, extension, with_number=False):
    artist = _clean_filename(song.get("ART_NAME") or "Unknown artist")
    title = _clean_filename(song_title(song) or "Unknown title")
    if with_number:
        number = int(song.get("TRACK_NUMBER") or 0)
        disc = int(song.get("DISK_NUMBER") or 1)
        # Track 3 of the second disc is not track 3 of the first.
        prefix = f"{disc}-{number:02d}" if disc > 1 else f"{number:02d}"
        return f"{_fit(f'{prefix} - {artist} {title}')}.{extension}"
    return f"{_fit(f'{artist} - {title}')}.{extension}"


def album_folder(song):
    artist = _clean_filename(song.get("ALB_ART_NAME") or song.get("ART_NAME") or "Unknown artist")
    album = _clean_filename(song.get("ALB_TITLE") or "Unknown album")
    return _fit(f"{artist} - {album}")


# ── Cipher ────────────────────────────────────────────────────────────────────

def _cipher_key(song_id):
    digest = b2a_hex(hashlib.md5(str(song_id).encode()).digest())
    return "".join(chr(digest[i] ^ digest[i + 16] ^ CIPHER_KEY[i]) for i in range(16))


def _decrypt(data, key):
    """Deezer encrypts every third block of 2048 bytes; the rest is plain.

    Each encrypted block is its own CBC message starting from the IV, so it
    needs a fresh cipher: reusing one carries the chaining state over and
    garbles the first 8 bytes of every encrypted block after the first."""
    out = bytearray(data)
    for index in range(len(out) // BLOCK_SIZE):
        if index % 3:
            continue
        start = index * BLOCK_SIZE
        cipher = Blowfish.new(key.encode(), Blowfish.MODE_CBC, CIPHER_IV)
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


def _album_genre(song):
    """Without it, a downloaded file has no genre. A failure must not stop the download."""
    if not song.get("ALB_ID"):
        return None
    try:
        from core.deezer import _public_api

        genres = ((_public_api(f"/album/{song['ALB_ID']}") or {}).get("genres") or {}).get("data") or []
        return genres[0].get("name") if genres else None
    except Exception as e:
        _log(f"No genre for album {song['ALB_ID']}: {e}")
        return None


def _write_tags(path, song, is_flac):
    cover = _cover(song)
    artist = song.get("ART_NAME")
    title = song_title(song)
    album = song.get("ALB_TITLE")
    album_artist = song.get("ALB_ART_NAME") or artist
    track_number = song.get("TRACK_NUMBER")
    disc_number = song.get("DISK_NUMBER")
    released = song.get("PHYSICAL_RELEASE_DATE") or song.get("DIGITAL_RELEASE_DATE")
    genre = _album_genre(song)

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
        if genre:
            audio["genre"] = genre
        if song.get("SNG_ID"):
            audio[DEEZER_ID_TAG.lower()] = str(song["SNG_ID"])
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
    if genre:
        audio["TCON"] = TCON(encoding=3, text=genre)
    if song.get("SNG_ID"):
        audio["TXXX:" + DEEZER_ID_TAG] = TXXX(encoding=3, desc=DEEZER_ID_TAG, text=str(song["SNG_ID"]))
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
        raise DeezerDownloadError(NO_LINK)
    return sources[0]["url"]


def is_explicit(song):
    return str(song.get("EXPLICIT_LYRICS") or "0") == "1"


def _in_country():
    country = session().country
    return f" ({country})" if country else ""


def _unavailable(error):
    """The message for a track Deezer will not serve to this account."""
    if str(error) != NO_LINK:
        return DeezerDownloadError(str(error))
    return DeezerDownloadError(f"Not available for your Deezer account{_in_country()}")


def _source(song, sound_format):
    """(url, song the file comes from).

    When a release is not available, Deezer often names another release of the
    same recording (FALLBACK). It is only used when it is explicit exactly when
    the requested track is: otherwise an explicit track could silently come
    back as its censored version."""
    try:
        return _media_url(song["TRACK_TOKEN"], sound_format), song
    except DeezerDownloadError as error:
        fallback = song.get("FALLBACK") or {}
        if not fallback.get("TRACK_TOKEN"):
            raise _unavailable(error)
        if is_explicit(fallback) != is_explicit(song):
            version = "censored" if is_explicit(song) else "explicit"
            raise DeezerDownloadError(f"Only the {version} version is available for your Deezer account{_in_country()}")
        try:
            return _media_url(fallback["TRACK_TOKEN"], sound_format), fallback
        except DeezerDownloadError:
            raise _unavailable(error)


def download_song(song, target, on_bytes=None, on_note=None):
    """Downloads one track to `target` and writes its tags.

    `on_bytes(received, total)` follows the transfer; `total` is 0 when Deezer
    does not say the size. `on_note(message)` is told when the file comes from
    another release of the same recording. The tags stay those of the
    requested track, so an album keeps its own title and numbering.
    Returns the path."""
    s = session()
    sound_format = s.sound_format()
    if not song.get("TRACK_TOKEN"):
        raise DeezerDownloadError("Deezer did not give a download token for this track")

    url, source = _source(song, sound_format)
    if source is not song:
        note = f"From another release: {source.get('ALB_TITLE') or 'unknown album'}"
        _log(f"{song_label(song)}: {note}")
        if on_note:
            on_note(note)
    resp = s.http.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("Content-Length") or 0)
    chunks, received = [], 0
    for chunk in resp.iter_content(64 * 1024):
        chunks.append(chunk)
        received += len(chunk)
        if on_bytes:
            on_bytes(received, total)
    payload = _decrypt(b"".join(chunks), _cipher_key(source["SNG_ID"]))

    target.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own: two downloads of one track at once must not share a
    # file. Tagged before it takes its place, so the library never reads it
    # without its tags.
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.chmod(temporary, 0o644)
        try:
            _write_tags(Path(temporary), song, sound_format == "FLAC")
        except Exception as e:
            _log(f"Could not write the tags of {target.name}: {e}")
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
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


def song_label(song):
    return f"{song.get('ART_NAME') or 'Unknown artist'} - {song_title(song) or 'Unknown title'}"


def download_track(track_id, base_dir=None, on_start=None, on_bytes=None, on_note=None):
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
    return download_song(song, target, on_bytes=on_bytes, on_note=on_note)


def download_album(album_id, base_dir=None, on_track=None, on_start=None, on_note=None):
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
                download_song(song, target, on_note=(lambda note, song=song: on_note(song, note)) if on_note else None)
            downloaded.append(target)
            if on_track:
                on_track(song, target, None)
        except Exception as e:
            _log(f"Could not download {song.get('SNG_TITLE')}: {e}")
            if on_track:
                on_track(song, None, e)
    return downloaded


def album_artist_id(album_id) -> str:
    """The Deezer ID of the album's main artist, or "" when Deezer does not say."""
    from core.deezer import _public_api

    try:
        return str(((_public_api(f"/album/{int(album_id)}") or {}).get("artist") or {}).get("id") or "")
    except Exception as e:
        _log(f"No main artist for album {album_id}: {e}")
        return ""


def artist_albums(artist_id):
    """[{id, title}] of every release of an artist, from the public API."""
    from core.deezer import public_pages

    try:
        return [{"id": str(a["id"]), "title": a.get("title") or "",
                 "artist_id": str((a.get("artist") or {}).get("id") or "")}
                for a in public_pages(f"/artist/{int(artist_id)}/albums")]
    except RuntimeError as e:
        raise DeezerDownloadError(f"Deezer has no release for artist {artist_id}") from e
