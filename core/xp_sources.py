"""Reading playlists from other platforms: a public Spotify link, or a CSV.

A Spotify link is read from the public embed page (open.spotify.com/embed),
the one websites use to show a player. It needs no account, but it lists only
the first 100 tracks of a public playlist, without album or ISRC. A CSV export
(Exportify, TuneMyMusic, Soundiiz) has no size limit, works for private
playlists, and usually carries the ISRC, which gives an exact Deezer match.

Both readers return the same shape:
    {"title", "picture", "truncated", "tracks": [{"key", "position", "title",
     "artists": [...], "album", "duration_ms", "isrc", "explicit"}]}
`explicit` is None when the source does not say.
"""
import csv
import hashlib
import io
import json
import re

import requests

EMBED_URL = "https://open.spotify.com/embed/playlist/{id}"
# The embed page is a web page: a browser user agent gets the full markup.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
EMBED_LIMIT = 100

SPOTIFY_PLAYLIST = re.compile(
    r"(?:open\.spotify\.com/(?:[a-z-]+/)*playlist/|spotify:playlist:)([A-Za-z0-9]{10,40})"
)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 10_000


class SourceError(RuntimeError):
    pass


def spotify_playlist_id(text):
    """The playlist ID of an open.spotify.com link or a spotify: URI, else None."""
    m = SPOTIFY_PLAYLIST.search(text or "")
    return m.group(1) if m else None


# ── Spotify ───────────────────────────────────────────────────────────────────

def _split_spotify_artists(subtitle):
    # The embed joins artists with a comma and a no-break space.
    parts = re.split(r", ", subtitle or "")
    return [p.strip() for p in parts if p.strip()]


def _cover(entity):
    sources = (entity.get("coverArt") or {}).get("sources") or []
    best = max(sources, key=lambda s: s.get("width") or 0, default=None)
    return (best or {}).get("url") or ""


