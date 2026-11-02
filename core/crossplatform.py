"""Playlists from other platforms (a Spotify link or a CSV export), matched to
Deezer tracks so they work like Deezer playlists: previews, downloads, scans
against the library and automation.

Each source track gets a "pick": the Deezer track used for it, with a status:
  isrc       found by its ISRC, certain
  auto       found by search with a high score
  uncertain  the best search result, used but flagged for review
  none       nothing close enough on Deezer
  manual     chosen by hand ("Find on Deezer"), possibly "not on Deezer";
             kept by every later sync
Tracks without a Deezer track get the ID "src:<key>": it is not a number, so
downloads and previews already leave them out.

The state lives in data/crossplatform.json (see core.config), apart from the
preview state that every scan rewrites.
"""
import re
import time
import unicodedata
import uuid

from core.config import get_crossplatform_state, modify_crossplatform_state, modify_preview_state
from core.matching import artist_keys, clean_title
from core.normalization import extract_version_flags, normalize_text
from core.utils import similarity
from core.xp_sources import SourceError, read_csv, read_spotify, spotify_playlist_id

XP_ID = re.compile(r"^xp-(spotify|csv)-([A-Za-z0-9_-]+)$")

SOURCE_NAMES = {"spotify": "Spotify", "csv": "CSV"}

AUTO_SCORE = 0.9
REVIEW_SCORE = 0.7
# Explicit and clean are judged on the track's flag, remaster is a minor change.
FLAGS_IGNORED = {"explicit", "clean"}

_FEAT = re.compile(r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s[^\)\]]*[\)\]]", re.I)
_ARTIST_CUT = re.compile(r"\s*(?:,|;|&|\bfeat\.?|\bft\.?|\bx\b)\s*", re.I)
# What follows the title: "(Herman Melville Mix)", "[Live]", " - 2004 Remaster".
_DECORATION = re.compile(r"[\(\[]([^\)\]]*)[\)\]]|\s-\s(.+)$")
# Words that do not make another recording.
_NEUTRAL_WORDS = {
    "feat", "ft", "featuring", "with", "from", "remaster", "remastered", "version",
    "the", "a", "an", "and", "of", "by", "digital", "mono", "stereo", "explicit", "clean",
}


def parse_xp_id(playlist_id):
    m = XP_ID.match(str(playlist_id))
    return (m.group(1), m.group(2)) if m else None


# ── Matching one source track to Deezer ───────────────────────────────────────

def _snapshot(item):
    album = item.get("album") or {}
    return {
        "title": item.get("title") or "",
        "artist": (item.get("artist") or {}).get("name") or "",
        "album": album.get("title") or "",
        "duration": int(item.get("duration") or 0) or None,
        "explicit": bool(item.get("explicit_lyrics")),
        "cover": album.get("cover_medium") or "",
    }


def _pick(item, status, score):
    return {
        "deezer_id": str(item["id"]) if item else None,
        "status": status,
        "score": score,
        "deezer": _snapshot(item) if item else None,
        "matched_at": int(time.time()),
    }


def _plain(text):
    """Lower case without accents, parentheses kept (normalize_text drops them)."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _words(text):
    return set(re.findall(r"[a-z0-9]+", _plain(text)))


def _decoration_words(title):
    words = set()
    for group in _DECORATION.findall(_FEAT.sub("", title or "")):
        words |= _words(" ".join(group))
    return {w for w in words if w not in _NEUTRAL_WORDS and not re.fullmatch(r"\d{4}", w) and len(w) > 1}


def _title_forms(title):
    """The title, and without Spotify's " - 2004 Remaster" style suffix."""
    base = _FEAT.sub("", title or "")
    forms = {clean_title(normalize_text(base))}
    if " - " in base:
        forms.add(clean_title(normalize_text(base.split(" - ")[0])))
    return {f for f in forms if f}


