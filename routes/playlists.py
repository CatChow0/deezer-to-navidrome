import threading

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from core.config import (
    create_task,
    delete_playlist_cache,
    load_config,
    push_task_event,
    push_task_row_update,
    get_preview_state,
    TASKS,
)
from core.deezer import (
    build_playlist_preview,
    cache_cover,
    convert_playlist,
    extract_queue_state,
    extract_track_id_from_queue_item,
    fetch_deezer_playlist_info,
    load_playlists,
    mark_preview_rows_downloaded,
    parse_queue_items,
    save_playlists,
)
from core.utils import extract_playlist_id
from core import scheduler

import requests
import time

playlists_bp = Blueprint("playlists", __name__)


def _log_dl(msg):
    print(f"[download-missing] {msg}", flush=True)


@playlists_bp.get("/")
def home():
    playlists = load_playlists()
    return render_template("home.html", playlists=playlists)


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

    task_id = create_task()

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

    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url not configured"}), 400

    task_id = create_task()

    def runner():
        total = len(missing_rows)
        pending_ids = {str(row["track_id"]).strip() for row in missing_rows if row.get("track_id") is not None}
        _log_dl(f"missing track ids: {sorted(pending_ids)}")
        success_ids = set()
        failed_ids = set()

        try:
            push_task_event(task_id, "Starting download of missing tracks", stage="download_missing", progress=0)

            for row in missing_rows:
                track_id = str(row["track_id"]).strip()
                _log_dl(f"launch download track_id={track_id}")
                try:
                    resp = requests.post(
                        f"{base_url}/download",
                        json={
                            "type": "track",
                            "music_id": int(track_id),
                            "add_to_playlist": False,
                            "create_zip": False,
                        },
                        timeout=60,
                    )
                    resp.raise_for_status()
                    _log_dl(f"download request sent track_id={track_id} status={resp.status_code}")
                except Exception:
                    failed_ids.add(track_id)
                    pending_ids.discard(track_id)

            idle_loops = 0
            max_idle_loops = 120

            while pending_ids and idle_loops < max_idle_loops:
                time.sleep(3)
                try:
                    queue_resp = requests.get(f"{base_url}/queue", timeout=30)
                    queue_resp.raise_for_status()
                    queue_items = parse_queue_items(queue_resp.json())
                except Exception:
                    idle_loops += 1
                    push_task_event(
                        task_id,
                        f"Checking queue… {len(success_ids)}/{total} downloaded",
                        stage="download_missing",
                        progress=round(((len(success_ids) + len(failed_ids)) / total) * 100),
                    )
                    continue

                completed_now = set()
                failed_now = set()

                for item in queue_items:
                    tid = extract_track_id_from_queue_item(item)
                    state = extract_queue_state(item)
                    result = item.get("result")
                    _log_dl(f"queue item raw_track_id={tid} state={state} result={result} pending={sorted(pending_ids)}")

                    if not tid:
                        continue
                    tid = str(tid).strip()
                    if tid not in pending_ids:
                        continue

                    if state == "mission accomplished":
                        completed_now.add(tid)
                        _log_dl(f"TRACK DONE tid={tid}")
                    elif state == "failed":
                        failed_now.add(tid)

                if completed_now:
                    success_ids.update(completed_now)
                    pending_ids.difference_update(completed_now)
                    changed_rows = mark_preview_rows_downloaded(playlist_id, completed_now)
                    for row in changed_rows:
                        push_task_row_update(task_id, row)
                    push_task_event(
                        task_id,
                        f"Downloaded {len(success_ids)}/{total}",
                        stage="download_missing",
                        progress=round(((len(success_ids) + len(failed_ids)) / total) * 100),
                    )

                if failed_now:
                    failed_ids.update(failed_now)
                    pending_ids.difference_update(failed_now)
                    push_task_event(
                        task_id,
                        f"Failed downloads: {len(failed_ids)}",
                        stage="download_missing",
                        progress=round(((len(success_ids) + len(failed_ids)) / total) * 100),
                    )

                if not completed_now and not failed_now:
                    idle_loops += 1
                else:
                    idle_loops = 0

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
