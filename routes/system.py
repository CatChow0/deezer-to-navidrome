import json
import threading

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from queue import Empty

import requests

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
    load_config,
    push_task_event,
    save_config,
)
from core.version import get_app_version, get_latest_available_version

system_bp = Blueprint("system", __name__)


@system_bp.get("/favicon.ico")
def favicon():
    return "", 204


@system_bp.get("/covers/<path:filename>")
def serve_cover(filename):
    return send_from_directory(COVERS_DIR, filename)


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


@system_bp.get("/tasks/<task_id>/stream")
def task_stream(task_id):
    def generate():
        task = TASKS.get(task_id)
        if not task:
            yield 'data: {"type":"status","message":"Task not found","done":true,"error":true}\n\n'
            return
        while True:
            try:
                event = task["queue"].get(timeout=15)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("done"):
                    break
            except Empty:
                if task.get("done"):
                    break
                yield ": keepalive\n\n"

    return Response(generate(), mimetype="text/event-stream")


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
        deezer_dl_base_url = request.form.get("deezer_dl_base_url", "").strip().rstrip("/")

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

        cfg = {
            "scan_dirs": scan_dirs,
            "playlists_base_dir": playlists_base_dir,
            "playlist_ids_file": playlist_ids_file or str(PLAYLIST_IDS_FILE),
            "library_cache_file": library_cache_file or str(LIBRARY_CACHE_FILE),
            "preview_state_file": preview_state_file or str(PREVIEW_STATE_FILE),
            "host_to_navidrome_roots": mappings,
            "deezer_dl_base_url": deezer_dl_base_url or "https://deezerdl.example.com",
            "library_workers_per_dir": library_workers_per_dir,
            "match_workers": match_workers,
        }
        save_config(cfg)
        flash("Configuration saved")
        return redirect(url_for("system.config_view"))

    cfg = load_config()
    return render_template("config.html", config=cfg)


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


@system_bp.route("/deezer-dl/track/<track_id>", methods=["POST"])
def deezer_dl_track(track_id):
    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url not configured"}), 400

    task_id = create_task()

    def run():
        try:
            push_task_event(task_id, message=f"Sending DL request for track {track_id}…", stage="dl", progress=0)
            payload = {
                "type": "track",
                "music_id": track_id,
                "add_to_playlist": False,
                "create_zip": False,
            }
            resp = requests.post(f"{base_url}/download", json=payload, timeout=60)
            if resp.status_code != 200:
                push_task_event(
                    task_id,
                    message=f"Error {resp.status_code}: {resp.text[:200]}",
                    stage="dl",
                    done=True,
                    error=True,
                )
                return
            data = resp.json()
            push_task_event(
                task_id,
                message=f"Download started: {data.get('file') or data.get('message') or 'OK'}",
                stage="dl",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, message=f"Exception: {e}", stage="dl", done=True, error=True)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@system_bp.get("/deezer-dl/queue")
def deezer_dl_queue():
    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url not configured"}), 400
    try:
        resp = requests.get(f"{base_url}/queue", timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return jsonify({"error": f"Error calling /queue: {e}"}), 502
    return jsonify(resp.json())


@system_bp.post("/deezer-dl/download/start")
def deezer_dl_download_start():
    data = request.get_json(silent=True) or {}
    download_type = str(data.get("type") or "").strip().lower()
    music_id = str(data.get("music_id") or "").strip()
    if download_type not in {"track", "album", "artist"}:
        return jsonify({"error": "invalid type"}), 400
    if not music_id.isdigit():
        return jsonify({"error": "invalid music_id"}), 400

    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url not configured"}), 400

    task_id = create_task()

    def runner():
        try:
            push_task_event(task_id, f"Starting download {download_type} {music_id}", stage="download", progress=0)
            payload = {
                "type": download_type,
                "music_id": int(music_id),
                "add_to_playlist": False,
                "create_zip": False,
            }
            resp = requests.post(f"{base_url}/download", json=payload, timeout=60)
            resp.raise_for_status()
            push_task_event(
                task_id,
                f"Download started for {download_type} {music_id}",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, f"Download error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})
