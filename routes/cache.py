import threading

from flask import Blueprint, flash, jsonify, redirect, request, url_for

from core.config import create_task, push_task_event
from core.webhook import notify
from routes.auth import admin_only
from core.library import (
    library_snapshot,
    search_library,
    rebuild_library_cache_full,
    rebuild_library_cache_full_with_progress,
    refresh_library_cache_incremental,
    refresh_library_cache_incremental_with_progress,
)

cache_bp = Blueprint("cache", __name__)


@cache_bp.get("/api/library/stats")
def library_stats_route():
    return jsonify({"ok": True, **library_snapshot()["meta"]})


@cache_bp.get("/api/library/search")
def library_search_route():
    return jsonify({"ok": True, "results": search_library(request.args.get("q", ""))})


@cache_bp.post("/cache/rebuild")
@admin_only
def cache_rebuild_route():
    try:
        result = rebuild_library_cache_full()
        flash(f"Full cache rebuilt: {result['count']} entries")
        notify("library.updated", entries=result["count"])
    except Exception as e:
        flash(f"Cache rebuild error: {e}")
    return redirect(url_for("system.config_view"))


def _library_task(title, name, work, done):
    """Runs `work(progress_cb)` as a task followed in Activity; `done(result)` is
    its last message."""
    task_id = create_task(title, kind="library", cancellable=True)

    def runner():
        try:
            push_task_event(task_id, f"{name} in progress", stage="cache", progress=0)
            result = work(lambda message=None, progress=None, stage=None: push_task_event(
                task_id, message=message, progress=progress, stage=stage))
            push_task_event(task_id, done(result), stage="done", progress=100, done=True)
            notify("library.updated", entries=result["count"])
        except Exception as e:
            push_task_event(task_id, f"{name} error: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@cache_bp.post("/cache/full/start")
@admin_only
def cache_full_start():
    return _library_task("Full library rebuild", "Full library cache rebuild", rebuild_library_cache_full_with_progress,
                         lambda result: f"Full rebuild done: {result['count']} entries")


@cache_bp.post("/cache/incremental/start")
def cache_incremental_start():
    return _library_task("Library refresh", "Incremental cache refresh", refresh_library_cache_incremental_with_progress,
                         lambda result: f"Incremental refresh done: {result['count']} entries, {result['rebuilt']} rebuilt")


@cache_bp.post("/cache/refresh")
def cache_refresh_route():
    try:
        result = refresh_library_cache_incremental()
        flash(f"Incremental cache done: {result['count']} entries, {result['rebuilt']} rebuilt")
        notify("library.updated", entries=result["count"])
    except Exception as e:
        flash(f"Cache refresh error: {e}")
    return redirect(url_for("system.config_view"))