def read_spotify(playlist_id):
    try:
        resp = requests.get(EMBED_URL.format(id=playlist_id), headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        raise SourceError(f"Spotify did not answer: {e.__class__.__name__}")
    if resp.status_code == 404:
        raise SourceError("Spotify has no public playlist with this link. Private playlists need a CSV export.")
    if resp.status_code != 200:
        raise SourceError(f"Spotify answered HTTP {resp.status_code}")

    m = _NEXT_DATA.search(resp.text)
    try:
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
        items = entity["trackList"]
    except Exception:
        raise SourceError(
            "Spotify changed its page and the playlist could not be read. Import a CSV export instead."
        )

    tracks = []
    for position, item in enumerate(items, start=1):
        uri = str(item.get("uri") or "")
        if not uri.startswith("spotify:track:"):
            continue  # podcast episodes and local files
        tracks.append({
            "key": "sp:" + uri.rsplit(":", 1)[-1],
            "position": position,
            "title": str(item.get("title") or "").strip(),
            "artists": _split_spotify_artists(item.get("subtitle")),
            "album": "",
            "duration_ms": int(item.get("duration") or 0),
            "isrc": "",
            "explicit": bool(item.get("isExplicit")),
        })
    _renumber(tracks)
    return {
        "title": str(entity.get("name") or entity.get("title") or "Spotify playlist").strip(),
        "picture": _cover(entity),
        "truncated": len(items) >= EMBED_LIMIT,
        "tracks": tracks,
    }


# ── CSV ───────────────────────────────────────────────────────────────────────

# Header names of the common exporters, lower-cased.
COLUMNS = {
    "title": ("track name", "title", "track title", "song name", "song", "track", "name"),
    "artist": ("artist name(s)", "artist names", "artist name", "artist(s)", "artists", "artist"),
    "album": ("album name", "album title", "album"),
    "duration": ("duration (ms)", "track duration (ms)", "duration_ms", "duration", "length", "time"),
    "isrc": ("isrc",),
    "explicit": ("explicit",),
    "uri": ("track uri", "spotify uri", "spotify - id", "spotify id", "uri"),
    "playlist": ("playlist name", "playlist"),
}


def _decode(data):
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SourceError("The file is not a text CSV")


def _column_map(header):
    names = [h.strip().lower() for h in header]
    found = {}
    for field, aliases in COLUMNS.items():
        for alias in aliases:
            if alias in names:
                found[field] = names.index(alias)
                break
    return found


def _duration_ms(value):
    value = (value or "").strip()
    if not value:
        return 0
    if ":" in value:  # 3:43 or 1:02:10
        seconds = 0
        for part in value.split(":"):
            if not part.strip().isdigit():
                return 0
            seconds = seconds * 60 + int(part)
        return seconds * 1000
    try:
        number = float(value)
    except ValueError:
        return 0
    # Exporters give milliseconds; a small number can only be seconds.
    return int(number if number > 10_000 else number * 1000)


def _truthy(value):
    value = (value or "").strip().lower()
    if value in ("true", "yes", "1", "explicit", "y"):
        return True
    if value in ("false", "no", "0", "clean", "n"):
        return False
    return None


def _split_csv_artists(value):
    value = (value or "").strip()
    parts = re.split(r"\s*;\s*|\s*\|\s*", value) if re.search(r"[;|]", value) else [value]
    return [p for p in parts if p]


def _csv_key(row):
    if row["uri"]:
        tail = row["uri"].rsplit(":", 1)[-1].rsplit("/", 1)[-1]
        if re.fullmatch(r"[A-Za-z0-9]{10,40}", tail):
            return "sp:" + tail
    if row["isrc"]:
        return "isrc:" + row["isrc"]
    raw = "|".join([";".join(row["artists"]).lower(), row["title"].lower(), str(row["duration_ms"] // 1000)])
    return "h:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def read_csv(data, filename=""):
    if len(data) > MAX_CSV_BYTES:
        raise SourceError("The file is larger than 5 MB")
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration:
        raise SourceError("The file is empty")
    columns = _column_map(header)
    if "title" not in columns or "artist" not in columns:
        raise SourceError("No title and artist columns found. Export the playlist with Exportify, TuneMyMusic or Soundiiz.")

    def cell(values, field):
        index = columns.get(field)
        return values[index].strip() if index is not None and index < len(values) else ""

    tracks, playlist_name = [], ""
    for values in reader:
        if len(tracks) >= MAX_CSV_ROWS:
            raise SourceError(f"The file has more than {MAX_CSV_ROWS} tracks")
        title = cell(values, "title")
        artists = _split_csv_artists(cell(values, "artist"))
        if not title or not artists:
            continue
        playlist_name = playlist_name or cell(values, "playlist")
        tracks.append({
            "position": len(tracks) + 1,
            "title": title,
            "artists": artists,
            "album": cell(values, "album"),
            "duration_ms": _duration_ms(cell(values, "duration")),
            "isrc": cell(values, "isrc").upper().replace("-", ""),
            "explicit": _truthy(cell(values, "explicit")),
            "uri": cell(values, "uri"),
        })
    if not tracks:
        raise SourceError("The file has no track")

    for track in tracks:
        track["key"] = _csv_key(track)
        del track["uri"]
    _dedupe_keys(tracks)
    stem = re.sub(r"\.[^.]+$", "", filename or "").replace("_", " ").strip()
    return {"title": playlist_name or stem or "Imported playlist", "picture": "", "truncated": False, "tracks": tracks}


def _renumber(tracks):
    for position, track in enumerate(tracks, start=1):
        track["position"] = position
    _dedupe_keys(tracks)


def _dedupe_keys(tracks):
    # A playlist may hold the same song twice: each copy gets its own key.
    seen = {}
    for track in tracks:
        count = seen.get(track["key"], 0)
        seen[track["key"]] = count + 1
        if count:
            track["key"] = f"{track['key']}#{count + 1}"
