import threading

from flask import Blueprint, flash, jsonify, redirect, url_for

from core.config import create_task, push_task_event
from core.library import (
    rebuild_library_cache_full,
    rebuild_library_cache_full_with_progress,
    refresh_library_cache_incremental,
    refresh_library_cache_incremental_with_progress,
)

cache_bp = Blueprint("cache", __name__)


@cache_bp.post("/cache/rebuild")
def cache_rebuild_route():
    try:
        result = rebuild_library_cache_full()
        flash(f"Full cache rebuilt: {result['count']} entries")
    except Exception as e:
        flash(f"Cache rebuild error: {e}")
    return redirect(url_for("system.config_view"))


@cache_bp.post("/cache/full/start")
def cache_full_start():
    task_id = create_task()

    def runner():
        try:
            push_task_event(task_id, "Full library cache rebuild in progress", stage="cache", progress=0)
            result = rebuild_library_cache_full_with_progress(
                progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                    task_id, message=message, progress=progress, stage=stage
                )
            )
            push_task_event(
                task_id,
                f"Full rebuild done: {result['count']} entries",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, f"Full rebuild error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@cache_bp.post("/cache/incremental/start")
def cache_incremental_start():
    task_id = create_task()

    def runner():
        try:
            push_task_event(task_id, "Incremental cache refresh in progress", stage="cache", progress=0)
            result = refresh_library_cache_incremental_with_progress(
                progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                    task_id, message=message, progress=progress, stage=stage
                )
            )
            push_task_event(
                task_id,
                f"Incremental refresh done: {result['count']} entries, {result['rebuilt']} rebuilt",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(task_id, f"Incremental refresh error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@cache_bp.post("/cache/refresh")
def cache_refresh_route():
    try:
        result = refresh_library_cache_incremental()
        flash(f"Incremental cache done: {result['count']} entries, {result['rebuilt']} rebuilt")
    except Exception as e:
        flash(f"Cache refresh error: {e}")
    return redirect(url_for("system.config_view"))
