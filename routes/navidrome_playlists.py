"""The playlists a Navidrome user made by hand, shown read-only: their cover and
their tracks, read from Navidrome as that user. A playlist of another user is
never shown, even to an account that is an admin in Navidrome."""
from flask import Blueprint, Response, jsonify

from core import crypto, nd_accounts, publish, subsonic

navidrome_playlists_bp = Blueprint("navidrome_playlists", __name__)


def _client(account_id):
    try:
        return publish._client(account_id)
    except (nd_accounts.AccountError, crypto.DecryptError):
        return None


@navidrome_playlists_bp.get("/navidrome/cover/<account_id>/<path:cover_id>")
def cover(account_id, cover_id):
    client = _client(account_id)
    if client is None:
        return Response(status=404)
    try:
        data, kind = client.binary("getCoverArt", id=cover_id, size=300)
    except subsonic.SubsonicError:
        return Response(status=404)
    if not kind.startswith("image/"):
        return Response(status=404)
    response = Response(data, mimetype=kind)
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@navidrome_playlists_bp.get("/api/navidrome/playlists/<account_id>/<navidrome_id>")
def playlist(account_id, navidrome_id):
    account = nd_accounts.get(account_id)
    client = _client(account_id)
    if account is None or client is None:
        return jsonify({"ok": False, "error": "This account cannot sign in to Navidrome"}), 404
    try:
        found = client.call("getPlaylist", id=navidrome_id).get("playlist") or {}
    except subsonic.SubsonicError as e:
        return jsonify({"ok": False, "error": e.message}), 404
    if str(found.get("owner") or "").lower() != account["username"].lower():
        return jsonify({"ok": False, "error": "Not found."}), 404
    entries = found.get("entry") or []
    entries = entries if isinstance(entries, list) else [entries]
    return jsonify({"ok": True, "playlist": {
        "id": found.get("id"), "name": found.get("name") or "", "owner": found.get("owner") or "",
        "comment": found.get("comment") or "", "song_count": int(found.get("songCount") or len(entries)),
        "duration": int(found.get("duration") or 0),
        "tracks": [{"title": e.get("title") or "", "artist": e.get("artist") or "", "album": e.get("album") or "",
                    "duration": int(e.get("duration") or 0)} for e in entries],
    }})