def score_candidate(src, item):
    """How well a Deezer search result fits a source track (about 0 to 1.1),
    or None when the artist or the title is clearly different."""
    keys = set().union(*(artist_keys(a) for a in src["artists"])) if src["artists"] else set()
    found = artist_keys((item.get("artist") or {}).get("name") or "")
    artist = max((1.0 if a == b else similarity(a, b) for a in keys for b in found), default=0.0)
    if artist < 0.85:
        return None

    got = clean_title(normalize_text(item.get("title") or ""))
    title = max((1.0 if wanted == got else similarity(wanted, got) for wanted in _title_forms(src["title"])), default=0.0)
    if title < 0.7:
        return None

    score = title * 0.6 + artist * 0.3
    if src.get("album"):
        score += 0.1 * similarity(normalize_text(src["album"]), normalize_text((item.get("album") or {}).get("title") or ""))
    else:
        score += 0.1 * title

    seconds = (src.get("duration_ms") or 0) / 1000
    if seconds and item.get("duration"):
        diff = abs(seconds - float(item["duration"]))
        score += 0.08 if diff <= 2 else 0.04 if diff <= 5 else 0.0 if diff <= 10 else -0.1 if diff <= 30 else -0.3

    # A remix, a live or a radio edit is a different recording.
    # Without the featured artists: the flags are found as substrings, and
    # "Don Toliver" would make a "live" version.
    src_flags = set(extract_version_flags(_FEAT.sub("", src["title"]))) - FLAGS_IGNORED
    got_flags = set(extract_version_flags(_FEAT.sub("", item.get("title") or ""), item.get("title_version") or "")) - FLAGS_IGNORED
    if src_flags != got_flags:
        # "Remastered" and "Original Album Version" are the same recording.
        score -= 0.08 if (src_flags ^ got_flags) <= {"remaster", "original"} else 0.3

    # Words added on either side ("Herman Melville Mix", "40th Anniversary")
    # name another recording more often than not.
    item_title = f"{item.get('title') or ''} ({item.get('title_version') or ''})"
    if _decoration_words(item_title) - _words(src["title"]):
        score -= 0.15
    if _decoration_words(src["title"]) - _words(item_title):
        score -= 0.1

    # Never trade an explicit track for its censored version (or back) silently.
    if src.get("explicit") is not None and bool(item.get("explicit_lyrics")) != src["explicit"]:
        score -= 0.3
    return round(score, 3)


def _queries(src):
    title = _FEAT.sub("", src["title"]).strip() or src["title"]
    artist = _ARTIST_CUT.split(src["artists"][0])[0].strip() if src["artists"] else ""
    queries = [f"{artist} {title}".strip()]
    if " - " in title:  # "Song - Remastered 2011": the plain title finds more
        queries.append(f"{artist} {title.split(' - ')[0]}".strip())
    queries.append(title)
    return list(dict.fromkeys(queries))


def match_track(src):
    """The pick for one source track: by ISRC first, else by search."""
    from core.deezer import _public_api

    if src.get("isrc"):
        try:
            item = _public_api(f"/track/isrc:{src['isrc']}")
            if item.get("id"):
                return _pick(item, "isrc", 1.0)
        except Exception:
            pass  # unknown ISRC: fall back to the search

    best, best_score, seen = None, None, set()
    for query in _queries(src):
        try:
            results = (_public_api("/search", {"q": query, "limit": 10}) or {}).get("data") or []
        except Exception:
            continue
        for item in results:
            if item.get("id") in seen or item.get("type", "track") != "track":
                continue
            seen.add(item.get("id"))
            score = score_candidate(src, item)
            if score is not None and (best_score is None or score > best_score):
                best, best_score = item, score
        if best_score is not None and best_score >= AUTO_SCORE:
            break

    if best is None or best_score < REVIEW_SCORE:
        return _pick(None, "none", best_score)
    return _pick(best, "auto" if best_score >= AUTO_SCORE else "uncertain", best_score)


def deezer_track(deezer_id):
    """A pick made by hand, from a Deezer track ID."""
    from core.deezer import _public_api

    try:
        item = _public_api(f"/track/{int(deezer_id)}")
    except RuntimeError:
        item = {}  # "no data": an ID Deezer does not know
    if not item.get("id"):
        raise ValueError("Deezer has no track with this ID")
    return _pick(item, "manual", None)


