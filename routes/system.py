import json
import threading
import time

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    request,
    send_from_directory,
    url_for,
)
from core.config import (
    COVERS_DIR,
    LIBRARY_CACHE_FILE,
    PLAYLIST_IDS_FILE,
    PREVIEW_STATE_FILE,
    TASKS,
    clear_dedup_choices_file,
    clear_dedup_report_file,
    clear_library_cache_file,
    clear_playlists_and_covers,
    clear_preview_state_file,
    create_task,
    follow_task,
    list_tasks,
    push_task_event,
    save_config,
)
from core.version import get_app_version, get_latest_available_version
from core import deezer_dl
from core import download_queue
from core import scheduler
from routes.playlists import render_app

system_bp = Blueprint("system", __name__)


@system_bp.get("/favicon.ico")
def favicon():
    return "", 204


@system_bp.get("/covers/<path:filename>")
def serve_cover(filename):
    # Covers are named after the playlist ID and rarely change: let the browser keep them for a day.
    return send_from_directory(COVERS_DIR, filename, max_age=86400)


@system_bp.get("/health")
def health():
    return jsonify({"ok": True})


@system_bp.get("/api/version")
def version_route():
    return jsonify({"version": get_app_version()})


@system_bp.get("/api/latest-version")
def latest_version_route():
    result = get_latest_available_version()
    return jsonify({
        "current_version": get_app_version(),
        "latest_version": result["version"],
        "url": result["url"],
        "source": result["source"],
        "update_available": result["version"] is not None,
    })


# Each stream is closed after this long; the browser reconnects and resumes
# after the last event it got. Reverse proxies often cut long-lived responses.
STREAM_SEGMENT_SECONDS = 45


@system_bp.get("/tasks/<task_id>/stream")
def task_stream(task_id):
    # EventSource sends Last-Event-ID when it reconnects by itself; "from" is
    # used when the page has to open a new stream.
    last_id = request.headers.get("Last-Event-ID", "")
    from_arg = request.args.get("from", "")
    start = int(last_id) + 1 if last_id.isdigit() else int(from_arg) if from_arg.isdigit() else 0

    def generate():
        yield "retry: 1500\n\n"
        if task_id not in TASKS:
            yield 'data: {"type":"status","message":"Task not found","done":true,"error":true}\n\n'
            return
        deadline = time.monotonic() + STREAM_SEGMENT_SECONDS
        for index, event in follow_task(task_id, start=start, keepalive=10):
            if event is None:
                yield ": keepalive\n\n"
            else:
                yield f"id: {index}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            if time.monotonic() > deadline:
                return

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@system_bp.get("/api/tasks")
def tasks_route():
    return jsonify({"ok": True, "tasks": list_tasks()})


@system_bp.route("/config", methods=["GET", "POST"])
def config_view():
    if request.method == "POST":
        scan_dirs = [
            x.strip()
            for x in request.form.get("scan_dirs", "").splitlines()
            if x.strip()
        ]
        playlists_base_dir = request.form.get("playlists_base_dir", "").strip()
        playlist_ids_file = request.form.get("playlist_ids_file", "").strip()
        library_cache_file = request.form.get("library_cache_file", "").strip()
        preview_state_file = request.form.get("preview_state_file", "").strip()
        deezer_dl_dir = request.form.get("deezer_dl_dir", "").strip()

        mapping_hosts = request.form.getlist("mapping_host[]")
        mapping_navs = request.form.getlist("mapping_navidrome[]")

        mappings = []
        for h, n in zip(mapping_hosts, mapping_navs):
            h = h.strip()
            n = n.strip()
            if h and n:
                mappings.append({"host": h, "navidrome": n})

        library_workers_per_dir = max(1, int(request.form.get("library_workers_per_dir", "2") or "2"))
        match_workers = max(1, int(request.form.get("match_workers", "4") or "4"))
        release_refresh_hours = max(0, int(request.form.get("release_refresh_hours", "24") or "24"))
        download_workers = max(1, int(request.form.get("download_workers", "4") or "4"))

        cfg = {
            "scan_dirs": scan_dirs,
            "playlists_base_dir": playlists_base_dir,
            "playlist_ids_file": playlist_ids_file or str(PLAYLIST_IDS_FILE),
            "library_cache_file": library_cache_file or str(LIBRARY_CACHE_FILE),
            "preview_state_file": preview_state_file or str(PREVIEW_STATE_FILE),
            "host_to_navidrome_roots": mappings,
            "deezer_dl_dir": deezer_dl_dir,
            "library_workers_per_dir": library_workers_per_dir,
            "match_workers": match_workers,
            "release_refresh_hours": release_refresh_hours,
            "download_workers": download_workers,
        }
        save_config(cfg)
        scheduler.restart()
        flash("Configuration saved")
        return redirect(url_for("system.config_view"))

    return render_app("settings")


