from contextlib import closing

from flask import Blueprint, jsonify, request

from core import stats_db, stats_enrich, stats_import, stats_ingest, stats_queries
from core.stats_queries import BadPeriod
from routes.playlists import render_app

stats_bp = Blueprint("stats", __name__)

# Where Navidrome reaches this app when both run in the same compose file.
BASE_URL_HINT = "http://deezer-to-navidrome:8080/apis/listenbrainz/1/"
MIN_PASTED_TOKEN = 8


@stats_bp.errorhandler(BadPeriod)
def bad_period(error):
    return jsonify({"ok": False, "error": str(error)}), 400


@stats_bp.get("/stats")
def stats_view():
    return render_app("stats")


@stats_bp.get("/api/stats/recaps")
def recaps():
    return jsonify(stats_queries.recap_index(request.args.get("tz")))


@stats_bp.get("/api/stats/overview")
def overview():
    args = request.args
    return jsonify(stats_queries.overview(args.get("period", ""), args.get("key", ""), args.get("tz")))


@stats_bp.get("/api/stats/recap")
def recap():
    args = request.args
    return jsonify(stats_queries.recap(args.get("type", ""), args.get("key", ""), args.get("tz")))


@stats_bp.get("/api/stats/<any(artist, album, track):kind>/<int:entity_id>")
def entity(kind, entity_id):
    data = stats_queries.entity(kind, entity_id, request.args.get("tz"))
    if data is None:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(data)


@stats_bp.get("/api/stats/plays")
def plays():
    return jsonify(stats_queries.search_plays(request.args.get("q", ""), request.args.get("page", 1, type=int)))


@stats_bp.get("/api/stats/status")
def status():
    with closing(stats_db.connect()) as conn:
        count = stats_db.play_count(conn)
        last_play = conn.execute("SELECT MAX(listened_at) FROM plays").fetchone()[0]
        last_import = stats_db.get_meta(conn, "last_import")
        enrich = stats_enrich.progress(conn)
    return jsonify({
        "plays": count,
        "last_play_at": last_play,
        "token": stats_ingest.scrobble_token(),
        "token_from_env": stats_ingest.token_from_env(),
        "base_url_hint": BASE_URL_HINT,
        "sources": stats_import.source_status(),
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
        task_id = stats_import.start_import_task(mode)
    except stats_import.ImportRefused as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True, "task_id": task_id}), 202


def _env_token_refusal():
    return jsonify({"ok": False, "error": "This token is set by SCROBBLE_TOKEN: change it there."}), 409


@stats_bp.post("/api/stats/token")
def make_token():
    if stats_ingest.token_from_env():
        return _env_token_refusal()
    body = request.get_json(silent=True)
    pasted = str(body.get("token") or "").strip() if isinstance(body, dict) else ""
    if pasted:
        if len(pasted) < MIN_PASTED_TOKEN or any(c.isspace() for c in pasted):
            return jsonify({"ok": False, "error": f"Use at least {MIN_PASTED_TOKEN} characters, without spaces."}), 400
        stats_ingest.set_scrobble_token(pasted)
        return jsonify({"ok": True, "token": pasted})
    return jsonify({"ok": True, "token": stats_ingest.new_scrobble_token()})


@stats_bp.delete("/api/stats/token")
def delete_token():
    if stats_ingest.token_from_env():
        return _env_token_refusal()
    stats_ingest.set_scrobble_token("")
    return jsonify({"ok": True})
