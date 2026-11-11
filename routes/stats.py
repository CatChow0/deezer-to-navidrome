from contextlib import closing

from flask import Blueprint, g, jsonify, request, send_file, session

from core import account_context, nd_accounts, stats_covers, stats_db, stats_enrich, stats_files, stats_import, stats_ingest, stats_queries
from core.stats_queries import BadPeriod
from routes.playlists import render_app

stats_bp = Blueprint("stats", __name__)

# Where Navidrome reaches this app when both run in the same compose file.
BASE_URL_HINT = "http://deezer-to-navidrome:8080/apis/listenbrainz/1/"
# Anyone with the address can try tokens (routes/listenbrainz.py): a short
# one would be guessed.
MIN_PASTED_TOKEN = 16
MAX_ID = 2 ** 63 - 1
COVER_MAX_AGE = 365 * 86400
AUDIO_TYPES = {
    ".flac": "audio/flac", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav",
}


def _account():
    """The profile whose history this request reads: the one an address names
    (a cover or a track keeps the page it belongs to), else this browser's."""
    asked = request.args.get("a")
    if asked and asked in account_context.own_profiles(g.get("user")):
        return asked
    return account_context.resolve(request, session)


@stats_bp.errorhandler(BadPeriod)
def bad_period(error):
    return jsonify({"ok": False, "error": str(error)}), 400


@stats_bp.get("/stats")
def stats_view():
    return render_app("stats")


@stats_bp.get("/stats/cover/<any(track, album, artist):kind>/<int:item_id>")
def cover(kind, item_id):
    found = stats_covers.cover_for(_account(), kind, item_id) if item_id <= MAX_ID else None
    if found is None:
        response = jsonify({"ok": False, "error": "No cover"})
        response.status_code = 404
        response.headers["Cache-Control"] = "no-store"
        return response
    response = send_file(found, mimetype="image/jpeg", conditional=True, etag=True)
    # Sign-in only: never for a shared proxy. Without a version the browser must ask.
    response.headers["Cache-Control"] = f"private, max-age={COVER_MAX_AGE}" if request.args.get("v") else "private, no-cache"
    return response


@stats_bp.get("/stats/audio/<int:track_id>")
def audio(track_id):
    found = None
    if track_id <= MAX_ID:
        with closing(stats_db.connect(_account())) as conn:
            row = conn.execute("SELECT key, file_path FROM tracks WHERE id = ?", (track_id,)).fetchone()
        found = stats_files.local_file(row) if row else None
    if found is None or found.suffix.casefold() not in AUDIO_TYPES:
        return jsonify({"ok": False, "error": "No file for this track"}), 404
    return send_file(found, mimetype=AUDIO_TYPES.get(found.suffix.casefold()), conditional=True, max_age=0)


@stats_bp.get("/api/stats/recaps")
def recaps():
    return jsonify(stats_queries.recap_index(_account(), request.args.get("tz")))


@stats_bp.get("/api/stats/overview")
def overview():
    args = request.args
    return jsonify(stats_queries.overview(_account(), args.get("period", ""), args.get("key", ""), args.get("tz")))


@stats_bp.get("/api/stats/recap")
def recap():
    args = request.args
    return jsonify(stats_queries.recap(_account(), args.get("type", ""), args.get("key", ""), args.get("tz")))


@stats_bp.get("/api/stats/<any(artist, album, track):kind>/<int:entity_id>")
def entity(kind, entity_id):
    data = stats_queries.entity(_account(), kind, entity_id, request.args.get("tz")) if entity_id <= MAX_ID else None
    if data is None:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(data)


@stats_bp.get("/api/stats/plays")
def plays():
    return jsonify(stats_queries.search_plays(_account(), request.args.get("q", ""), request.args.get("page", 1, type=int), per_page=25))


@stats_bp.get("/api/stats/status")
def status():
    account = _account()
    profile = nd_accounts.get(account) or {}
    with closing(stats_db.connect(account)) as conn:
        count = stats_db.play_count(conn)
        last_play = conn.execute("SELECT MAX(listened_at) FROM plays").fetchone()[0]
        last_import = stats_db.get_meta(conn, "last_import")
        enrich = stats_enrich.progress(conn)
    return jsonify({
        "account": {"id": account, "label": profile.get("label") or account, "username": profile.get("username") or "",
                    "several": len(nd_accounts.list_accounts()) > 1},
        "plays": count,
        "last_play_at": last_play,
        "token": stats_ingest.scrobble_token(account),
        "token_from_env": stats_ingest.token_from_env(account),
        "token_env": stats_ingest.token_env_name(account),
        "base_url_hint": BASE_URL_HINT,
        "sources": stats_import.source_status(account),
        "last_import": last_import,
        "enrich": enrich,
        "import_running": stats_import.import_running(),
    })


@stats_bp.post("/api/stats/import")
def start_import():
    body = request.get_json(silent=True)
    mode = body.get("mode") if isinstance(body, dict) else None
    if mode not in ("merge", "clean"):
        return jsonify({"ok": False, "error": "Choose merge or clean"}), 400
    try:
        task_id = stats_import.start_import_task(_account(), mode)
    except stats_import.ImportRefused as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True, "task_id": task_id}), 202


@stats_bp.post("/api/stats/import/preview")
def preview_import():
    if stats_import.import_running():
        return jsonify({"ok": False, "error": "A rebuild is already running."}), 409
    try:
        return jsonify({"ok": True, **stats_import.preview_clean(_account())})
    except stats_import.ImportRefused as e:
        return jsonify({"ok": False, "error": str(e)}), 409


def _env_token_refusal(account):
    name = stats_ingest.token_env_name(account)
    return jsonify({"ok": False, "error": f"This token is set by {name}: change it there."}), 409


@stats_bp.post("/api/stats/token")
def make_token():
    """The token of this browser's profile."""
    account = _account()
    if stats_ingest.token_from_env(account):
        return _env_token_refusal(account)
    body = request.get_json(silent=True)
    pasted = str(body.get("token") or "").strip() if isinstance(body, dict) else ""
    if pasted:
        if len(pasted) < MIN_PASTED_TOKEN or any(c.isspace() for c in pasted):
            return jsonify({"ok": False, "error": f"Use at least {MIN_PASTED_TOKEN} characters, without spaces."}), 400
        try:
            stats_ingest.set_scrobble_token(account, pasted)
        except stats_ingest.TokenTaken as e:
            return jsonify({"ok": False, "error": str(e)}), 409
        return jsonify({"ok": True, "token": pasted})
    return jsonify({"ok": True, "token": stats_ingest.new_scrobble_token(account)})


@stats_bp.delete("/api/stats/token")
def delete_token():
    account = _account()
    if stats_ingest.token_from_env(account):
        return _env_token_refusal(account)
    stats_ingest.forget_token(account)
    return jsonify({"ok": True})