# ── Tracks as the playlist pipeline sees them ─────────────────────────────────

def track_id_of(key, pick):
    return int(pick["deezer_id"]) if pick and pick.get("deezer_id") else f"src:{key}"


def _to_track(src, pick):
    artists = ", ".join(src["artists"])
    if pick and pick.get("deezer_id"):
        d = pick["deezer"] or {}
        title, artist, album, duration = d.get("title") or src["title"], d.get("artist") or artists, d.get("album") or "", d.get("duration")
    else:
        title, artist, album = src["title"], artists, src.get("album") or ""
        duration = (src.get("duration_ms") or 0) // 1000 or None
    return {
        "position": src["position"],
        "track_id": track_id_of(src["key"], pick),
        "title": title,
        "artist": artist,
        "album": album,
        "duration": duration,
        "norm_title": normalize_text(title),
        "norm_artist": normalize_text(artist),
        "norm_album": normalize_text(album),
        "version_flags": extract_version_flags(title, artist),
        "xp": {
            "key": src["key"],
            "status": pick["status"] if pick else "pending",
            "score": pick.get("score") if pick else None,
            "on_deezer": bool(pick and pick.get("deezer_id")),
            "source_title": src["title"],
            "source_artist": artists,
            "source_duration": (src.get("duration_ms") or 0) // 1000 or None,
            "source_explicit": src.get("explicit"),
        },
    }


def xp_tracks(playlist_id):
    """The tracks of an imported playlist, from the saved picks (no network)."""
    state = get_crossplatform_state(playlist_id) or {}
    picks = state.get("picks") or {}
    return [_to_track(src, picks.get(src["key"])) for src in state.get("tracks") or []]


def track_for(playlist_id, key):
    return next((t for t in xp_tracks(playlist_id) if t["xp"]["key"] == key), None)


def summary(playlist_id):
    state = get_crossplatform_state(playlist_id) or {}
    picks = state.get("picks") or {}
    statuses = [(picks.get(t["key"]) or {}).get("status", "pending") for t in state.get("tracks") or []]
    on_deezer = sum(1 for t in state.get("tracks") or [] if (picks.get(t["key"]) or {}).get("deezer_id"))
    return {
        "source": state.get("source"),
        "source_name": SOURCE_NAMES.get(state.get("source"), "Other platform"),
        "source_url": state.get("source_url") or "",
        "truncated": bool(state.get("truncated")),
        "synced_at": state.get("synced_at"),
        "total": len(statuses),
        "on_deezer": on_deezer,
        "review": statuses.count("uncertain"),
        "not_found": len(statuses) - on_deezer - statuses.count("pending"),
        "pending": statuses.count("pending"),
    }


# ── Adding, syncing and picking by hand ───────────────────────────────────────

def _create(playlist_id, source, source_id, source_url, info):
    def change(old):
        return {
            "source": source,
            "source_id": source_id,
            "source_url": source_url,
            "title": info["title"],
            "picture": info["picture"],
            "truncated": info["truncated"],
            "synced_at": int(time.time()),
            "tracks": info["tracks"],
            "picks": (old or {}).get("picks") or {},
        }

    modify_crossplatform_state(playlist_id, change)


def _register(playlist_id, info, source):
    from core.deezer import cache_cover, load_playlists, save_playlists

    entry = {"id": playlist_id, "title": info["title"], "picture": info["picture"], "source": source}
    save_playlists([*load_playlists(), entry])
    cache_cover(entry)


def add_spotify(text):
    """Saves a Spotify playlist from its link. Returns (playlist_id, added)."""
    from core.deezer import load_playlists

    source_id = spotify_playlist_id(text)
    if not source_id:
        raise SourceError("This is not a Spotify playlist link")
    playlist_id = f"xp-spotify-{source_id}"
    if any(p["id"] == playlist_id for p in load_playlists()):
        return playlist_id, False
    info = read_spotify(source_id)
    if not info["tracks"]:
        raise SourceError("This Spotify playlist has no track")
    _create(playlist_id, "spotify", source_id, f"https://open.spotify.com/playlist/{source_id}", info)
    _register(playlist_id, info, "spotify")
    return playlist_id, True


