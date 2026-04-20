import re
from pathlib import Path

from mutagen import File as MutagenFile

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wv", ".mp4"}

try:
    from rapidfuzz.distance import Indel as _Indel
    def similarity(a: str, b: str) -> float:
        return _Indel.normalized_similarity(a, b) if a and b else 0.0
except ImportError:
    from difflib import SequenceMatcher
    def similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a or "", b or "").ratio() if a and b else 0.0


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    return re.sub(r"\s+", " ", name).strip()


def extract_playlist_id(text: str):
    text = (text or "").strip()
    if text.isdigit():
        return text
    m = re.search(r"/playlist/(\d+)", text)
    return m.group(1) if m else None


def safe_get_first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def read_tags(path: Path):
    artist = ""
    title = ""
    album = ""
    duration = None
    try:
        audio = MutagenFile(path)
        if audio is not None:
            if getattr(audio, "info", None) and getattr(audio.info, "length", None):
                duration = float(audio.info.length)
            tags = getattr(audio, "tags", {}) or {}
            if path.suffix.lower() == ".mp3":
                artist = str(safe_get_first(tags.get("TPE1", [""])))
                title = str(safe_get_first(tags.get("TIT2", [""])))
                album = str(safe_get_first(tags.get("TALB", [""])))
            else:
                artist = str(safe_get_first(tags.get("artist", [""])))
                title = str(safe_get_first(tags.get("title", [""])))
                album = str(safe_get_first(tags.get("album", [""])))
    except Exception:
        pass
    return {
        "artist": artist.strip(),
        "title": title.strip(),
        "album": album.strip(),
        "duration": duration,
    }


def get_file_signature(path: Path):
    st = path.stat()
    return st.st_mtime_ns, st.st_size
