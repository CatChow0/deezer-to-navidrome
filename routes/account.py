import threading

from flask import Blueprint, jsonify, request

from core.config import create_task, load_secret, push_task_event, save_secret, secret_from_env
from core.deezer import follow_mix, load_playlists, mix_id
from core.deezer_account import DeezerAccountError, account_status, available_mixes, forget_session
from core.releases import load_prefs, load_releases, refresh_hours, refresh_lock, refresh_releases, set_muted

account_bp = Blueprint("account", __name__)


def _status():
    if not load_secret("deezer_arl"):
        return {"connected": False, "name": "", "error": None, "from_env": False}
    return {**account_status(), "from_env": secret_from_env("deezer_arl")}


@account_bp.get("/api/deezer/account")
def account_route():
    return jsonify({"ok": True, **_status()})


@account_bp.post("/api/deezer/account")
def connect_account_route():
    arl = str((request.get_json(silent=True) or {}).get("arl") or "").strip()
    if not arl:
        return jsonify({"ok": False, "error": "Paste the ARL value first"}), 400
    status = account_status(arl)
    if not status["connected"]:
        forget_session()
        return jsonify({"ok": False, "error": status["error"]}), 400
    save_secret("deezer_arl", arl)
    return jsonify({"ok": True, **_status()})


@account_bp.delete("/api/deezer/account")
def disconnect_account_route():
    save_secret("deezer_arl", None)
    forget_session()
    return jsonify({"ok": True, **_status()})


@account_bp.get("/api/deezer/mixes")
def mixes_route():
    try:
        found = available_mixes()
    except DeezerAccountError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    followed = {p["id"] for p in load_playlists()}
    for mix in found["mixes"]:
        mix["id"] = mix_id(mix["kind"], mix["source_id"])
        mix["followed"] = mix["id"] in followed
    for playlist in found["playlists"]:
        playlist["followed"] = playlist["id"] in followed
    return jsonify({"ok": True, **found})


@account_bp.post("/api/deezer/mixes/follow")
def follow_mix_route():
    data = request.get_json(silent=True) or {}
    kind, source_id = data.get("kind"), str(data.get("source_id") or "")
    if kind not in ("stl", "flow") or not source_id:
        return jsonify({"ok": False, "error": "Unknown mix"}), 400
    try:
        pid, added = follow_mix(kind, source_id, str(data.get("title") or "Mix"))
    except DeezerAccountError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "id": pid, "added": added})


@account_bp.get("/api/releases")
def releases_route():
    return jsonify({
        "ok": True,
        "connected": bool(load_secret("deezer_arl")),
        "refresh_hours": refresh_hours(),
        "muted": load_prefs()["muted"],
        **load_releases(),
    })


@account_bp.post("/api/releases/mute")
def mute_artist_route():
    data = request.get_json(silent=True) or {}
    artist_id = str(data.get("artist_id") or "")
    if not artist_id.isdigit():
        return jsonify({"ok": False, "error": "Unknown artist"}), 400
    prefs = set_muted(artist_id, str(data.get("name") or ""), bool(data.get("muted")))
    return jsonify({"ok": True, "muted": prefs["muted"]})


def start_release_refresh(title="Release feed refresh"):
    """Runs the refresh in the background unless one is already running; returns the task ID or None."""
    if not refresh_lock.acquire(blocking=False):
        return None
    task_id = create_task(title, kind="releases")

    def runner():
        try:
            feed = refresh_releases(
                progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                    task_id, message=message, progress=progress, stage=stage
                )
            )
            push_task_event(
                task_id,
                f"{len(feed['releases'])} releases from {feed['artists']} artists",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, f"Release feed failed: {e}", stage="error", done=True, error=True)
        finally:
            refresh_lock.release()

    threading.Thread(target=runner, daemon=True).start()
    return task_id


@account_bp.post("/api/releases/refresh")
def refresh_releases_route():
    if not load_secret("deezer_arl"):
        return jsonify({"ok": False, "error": "Connect your Deezer account in Settings first"}), 400
    task_id = start_release_refresh()
    if task_id is None:
        return jsonify({"ok": False, "error": "The release feed is already refreshing"}), 409
    return jsonify({"ok": True, "task_id": task_id})
