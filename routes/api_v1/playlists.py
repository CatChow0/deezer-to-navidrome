"""The playlists of the profile: the dashboard's list, adding one (a Deezer or
Spotify link, a CSV file), its tracks and matches, where it goes in Navidrome,
its scans and downloads, and the playlists its user made in Navidrome."""
import requests
from flask import request, session

from core import account_context
from core.config import get_preview_state
from core.deezer import load_playlists
from routes import navidrome_playlists as made_in_navidrome
from routes import playlists as web
from routes import system
from routes.api_v1 import COVERED, api_v1_bp, body, error, expose, ok, replaces


def _profile():
    return account_context.resolve(request, session)


def _tile(playlist) -> dict:
    """A playlist as the dashboard shows it, with how far its matching got."""
    state = get_preview_state(playlist["id"]) or {}
    rows = state.get("rows") if isinstance(state.get("rows"), list) else None
    return {
        "id": playlist["id"],
        "title": playlist.get("title") or "",
        # The Deezer title, when its user renamed it in Navidrome.
        "deezer_title": playlist.get("deezer_title") or "",
        "kind": playlist.get("kind") or "",
        "source": playlist.get("source") or "",
        "subtitle": playlist.get("subtitle") or "",
        "cover": f"/api/v1/covers/{playlist['cover_cached']}" if playlist.get("cover_cached") else "",
        "accounts": playlist.get("accounts") or [],
        "automation": {
            "scan": bool(playlist.get("auto_scan_enabled")),
            "interval_minutes": playlist.get("auto_scan_interval_minutes") or 60,
            "download": bool(playlist.get("auto_download_after_scan")),
        },
        "tracks": None if rows is None else {
            "total": len(rows), "matched": state.get("matched_count"),
            "unmatched": state.get("unmatched_count"), "unchecked": state.get("unchecked_count"),
        },
    }


def _made_there(playlist, profile) -> dict:
    return {
        "account": profile,
        "id": playlist["navidrome_id"],
        "name": playlist.get("name") or "",
        "song_count": playlist.get("song_count") or 0,
        "duration": playlist.get("duration") or 0,
        "cover": f"/api/v1/navidrome/cover/{profile}/{playlist['cover_art']}" if playlist.get("cover_art") else "",
    }


@api_v1_bp.get("/playlists")
@replaces(web.home)
def playlists_list():
    profile = _profile()
    playlists, made_there = web.dashboard_playlists(profile)
    return ok({"profile": profile, "playlists": [_tile(p) for p in playlists],
               "navidrome": [_made_there(p, profile) for p in made_there]}, cache=True)


@api_v1_bp.post("/playlists")
@replaces(web.add_playlist)
def playlists_add():
    link = str(body().get("link") or "").strip()
    if not link:
        return error("invalid", "Send the playlist's link or ID as link.", 400)
    try:
        result = web.add_playlist_for(link, _profile())
    except web.PlaylistError as e:
        return error("invalid", str(e), 400)
    except requests.RequestException as e:
        return error("upstream_error", f"Deezer did not answer: {e}", 502)
    result.pop("open", None)
    return ok(result, status=201 if result["added"] else 200)


@api_v1_bp.post("/playlists/import")
@replaces(web.import_csv_playlist)
def playlists_import():
    upload = request.files.get("csv_file")
    if upload is None or not upload.filename:
        return error("invalid", "Send the CSV file as csv_file, in multipart/form-data.", 400)
    try:
        result = web.import_csv_for(upload.filename, upload.read(web.MAX_CSV_BYTES + 1), _profile())
    except web.PlaylistError as e:
        return error("invalid", str(e), 400)
    return ok(result, status=201)


@api_v1_bp.delete("/playlists/<playlist_id>")
@replaces(web.delete_playlist)
def playlists_delete(playlist_id):
    """Off this profile; deleted when no other profile has it."""
    if not any(p["id"] == playlist_id for p in load_playlists()):
        return error("not_found", "No such playlist.", 404)
    try:
        return ok(web.delete_playlist_for(playlist_id, _profile()))
    except web.PlaylistError as e:
        return error("not_found", str(e), 404)


expose("/playlists/<playlist_id>/tracks", web.playlist_preview_route, name="playlist_tracks")
expose("/playlists/<playlist_id>/navidrome", web.playlist_navidrome_route, name="playlist_navidrome")
expose("/playlists/<playlist_id>/accounts", web.playlist_accounts_route, ("PUT",), name="playlist_accounts")
expose("/playlists/<playlist_id>/automation", web.update_playlist_automation, ("PUT",), name="playlist_automation")
expose("/playlists/<playlist_id>/scan", web.convert_playlist_start, ("POST",), name="playlist_scan")
# The web's older, blocking scan: the task above does the same.
COVERED.add(web.convert_playlist_route)
expose("/playlists/<playlist_id>/download-missing", web.download_missing_start, ("POST",), name="playlist_download_missing")
expose("/playlists/<playlist_id>/match", web.manual_match_route, ("POST",), name="playlist_match")
expose("/playlists/<playlist_id>/source-match", web.source_match_route, ("POST",), name="playlist_source_match")
expose("/playlists/<playlist_id>/publish", web.publish_now_route, ("POST",), name="playlist_publish")
expose("/covers/<path:filename>", system.serve_cover, name="covers")

expose("/navidrome/playlists/<account_id>/<navidrome_id>", made_in_navidrome.playlist, name="navidrome_playlist")
expose("/navidrome/cover/<account_id>/<path:cover_id>", made_in_navidrome.cover, name="navidrome_cover")
