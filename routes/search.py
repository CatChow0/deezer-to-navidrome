from flask import Blueprint, jsonify, request

from core.deezer import fetch_deezer_album_details, fetch_deezer_artist_details, search_deezer
from core.library import load_library_cache
from core.config import get_paths_from_config
from core.normalization import normalize_text

search_bp = Blueprint("search", __name__)

def _get_library_index():
    """Charge le cache de la bibliothèque et retourne un index normalisé."""
    try:
        _, _, library_cache_file, _ = get_paths_from_config()
        library = load_library_cache(library_cache_file)

        # Index par titre normalisé (lowercase)
        tracks_index = {}
        albums_index = {}
        artists_index = {}

        for entry in library:
            norm_title = normalize_text(entry.get("tag_title") or entry.get("parsed_track_title") or "")
            norm_artist = normalize_text(entry.get("tag_artist") or entry.get("parsed_artist") or "")
            norm_album = normalize_text(entry.get("tag_album") or entry.get("album_dir_norm") or "")

            # Index tracks
            if norm_title:
                key = f"{norm_artist}:{norm_title}"
                tracks_index[key] = entry

            # Index albums par nom d'album + artiste
            if norm_album:
                key = f"{norm_artist}:{norm_album}"
                if key not in albums_index:
                    albums_index[key] = []
                albums_index[key].append(entry)

            # Index artistes
            if norm_artist:
                if norm_artist not in artists_index:
                    artists_index[norm_artist] = {"albums": set(), "tracks": []}
                if norm_album:
                    artists_index[norm_artist]["albums"].add(norm_album)
                artists_index[norm_artist]["tracks"].append(entry)

        return tracks_index, albums_index, artists_index
    except Exception:
        return {}, {}, {}


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


@search_bp.get("/search/library-check")
def check_library_route():
    """Vérifie quels éléments de la recherche existent déjà dans la bibliothèque.

    Query params:
        - type: track|album|artist
        - ids: liste d'IDs séparés par des virgules
        - artist: nom de l'artiste (optionnel, pour meilleure correspondance)
    """
    q_type = request.args.get("type", "track").lower()
    ids_str = request.args.get("ids", "")
    artist_name = request.args.get("artist", "")

    if not ids_str:
        return jsonify({"ok": True, "results": {}})

    ids = [i.strip() for i in ids_str.split(",") if i.strip()]
    tracks_index, albums_index, artists_index = _get_library_index()

    results = {}

    if q_type == "track":
        # Format: track_id -> { owned: bool, artist_match: bool }
        for track_id in ids:
            # On cherche par titre + artiste
            key_base = f":{normalize_text(track_id)}"  # Fallback par ID/titre
            owned = False
            artist_match = False

            if artist_name:
                norm_artist = normalize_text(artist_name)
                norm_title = normalize_text(track_id)
                search_key = f"{norm_artist}:{norm_title}"
                if search_key in tracks_index:
                    owned = True
                    artist_match = True
                else:
                    # Cherche juste par titre
                    for key in tracks_index:
                        if key.endswith(f":{norm_title}"):
                            owned = True
                            if key.startswith(f"{norm_artist}:"):
                                artist_match = True
                            break
            else:
                # Cherche juste par titre
                norm_title = normalize_text(track_id)
                for key in tracks_index:
                    if key.endswith(f":{norm_title}"):
                        owned = True
                        break

            results[track_id] = {"owned": owned, "artist_match": artist_match}

    elif q_type == "album":
        # Format: album_id -> { owned_count: int, total_tracks: int, album_match: bool }
        for album_id in ids:
            owned_count = 0
            album_match = False

            if artist_name:
                norm_artist = normalize_text(artist_name)
                norm_album = normalize_text(album_id)
                search_key = f"{norm_artist}:{norm_album}"
                if search_key in albums_index:
                    owned_count = len(albums_index[search_key])
                    album_match = True
                else:
                    # Cherche juste par nom d'album
                    for key in albums_index:
                        if key.endswith(f":{norm_album}"):
                            owned_count = len(albums_index[key])
                            break
            else:
                norm_album = normalize_text(album_id)
                for key in albums_index:
                    if key.endswith(f":{norm_album}"):
                        owned_count = len(albums_index[key])
                        break

            results[album_id] = {
                "owned_count": owned_count,
                "album_match": album_match
            }

    elif q_type == "artist":
        # Format: artist_id -> { albums_owned: int, total_albums: int }
        for artist_id in ids:
            norm_artist = normalize_text(artist_id)
            artist_data = artists_index.get(norm_artist, {"albums": set(), "tracks": []})
            results[artist_id] = {
                "albums_owned": len(artist_data.get("albums", set())),
                "tracks_owned": len(artist_data.get("tracks", []))
            }

    return jsonify({"ok": True, "results": results})