@system_bp.get("/api/scheduler/status")
def scheduler_status():
    from core.deezer import load_playlists
    playlists = load_playlists()
    state = scheduler.get_status()
    result = []
    enabled_count = 0
    for pl in playlists:
        pid = pl["id"]
        s = state.get(pid, {})
        enabled = bool(pl.get("auto_scan_enabled"))
        if enabled:
            enabled_count += 1
        result.append({
            "id": pid,
            "title": pl.get("title", ""),
            "auto_scan_enabled": enabled,
            "auto_scan_interval_minutes": pl.get("auto_scan_interval_minutes") or 60,
            "auto_download_after_scan": bool(pl.get("auto_download_after_scan")),
            "next_run_at": s.get("next_run_at"),
            "last_run_at": s.get("last_run_at"),
        })
    return jsonify({"playlists": result, "enabled_count": enabled_count})


@system_bp.post("/admin/clear/library-cache")
def clear_library_cache_route():
    clear_library_cache_file()
    flash("music_library_cache cleared")
    return redirect(url_for("system.config_view"))


@system_bp.post("/admin/clear/preview-state")
def clear_preview_state_route():
    clear_preview_state_file()
    flash("playlist_preview_state cleared")
    return redirect(url_for("system.config_view"))


@system_bp.post("/admin/clear/playlists")
def clear_playlists_route():
    clear_playlists_and_covers()
    flash("Playlists, covers and playlist_preview_state cleared")
    return redirect(url_for("system.config_view"))


@system_bp.post("/admin/clear/all")
def clear_all_route():
    clear_playlists_and_covers()
    clear_library_cache_file()
    flash("All cleared: playlists, covers, playlist_preview_state and music_library_cache")
    return redirect(url_for("system.config_view"))


@system_bp.post("/admin/clear/dedup-report")
def clear_dedup_report_route():
    clear_dedup_report_file()
    flash("dedup_report cleared")
    return redirect(url_for("system.config_view"))


@system_bp.post("/admin/clear/dedup-choices")
def clear_dedup_choices_route():
    clear_dedup_choices_file()
    flash("dedup_choices cleared")
    return redirect(url_for("system.config_view"))


def _finished(task_id, message):
    """Builds the callback that closes a download task when the queue is done."""

    def done(_task, _result, error):
        if error:
            push_task_event(task_id, f"Download failed: {error}", stage="error", done=True, error=True)
        else:
            push_task_event(task_id, message, stage="done", progress=100, done=True)

    return done


@system_bp.route("/deezer-dl/track/<track_id>", methods=["POST"])
def deezer_dl_track(track_id):
    if not track_id.isdigit():
        return jsonify({"error": "invalid track id"}), 400
    if not deezer_dl.download_arl():
        return jsonify({"error": "No Deezer account connected. Add your ARL in Settings."}), 400

    task_id = create_task(f"Download track {track_id}", kind="download", visible=False)

    def run():
        try:
            push_task_event(task_id, message=f"Downloading track {track_id}…", stage="dl", progress=0)
            download_queue.enqueue_download("track", track_id, on_done=_finished(task_id, f"Downloaded track {track_id}"))
        except Exception as e:
            push_task_event(task_id, message=f"Download failed: {e}", stage="error", done=True, error=True)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@system_bp.get("/deezer-dl/queue")
def deezer_dl_queue():
    """The downloads in progress and the ones already done.

    Same shape as the queue of the separate downloader, so the pages reading
    it did not have to change."""
    return jsonify(download_queue.queue_snapshot())


@system_bp.post("/deezer-dl/download/start")
def deezer_dl_download_start():
    data = request.get_json(silent=True) or {}
    download_type = str(data.get("type") or "").strip().lower()
    music_id = str(data.get("music_id") or "").strip()
    if download_type not in {"track", "album"}:
        return jsonify({"error": "invalid type"}), 400
    if not music_id.isdigit():
        return jsonify({"error": "invalid music_id"}), 400
    if not deezer_dl.download_arl():
        return jsonify({"error": "No Deezer account connected. Add your ARL in Settings."}), 400

    task_id = create_task(f"Download {download_type} {music_id}", kind="download", visible=False)

    def runner():
        try:
            push_task_event(task_id, f"Starting download {download_type} {music_id}", stage="download", progress=0)
            download_queue.enqueue_download(
                download_type, music_id, on_done=_finished(task_id, f"Downloaded {download_type} {music_id}")
            )
        except Exception as e:
            push_task_event(task_id, f"Download error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})