def add_csv(filename, data):
    """Saves a playlist from a CSV export. Returns its ID."""
    info = read_csv(data, filename)
    playlist_id = f"xp-csv-{uuid.uuid4().hex[:12]}"
    _create(playlist_id, "csv", "", "", info)
    _register(playlist_id, info, "csv")
    return playlist_id


def _move_local_state(playlist_id, old_id, new_id):
    """A track's Deezer pick changed: its manual file choice ("Fix") follows it.
    The downloaded mark does not, since it was another Deezer track."""
    if str(old_id) == str(new_id):
        return

    def change(state):
        if not state:
            return state
        overrides = dict(state.get("overrides") or {})
        if str(old_id) in overrides and str(new_id) not in overrides:
            overrides[str(new_id)] = overrides.pop(str(old_id))
            state = {**state, "overrides": overrides}
        return state

    modify_preview_state(playlist_id, change)


def _store_pick(playlist_id, key, pick, keep_manual):
    """Saves a pick and returns the one it replaced."""
    replaced = {}

    def change(state):
        state = dict(state or {})
        picks = dict(state.get("picks") or {})
        old = picks.get(key)
        replaced["pick"] = old
        # A pick made by hand while a sync ran wins over the sync.
        if keep_manual and old and old.get("status") == "manual":
            return state
        picks[key] = pick
        state["picks"] = picks
        return state

    modify_crossplatform_state(playlist_id, change)
    return replaced.get("pick")


def resync(playlist_id, full=False, progress=None):
    """Reads the source again (Spotify only: a CSV is a snapshot), then matches
    the tracks that have no pick yet, or with `full` every track not picked by
    hand. `progress(done, total, track)` follows the matching."""
    state = get_crossplatform_state(playlist_id)
    if not state:
        raise LookupError("This imported playlist has no saved tracks")

    if state.get("source") == "spotify":
        try:
            info = read_spotify(state["source_id"])
        except SourceError:
            if not state.get("tracks"):
                raise
            info = None  # keep the last copy; the next sync tries again
        if info is not None:
            keys = {t["key"] for t in info["tracks"]}

            def change(old):
                old = dict(old or {})
                old.update({
                    "tracks": info["tracks"],
                    "truncated": info["truncated"],
                    "synced_at": int(time.time()),
                    "picks": {k: v for k, v in (old.get("picks") or {}).items() if k in keys},
                })
                return old

            state = modify_crossplatform_state(playlist_id, change)

    picks = state.get("picks") or {}
    todo = [
        t for t in state.get("tracks") or []
        if t["key"] not in picks or (full and picks[t["key"]].get("status") != "manual")
    ]
    for done, src in enumerate(todo, start=1):
        pick = match_track(src)
        old = _store_pick(playlist_id, src["key"], pick, keep_manual=True)
        if old and (old.get("status") != "manual"):
            _move_local_state(playlist_id, track_id_of(src["key"], old), track_id_of(src["key"], pick))
        if progress:
            progress(done, len(todo), track_for(playlist_id, src["key"]))
    return len(todo)


def set_pick(playlist_id, key, choice):
    """Picks the Deezer track of one source track by hand: a Deezer track ID,
    None for "not on Deezer", or "auto" to go back to the automatic match.
    Returns the track as the pipeline sees it."""
    state = get_crossplatform_state(playlist_id) or {}
    src = next((t for t in state.get("tracks") or [] if t["key"] == key), None)
    if src is None:
        raise LookupError("This track is not in the playlist any more")

    if choice == "auto":
        pick = match_track(src)
    elif choice is None:
        pick = _pick(None, "manual", None)
    else:
        pick = deezer_track(choice)

    old = _store_pick(playlist_id, key, pick, keep_manual=False)
    _move_local_state(playlist_id, track_id_of(key, old), track_id_of(key, pick))
    return track_for(playlist_id, key)
