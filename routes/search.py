from flask import Blueprint, jsonify, request

from core.deezer import fetch_deezer_album_details, fetch_deezer_artist_details, search_deezer

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
