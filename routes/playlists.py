import threading

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from core.config import (
    create_task,
    delete_playlist_cache,
    load_config,
    push_task_event,
    push_task_row_update,
    get_preview_state,
    whats_new_state,
)
from core import deezer_dl
from core import download_queue
from core.download_queue import enqueue_download
from core.deezer import (
    playlist_title,
    apply_manual_match,
    build_playlist_preview,
    cache_cover,
    convert_playlist,
    fetch_deezer_playlist_info,
    load_playlists,
    mark_preview_rows_downloaded,
    save_playlists,
)
from core.utils import extract_playlist_id
from core import scheduler

import time

playlists_bp = Blueprint("playlists", __name__)


def _log_dl(msg):
    print(f"[download-missing] {msg}", flush=True)


def render_app(view):
    """Dashboard and settings live on the same page; `view` picks the one shown first."""
    return render_template(
        "home.html",
        playlists=load_playlists(),
        config=load_config(),
        view=view,
        download_dir=deezer_dl.download_dir_status(),
        whats_new=whats_new_state(),
    )


@playlists_bp.get("/")
def home():
    return render_app("dashboard")


@playlists_bp.get("/releases")
def releases_view():
    return render_app("releases")


@playlists_bp.post("/playlist/add")
def add_playlist():
    value = request.form.get("playlist_input", "")
    pid = extract_playlist_id(value)
    if not pid:
        flash("Invalid ID or URL")
        return redirect(url_for("playlists.home"))

    playlists = load_playlists()
    if any(p["id"] == pid for p in playlists):
        flash("Playlist already saved")
        return redirect(url_for("playlists.home"))

    info = fetch_deezer_playlist_info(pid)
    playlists.append(info)
    save_playlists(playlists)
    cache_cover(info)
    flash("Playlist added")
    return redirect(url_for("playlists.home"))


@playlists_bp.post("/playlist/<playlist_id>/delete")
def delete_playlist(playlist_id):
    playlists = [p for p in load_playlists() if p["id"] != playlist_id]
    save_playlists(playlists)
    delete_playlist_cache(playlist_id)
    flash("Playlist deleted")
    return redirect(url_for("playlists.home"))


@playlists_bp.post("/playlist/<playlist_id>/convert")
def convert_playlist_route(playlist_id):
    try:
        result = convert_playlist(playlist_id)
        flash(
            f"Conversion done: {result['playlist_title']} ({result['matched']} matched, {result['unmatched']} missing)"
        )
    except Exception as e:
        flash(f"Conversion error: {e}")
    return redirect(url_for("playlists.home"))


