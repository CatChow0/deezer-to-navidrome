import time

import requests
from flask import Blueprint, jsonify, request

from core.deezer import fetch_deezer_album_details, fetch_deezer_artist_details, search_deezer
from core.library import library_snapshot
from core.matching import clean_title, find_best_match
from core.normalization import extract_version_flags, normalize_album_strict, normalize_text
from core.utils import similarity

search_bp = Blueprint("search", __name__)

@search_bp.get("/search")
def search_route():
    q = (request.args.get("q") or "").strip()
    search_type = (request.args.get("type") or "track").strip().lower()
    if search_type not in {"track", "album", "artist"}:
        return jsonify({"ok": False, "error": "invalid type"}), 400
    if not q:
        return jsonify({"ok": True, "results": []})
    try:
        results = search_deezer(q, search_type)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@search_bp.get("/search/album/<album_id>")
def search_album_detail_route(album_id):
    try:
        return jsonify({"ok": True, "album": fetch_deezer_album_details(album_id)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@search_bp.get("/search/artist/<artist_id>")
def search_artist_detail_route(artist_id):
    try:
        return jsonify({"ok": True, "artist": fetch_deezer_artist_details(artist_id)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@search_bp.post("/search/library-check")
def check_library_route():
    """Which search results are already in the library.

    Body: {"items": [{"key", "type": track|album|artist, "title", "artist", "album", "duration"}]}
    Tracks use the same matcher as playlist scans; albums count the distinct
    titles owned from that artist's album; artists count owned albums.
    """
    items = (request.get_json(silent=True) or {}).get("items") or []
    snap = library_snapshot()
    library, index = snap["library"], snap["index"]
    candidates_cache = {}

    def artist_entries(name):
        if name not in candidates_cache:
            candidates_cache[name] = index.artist_candidates(name) if name else {}
        return candidates_cache[name]

    def album_of(entry):
        return normalize_album_strict(entry.get("tag_album") or "") or entry.get("album_dir_norm") or ""

    results = {}
    for item in items[:100]:
        key = str(item.get("key") or "")
        kind = item.get("type")
        if kind == "track":
            title, artist, album = item.get("title") or "", item.get("artist") or "", item.get("album") or ""
            track = {
                "title": title,
                "artist": artist,
                "album": album,
                "duration": item.get("duration"),
                "norm_title": normalize_text(title),
                "norm_artist": normalize_text(artist),
                "norm_album": normalize_text(album),
                "version_flags": extract_version_flags(title, artist),
            }
            match = find_best_match(track, library, index) if title else None
            results[key] = {"owned": bool(match)}
        elif kind == "album":
            wanted = normalize_album_strict(item.get("title") or "")
            titles = set()
            for i in artist_entries(item.get("artist") or ""):
                entry = library[i]
                if wanted and similarity(wanted, album_of(entry)) >= 0.9:
                    titles.add(clean_title(entry.get("norm_tag_title") or entry.get("stem_norm") or ""))
            results[key] = {"owned_count": len(titles)}
        elif kind == "artist":
            entries = [library[i] for i, score in artist_entries(item.get("title") or "").items() if score >= 0.95]
            albums = {album_of(e) for e in entries} - {""}
            results[key] = {"albums_owned": len(albums), "tracks_owned": len(entries)}

    return jsonify({"ok": True, "results": results})


# Preview URLs carry an expiring token, so they are fetched when a track is
# played and kept only for a short while.
_PREVIEW_TTL = 20 * 60
_previews = {}


@search_bp.get("/api/preview/<track_id>")
def preview_route(track_id):
    if not track_id.isdigit():
        return jsonify({"ok": False, "error": "Invalid track"}), 400
    cached = _previews.get(track_id)
    if cached and time.time() - cached[0] < _PREVIEW_TTL:
        return jsonify({"ok": True, **cached[1]})
    try:
        data = requests.get(f"https://api.deezer.com/track/{track_id}", timeout=15).json()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Deezer did not answer: {e}"}), 502
    if "error" in data:
        return jsonify({"ok": False, "error": "This track is not on Deezer anymore"}), 404
    track = {
        "id": str(data.get("id")),
        "title": data.get("title") or "",
        "artist": (data.get("artist") or {}).get("name") or "",
        "album": (data.get("album") or {}).get("title") or "",
        "cover": (data.get("album") or {}).get("cover_medium") or "",
        "preview": data.get("preview") or "",
        "link": data.get("link") or f"https://www.deezer.com/track/{track_id}",
    }
    if len(_previews) > 500:
        _previews.clear()
    _previews[track_id] = (time.time(), track)
    return jsonify({"ok": True, **track})
