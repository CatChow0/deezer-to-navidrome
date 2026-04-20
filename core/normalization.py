import re
import unicodedata
from pathlib import Path

VERSION_KEYWORDS = {
    "instrumental": ["instrumental", "instr"],
    "acapella": ["acapella", "a cappella"],
    "remix": ["remix", "rmx"],
    "live": ["live"],
    "demo": ["demo"],
    "session": ["session", "garage session", "studio session"],
    "radio_edit": ["radio edit", "radio mix", "radio version"],
    "extended": ["extended", "extended mix", "extended version"],
    "edit": ["club edit", "single edit", "album edit", "special edit"],
    "mono": ["mono"],
    "stereo": ["stereo"],
    "clean": ["clean version", "clean edit"],
    "explicit": ["explicit"],
    "original": ["original", "original version", "original mix"],
    "bonus": ["bonus", "bonus track"],
    "alt": ["alternate", "alt version", "alternative"],
    "remaster": ["remaster", "remastered"],
}

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _normalize_for_flags(s: str) -> str:
    """Light normalization that keeps parenthetical/bracket content so version
    keywords like 'live', 'remix', 'radio edit' can be detected from tags such
    as 'Feather (Live Version)' or 'Title [Radio Edit]'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"\bfeat\.?\b", " feat ", s)
    s = re.sub(r"\bft\.?\b", " feat ", s)
    s = re.sub(r"\bfeaturing\b", " feat ", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(
        r"\b(remaster(ed)?|radio edit|explicit|clean|mono|stereo|version)\b", " ", s
    )
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Pre-normalized needles and compiled patterns — computed once at module load.
# _normalize_for_flags keeps parenthetical content so keywords inside (...) are detectable.
# strip_version_tokens still uses normalize_text (strips parentheticals) because it works
# on already-normalized titles used for dedup grouping.
_VERSION_NEEDLES_NORM: list[tuple[str, str]] = [
    (key, needle_norm)
    for key, needles in VERSION_KEYWORDS.items()
    for needle_norm in (_normalize_for_flags(n) for n in needles)
    if needle_norm
]
# For strip_version_tokens: patterns based on fully-normalized needles (no parentheticals)
_VERSION_STRIP_PATTERNS: list[re.Pattern] = [
    re.compile(rf"\b{re.escape(normalize_text(n))}\b")
    for needles in VERSION_KEYWORDS.values()
    for n in needles
    if normalize_text(n)
]


def normalize_album_strict(s: str) -> str:
    s = normalize_text(s)
    s = re.sub(
        r"\b(deluxe|expanded|complete|anniversary|collector s edition|edition)\b",
        " ",
        s,
    )
    s = re.sub(r"\b(cd|disc|digital media)\s*\d+\b", " ", s)
    s = re.sub(r"\b\d{4}\b", " ", s)
    return normalize_spaces(s)


def extract_track_number_from_path(path: str):
    name = Path(path).stem
    m = re.search(r"(?:^|\D)(\d{1,2})(?:\D|$)", name)
    return int(m.group(1)) if m else None


def extract_version_flags(*values):
    # Use _normalize_for_flags so keywords inside parentheses are preserved.
    # e.g. "Feather (Live Version)" → "feather live version" → detects "live"
    raw = " ".join([v for v in values if v])
    normalized = _normalize_for_flags(raw)
    found = set()
    for key, needle_norm in _VERSION_NEEDLES_NORM:
        if needle_norm in normalized:
            found.add(key)
    return sorted(found)


def strip_version_tokens(title: str) -> str:
    s = normalize_text(title)
    for pattern in _VERSION_STRIP_PATTERNS:
        s = pattern.sub(" ", s)
    s = re.sub(r"\b(version|mix)\b", " ", s)
    return normalize_spaces(s)


def audio_extension_rank(path: str) -> int:
    ext = Path(path).suffix.lower()
    order = {
        ".flac": 100,
        ".wav": 95,
        ".wv": 92,
        ".m4a": 80,
        ".opus": 70,
        ".ogg": 65,
        ".mp3": 60,
        ".aac": 55,
        ".mp4": 50,
    }
    return order.get(ext, 0)


def compute_quality_score(entry):
    score = 0.0
    score += audio_extension_rank(entry.get("path", ""))
    score += min((entry.get("size") or 0) / 1024 / 1024, 200)
    if entry.get("tag_artist"):
        score += 6
    if entry.get("tag_title"):
        score += 6
    if entry.get("tag_album"):
        score += 4
    if entry.get("duration"):
        score += 3
    return round(score, 2)


def get_duration_bucket(duration, bucket_size=2):
    if duration is None:
        return None
    return int(float(duration) // bucket_size) * bucket_size


def enrich_library_entry_for_dedup(entry):
    title_source = (
        entry.get("tag_title")
        or entry.get("parsed_track_title")
        or entry.get("parsed_title")
        or Path(entry.get("path", "")).stem
    )
    album_source = entry.get("tag_album") or entry.get("album_dir_norm") or ""
    artist_source = (
        entry.get("tag_artist")
        or entry.get("parsed_artist")
        or entry.get("artist_dir_norm")
        or ""
    )

    version_flags = extract_version_flags(
        entry.get("tag_title", ""),
        entry.get("parsed_title", ""),
        entry.get("parsed_track_title", ""),
        Path(entry.get("path", "")).stem,
    )

    track_number = extract_track_number_from_path(entry.get("path", ""))
    base_title = strip_version_tokens(title_source)
    album_norm_strict = normalize_album_strict(album_source)
    artist_norm_strict = normalize_text(artist_source)

    enriched = dict(entry)
    enriched.update(
        {
            "base_title": base_title,
            "album_norm_strict": album_norm_strict,
            "artist_norm_strict": artist_norm_strict,
            "version_flags": version_flags,
            "track_number": track_number,
            "quality_score": compute_quality_score(entry),
        }
    )
    return enriched


def version_flags_match(a, b):
    sa = set(a or [])
    sb = set(b or [])
    return sa == sb


def duration_close(a, b, tolerance=2.0):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tolerance


def should_group_as_duplicates(a, b):
    if a.get("artist_norm_strict") and b.get("artist_norm_strict"):
        if a["artist_norm_strict"] != b["artist_norm_strict"]:
            return False, "different_artist"

    if a.get("base_title") != b.get("base_title"):
        return False, "different_base_title"

    if not version_flags_match(a.get("version_flags"), b.get("version_flags")):
        return False, "different_version_flags"

    a_album = a.get("album_norm_strict") or ""
    b_album = b.get("album_norm_strict") or ""
    if a_album and b_album and a_album != b_album:
        return False, "different_album"

    a_track = a.get("track_number")
    b_track = b.get("track_number")
    if a_album and b_album and a_album == b_album and a_track and b_track and a_track != b_track:
        return False, "different_track_number_same_album"

    if a.get("duration") is not None and b.get("duration") is not None:
        if not duration_close(a.get("duration"), b.get("duration"), tolerance=2.0):
            return False, "different_duration"

    return True, "strict_match"


def safe_dict(value):
    return value if isinstance(value, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def normalize_group_identity(identity):
    identity = safe_dict(identity)
    return {
        "artist": identity.get("artist") or "",
        "album": identity.get("album") or "",
        "base_title": identity.get("base_title") or "",
        "version_flags": safe_list(identity.get("version_flags")),
    }


def normalize_entry(entry):
    entry = safe_dict(entry)
    return {
        "path_str": entry.get("path_str") or entry.get("path") or "",
        "tag_artist": entry.get("tag_artist") or "",
        "tag_title": entry.get("tag_title") or "",
        "tag_album": entry.get("tag_album") or "",
        "parsed_artist": entry.get("parsed_artist") or "",
        "parsed_title": entry.get("parsed_title") or "",
        "parsed_track_title": entry.get("parsed_track_title") or "",
        "stem_norm": entry.get("stem_norm") or "",
        "album_dir_norm": entry.get("album_dir_norm") or "",
        "artist_dir_norm": entry.get("artist_dir_norm") or "",
        "track_number": entry.get("track_number"),
        "duration": entry.get("duration"),
        "quality_score": entry.get("quality_score", 0),
        "version_flags": safe_list(entry.get("version_flags")),
    }
