"""Matching a Deezer track against the local library.

The artist is checked first: the Deezer main artist must match one of the
file's artists (collaborations are split, a leading "the" is ignored). That
check also picks the candidates, so only files from matching artists get their
title compared. A title must then be close, or near-close with a matching
duration. Version flags (live, remix, radio edit…) only change the ranking.
"""
import re

from core.normalization import normalize_text
from core.utils import similarity

ARTIST_MIN = 0.85
TITLE_MIN = 0.90
TITLE_MIN_WITH_DURATION = 0.80
DURATION_CLOSE = 3.0

_ARTIST_SPLIT = re.compile(
    r"\s*(?:,|;|/|\+|&|\bfeat\.?|\bft\.?|\bfeaturing\b|\bwith\b|\bx\b|\bvs\.?)\s*",
    re.IGNORECASE,
)
_LEADING_THE = re.compile(r"^the\s+")
_TRAILING_FEAT = re.compile(r"\s+feat\s+.*$")
_LEADING_TRACK_NO = re.compile(r"^\d{1,3}\s+")


def artist_keys(raw: str) -> set[str]:
    """Every way an artist credit can be referred to: the full credit and each
    collaborator, normalized, without a leading "the"."""
    keys = set()
    if not raw:
        return keys
    for part in [raw, *_ARTIST_SPLIT.split(raw)]:
        key = _LEADING_THE.sub("", normalize_text(part))
        if key:
            keys.add(key)
    return keys


def clean_title(norm_title: str) -> str:
    return _TRAILING_FEAT.sub("", norm_title or "").strip()


def _entry_artist_keys(entry) -> set[str]:
    keys = artist_keys(entry.get("tag_artist") or "") | artist_keys(entry.get("parsed_artist") or "")
    if entry.get("artist_dir_norm"):
        keys.add(_LEADING_THE.sub("", entry["artist_dir_norm"]))
    return keys


def _entry_titles(entry) -> list[str]:
    titles = [entry.get(k) for k in ("norm_tag_title", "norm_parsed_title", "norm_parsed_track_title")]
    titles = [clean_title(t) for t in titles if t]
    if not titles and entry.get("stem_norm"):
        titles.append(clean_title(_LEADING_TRACK_NO.sub("", entry["stem_norm"])))
    return titles


class LibraryIndex:
    """Artist → entries lookup, built once per library load."""

    def __init__(self, library: list):
        self.library = library
        self.by_artist: dict[str, list[int]] = {}
        self.titles: list[list[str]] = []
        for i, entry in enumerate(library):
            for key in _entry_artist_keys(entry):
                self.by_artist.setdefault(key, []).append(i)
            self.titles.append(_entry_titles(entry))
        self.artist_names = list(self.by_artist)

    def artist_candidates(self, raw_artist: str) -> dict[int, float]:
        """Entry index → best artist similarity, for entries whose artist matches."""
        found: dict[int, float] = {}
        for query in artist_keys(raw_artist):
            for name in self.artist_names:
                score = 1.0 if name == query else similarity(query, name)
                if score < ARTIST_MIN:
                    continue
                for i in self.by_artist[name]:
                    if score > found.get(i, 0.0):
                        found[i] = score
        return found


def build_title_index(library: list) -> LibraryIndex:
    """Kept under its historical name: callers build the index once per scan."""
    return LibraryIndex(library)


def _duration_diff(track, entry):
    td, ld = track.get("duration"), entry.get("duration")
    if not td or not ld:
        return None
    return abs(float(td) - float(ld))


def score_candidate(track, entry, artist_score: float, titles: list[str]):
    query = clean_title(track["norm_title"])
    title_score = max((1.0 if t == query else similarity(query, t) for t in titles), default=0.0)

    diff = _duration_diff(track, entry)
    close = diff is not None and diff <= DURATION_CLOSE
    if title_score < TITLE_MIN and not (title_score >= TITLE_MIN_WITH_DURATION and close):
        return None

    album_score = max(
        (similarity(track["norm_album"], a) for a in (entry.get("norm_tag_album"), entry.get("album_dir_norm")) if a),
        default=0.0,
    )

    score = title_score * 0.6 + artist_score * 0.25 + album_score * 0.05
    if diff is not None:
        score += 0.1 if diff <= 2 else 0.06 if diff <= 5 else 0.0 if diff <= 20 else -0.05

    track_flags = set(track.get("version_flags") or [])
    entry_flags = set(entry.get("version_flags") or [])
    if track_flags == entry_flags:
        score += 0.05 if track_flags else 0.0
    elif (track_flags ^ entry_flags) - {"remaster"}:
        score -= 0.15

    return {
        "score": round(score, 4),
        "title_score": round(title_score, 4),
        "artist_score": round(artist_score, 4),
        "album_score": round(album_score, 4),
    }


def find_best_match(track, library, title_index=None):
    index = title_index if isinstance(title_index, LibraryIndex) else LibraryIndex(library)

    if track.get("artist"):
        candidates = index.artist_candidates(track["artist"])
    else:
        # No artist on the Deezer side: fall back to comparing every title.
        candidates = {i: 0.0 for i in range(len(index.library))}

    best = None
    for i, artist_score in candidates.items():
        entry = index.library[i]
        scored = score_candidate(track, entry, artist_score, index.titles[i])
        if scored and (best is None or scored["score"] > best["score"]):
            best = {"entry": entry, **scored}
    return best