@playlists_bp.post("/playlist/<playlist_id>/convert/start")
def convert_playlist_start(playlist_id):
    data = request.get_json(silent=True) or {}
    quick = data.get("mode") == "quick"

    task_id = create_task(
        f"{'Quick' if quick else 'Full'} scan: {playlist_title(playlist_id)}",
        kind="scan",
        playlist_id=playlist_id,
    )

    def on_progress(message=None, progress=None, stage=None, row_update=None):
        if row_update is not None:
            push_task_row_update(task_id, row_update)
        if message is not None or progress is not None or stage is not None:
            push_task_event(task_id, message=message, progress=progress, stage=stage)

    def runner():
        try:
            mode_label = "Quick scan" if quick else "Full scan"
            push_task_event(task_id, f"{mode_label}: initializing", stage="init", progress=0)
            result = convert_playlist(playlist_id, progress_cb=on_progress, quick=quick)
            push_task_event(
                task_id,
                f"Conversion done: {result['playlist_title']} ({result['matched']} matched, {result['unmatched']} missing)",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, f"Conversion error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@playlists_bp.get("/playlist/<playlist_id>/preview")
def playlist_preview_route(playlist_id):
    try:
        data = build_playlist_preview(playlist_id)
        return jsonify({"ok": True, "playlist": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@playlists_bp.post("/playlist/<playlist_id>/automation")
def update_playlist_automation(playlist_id):
    data = request.get_json(silent=True) or {}
    playlists = load_playlists()
    pl = next((p for p in playlists if p["id"] == playlist_id), None)
    if not pl:
        return jsonify({"error": "Playlist not found"}), 404

    pl["auto_scan_enabled"] = bool(data.get("auto_scan_enabled"))
    pl["auto_scan_interval_minutes"] = max(1, int(data.get("auto_scan_interval_minutes") or 60))
    pl["auto_download_after_scan"] = bool(data.get("auto_download_after_scan"))

    save_playlists(playlists)
    scheduler.notify_playlist_updated(playlist_id, pl)

    sched_state = scheduler.get_status().get(playlist_id, {})
    return jsonify({
        "ok": True,
        "next_run_at": sched_state.get("next_run_at"),
        "last_run_at": sched_state.get("last_run_at"),
    })


@playlists_bp.post("/playlist/<playlist_id>/match")
def manual_match_route(playlist_id):
    data = request.get_json(silent=True) or {}
    track_id = str(data.get("track_id") or "").strip()
    if not track_id:
        return jsonify({"ok": False, "error": "track_id is required"}), 400
    try:
        row = apply_manual_match(playlist_id, track_id, str(data.get("mode") or ""), data.get("path"))
    except LookupError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "row": row})


@playlists_bp.post("/playlist/<playlist_id>/download-missing/start")
def download_missing_start(playlist_id: str):
    preview = get_preview_state(playlist_id)
    if not preview or not isinstance(preview.get("rows"), list):
        return jsonify({"error": "No preview found — run a conversion first"}), 400

    missing_rows = [
        row
        for row in preview["rows"]
        if row.get("matched") is False
        and row.get("track_id")
        and not row.get("downloaded")
    ]
    if not missing_rows:
        return jsonify({"error": "No missing tracks to download"}), 400

    if not deezer_dl.download_arl():
        return jsonify({"error": "No Deezer account connected. Add your ARL in Settings."}), 400

    task_id = create_task(f"Download missing: {playlist_title(playlist_id)}", kind="download-missing", playlist_id=playlist_id)

    def runner():
        total = len(missing_rows)
        pending_ids = {str(row["track_id"]).strip() for row in missing_rows if row.get("track_id") is not None}
        _log_dl(f"missing track ids: {sorted(pending_ids)}")
        success_ids = set()
        failed_ids = set()
        lock = threading.Lock()

        def on_track_done(_task, _result, error):
            track_id = str(_task.music_id)
            with lock:
                if error:
                    failed_ids.add(track_id)
                else:
                    success_ids.add(track_id)
                done = len(success_ids) + len(failed_ids)
            if not error:
                for row in mark_preview_rows_downloaded(playlist_id, {track_id}):
                    push_task_row_update(task_id, row)
            push_task_event(
                task_id,
                f"Downloaded {len(success_ids)}/{total}" + (f", {len(failed_ids)} failed" if failed_ids else ""),
                stage="download_missing",
                progress=round(done / total * 100),
            )

        try:
            push_task_event(task_id, "Starting download of missing tracks", stage="download_missing", progress=0)

            for row in missing_rows:
                track_id = str(row["track_id"]).strip()
                if not track_id.isdigit():
                    failed_ids.add(track_id)
                    pending_ids.discard(track_id)
                    continue
                _log_dl(f"queue download track_id={track_id}")
                try:
                    enqueue_download("track", track_id, on_done=on_track_done)
                except Exception as e:
                    # The queue should not refuse a download, but if it does the
                    # track must not be silently forgotten.
                    _log_dl(f"could not queue track_id={track_id}: {e}")
                    failed_ids.add(track_id)
                    pending_ids.discard(track_id)

            # The queue runs the downloads in the background; wait for them all.
            deadline = time.time() + 3600
            while pending_ids and time.time() < deadline:
                time.sleep(2)
                with lock:
                    finished = success_ids | failed_ids
                pending_ids -= finished

            if pending_ids:
                failed_ids.update(pending_ids)
                pending_ids.clear()

            push_task_event(
                task_id,
                f"Download complete: {len(success_ids)} succeeded, {len(failed_ids)} failed",
                stage="done",
                progress=100,
                done=True,
            )

        except Exception as e:
            push_task_event(task_id, f"Download error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id, "total": len(missing_rows)})
