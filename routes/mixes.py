"""The generated playlists: which versions run, and the tracks in quarantine."""
import logging
import time

from flask import Blueprint, jsonify, request

from core import mix_builder, metadata_fix, mixes_db, stats_db, stats_import, trial

logger = logging.getLogger(__name__)

mixes_bp = Blueprint("mixes", __name__)


def _track(row, plays, now) -> dict:
    return {
        "id": row["deezer_id"],
        "artist": row["artist"],
        "title": row["title"],
        "album": row["album"],
        "plays": plays.get(row["deezer_id"], 0),
        "reason": row["reason"],
        "days_left": max(0, (row["trial_ends_at"] - now + 86399) // 86400),
        "trash_days_left": max(0, (row["state_at"] + trial.TRASH_DAYS * 86400 - now + 86399) // 86400),
    }


def _state(conn) -> dict:
    now = int(time.time())
    stats = stats_db.connect()
    try:
        plays = trial.plays_since_download(conn, stats)
    finally:
        stats.close()
    entries = mix_builder.library_entries()
    analysis = metadata_fix.status(conn, entries)
    analysis["running"] = metadata_fix.is_running()
    usage = trial.usage(conn, plays)
    return {
        "settings": mix_builder.load_settings(conn),
        "downloads_blocked": mix_builder.downloads_possible(),
        "analysis": analysis,
        "running": mix_builder.is_running(),
        "last_run": mixes_db.get_meta(conn, "last_run"),
        "navidrome_mounted": stats_import._navidrome_path().is_file(),
        "usage": usage,
        "on_trial": [_track(r, plays, now) for r in trial.listing(conn, trial.ON_TRIAL)],
        "pending": [_track(r, plays, now) for r in trial.listing(conn, trial.PENDING)],
        "trash": [_track(r, plays, now) for r in trial.listing(conn, trial.TRASH)],
    }


@mixes_bp.get("/api/mixes")
def state():
    conn = mixes_db.connect()
    try:
        return jsonify(_state(conn))
    finally:
        conn.close()


@mixes_bp.post("/api/mixes/settings")
def settings():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "Expected settings"}), 400
    conn = mixes_db.connect()
    try:
        toggles = {k: body.pop(k) for k in ("daily", "blend", "discover") if k in body}
        try:
            mix_builder.save_settings(conn, body)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Limits must be numbers"}), 400
        for name, enabled in toggles.items():
            if enabled and name != "daily" and mix_builder.downloads_possible():
                return jsonify({"ok": False, "error": mix_builder.downloads_possible()}), 400
            mix_builder.set_enabled(conn, name, bool(enabled))
        if any(toggles.values()):
            metadata_fix.start_background(mix_builder.library_entries)
        return jsonify({"ok": True, **_state(conn)})
    finally:
        conn.close()


@mixes_bp.post("/api/metadata/fix")
def fix_metadata():
    """Asked for once, it then also takes care of new files on its own."""
    from core.config import create_task

    if metadata_fix.is_running():
        return jsonify({"ok": False, "error": "Already running"}), 409
    conn = mixes_db.connect()
    try:
        mixes_db.set_meta(conn, "metadata_fix_on", True)
        mixes_db.set_meta(conn, "metadata_write_off", False)
    finally:
        conn.close()
    task_id = create_task("Fix missing metadata", kind="metadata")
    metadata_fix.start_background(mix_builder.library_entries, task_id=task_id)
    return jsonify({"ok": True, "task_id": task_id})


@mixes_bp.post("/api/metadata/undo")
def undo_metadata():
    from core.config import create_task

    if metadata_fix.is_running():
        return jsonify({"ok": False, "error": "Fix missing metadata is running: wait for it to finish"}), 409
    task_id = create_task("Undo metadata fix", kind="metadata")
    metadata_fix.start_undo(task_id)
    return jsonify({"ok": True, "task_id": task_id})


@mixes_bp.post("/api/mixes/generate")
def generate():
    if mix_builder.is_running():
        return jsonify({"ok": False, "error": "Your mixes are already being generated"}), 409
    conn = mixes_db.connect()
    try:
        current = mix_builder.load_settings(conn)
    finally:
        conn.close()
    versions = [v for v in ("daily", "blend", "discover") if current[v]]
    if not versions:
        return jsonify({"ok": False, "error": "Turn on at least one version first"}), 400
    return jsonify({"ok": True, "task_id": mix_builder.start_task(versions)})


def _update_trial_playlist(conn) -> None:
    """The decision is made and the file has moved: a playlist that cannot be
    written (an unmapped folder, say) must not make it look like a failure."""
    try:
        mix_builder.publish_trial_playlist(conn)
    except (OSError, ValueError) as e:
        logger.warning("Could not update the On trial playlist: %s", e)


def _decide(action, deezer_id):
    conn = mixes_db.connect()
    try:
        action(conn, deezer_id, int(time.time()))
        _update_trial_playlist(conn)
        return jsonify({"ok": True, **_state(conn)})
    except (trial.TrialError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@mixes_bp.post("/api/mixes/trial/<deezer_id>/keep")
def keep(deezer_id):
    return _decide(trial.keep, deezer_id)


@mixes_bp.post("/api/mixes/trial/<deezer_id>/remove")
def remove(deezer_id):
    return _decide(trial.remove, deezer_id)


@mixes_bp.post("/api/mixes/trial/<deezer_id>/restore")
def restore(deezer_id):
    return _decide(trial.restore, deezer_id)


@mixes_bp.post("/api/mixes/trial/remove-pending")
def remove_pending():
    conn = mixes_db.connect()
    try:
        removed = trial.remove_all_pending(conn, int(time.time()))
        _update_trial_playlist(conn)
        return jsonify({"ok": True, "removed": removed, **_state(conn)})
    finally:
        conn.close()
