import logging
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_stop_event = threading.Event()
_scheduler_thread = None

# Per-playlist runtime state (in memory, lost on restart)
# {playlist_id: {"next_run_at": int, "last_run_at": int|None}}
_state: dict = {}


def get_status() -> dict:
    """Return a copy of the per-playlist schedule state."""
    with _lock:
        return {pid: dict(v) for pid, v in _state.items()}


def notify_playlist_updated(playlist_id: str, pl: dict):
    """Called immediately when a playlist's automation settings are saved."""
    with _lock:
        if not pl.get("auto_scan_enabled"):
            _state.pop(playlist_id, None)
        else:
            interval_secs = max(1, int(pl.get("auto_scan_interval_minutes") or 60)) * 60
            prev_last = (_state.get(playlist_id) or {}).get("last_run_at")
            _state[playlist_id] = {
                "next_run_at": int(time.time()) + interval_secs,
                "last_run_at": prev_last,
            }


def _sync_state_from_playlists(playlists):
    """Ensure _state is consistent with current playlist list (adds new, removes deleted)."""
    now = int(time.time())
    with _lock:
        current_ids = {pl["id"] for pl in playlists}

        # Remove playlists that no longer exist or have auto-scan disabled
        for pid in list(_state.keys()):
            pl = next((p for p in playlists if p["id"] == pid), None)
            if pl is None or not pl.get("auto_scan_enabled"):
                del _state[pid]

        # Add newly enabled playlists that aren't tracked yet
        for pl in playlists:
            pid = pl["id"]
            if pl.get("auto_scan_enabled") and pid not in _state:
                interval_secs = max(1, int(pl.get("auto_scan_interval_minutes") or 60)) * 60
                _state[pid] = {
                    "next_run_at": now + interval_secs,
                    "last_run_at": None,
                }

        _ = current_ids  # used implicitly above


def _run_playlist(pl, cfg):
    from core.config import create_task, push_task_event, push_task_row_update
    from core.deezer import convert_playlist, submit_missing_downloads

    pid = pl["id"]
    task_id = create_task(f"Auto scan: {pl.get('title') or pid}", kind="scan", playlist_id=pid)

    def on_progress(message=None, progress=None, stage=None, row_update=None):
        if row_update is not None:
            push_task_row_update(task_id, row_update)
        if message is not None or progress is not None or stage is not None:
            push_task_event(task_id, message=message, progress=progress, stage=stage)

    try:
        result = convert_playlist(pid, progress_cb=on_progress, quick=True)
        summary = f"{result.get('matched', 0)} matched, {result.get('unmatched', 0)} missing"
        logger.info(f"[auto-scan] Playlist {pid} ({pl.get('title', '')}): {summary}")
    except Exception as e:
        logger.error(f"[auto-scan] Scan failed for playlist {pid}: {e}")
        push_task_event(task_id, f"Scan failed: {e}", stage="error", done=True, error=True)
        return

    if pl.get("auto_download_after_scan"):
        base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
        if base_url:
            try:
                n = submit_missing_downloads(pid, base_url)
                if n:
                    summary += f", {n} sent to Deezer Downloader"
                    logger.info(f"[auto-scan] Submitted {n} download(s) for playlist {pid}")
            except Exception as e:
                summary += ", download request failed"
                logger.error(f"[auto-scan] Download submit failed for {pid}: {e}")
        else:
            logger.warning("[auto-scan] auto_download_after_scan enabled but deezer_dl_base_url is not set")

    push_task_event(task_id, f"Done: {summary}", stage="done", progress=100, done=True)


def _refresh_library_after_scans(count):
    from core.config import create_task, push_task_event
    from core.library import refresh_library_cache_incremental_with_progress

    logger.info(f"[auto-scan] {count} playlist(s) processed — running incremental cache refresh")
    task_id = create_task("Library refresh (after auto scan)", kind="library")
    try:
        refresh_library_cache_incremental_with_progress(
            progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                task_id, message=message, progress=progress, stage=stage
            )
        )
        push_task_event(task_id, "Library refreshed", stage="done", progress=100, done=True)
    except Exception as e:
        logger.error(f"[auto-scan] Cache refresh failed: {e}")
        push_task_event(task_id, f"Library refresh failed: {e}", stage="error", done=True, error=True)


def _scheduler_loop():
    while not _stop_event.is_set():
        if _stop_event.wait(timeout=30):
            break

        from core.deezer import load_playlists
        from core.config import load_config

        playlists = load_playlists()
        _sync_state_from_playlists(playlists)

        now = int(time.time())
        due = []
        with _lock:
            for pl in playlists:
                pid = pl["id"]
                s = _state.get(pid)
                if s and s["next_run_at"] <= now:
                    due.append(pl)

        if not due:
            continue

        cfg = load_config()
        for pl in due:
            _run_playlist(pl, cfg)
            pid = pl["id"]
            interval_secs = max(1, int(pl.get("auto_scan_interval_minutes") or 60)) * 60
            with _lock:
                if pid in _state:
                    _state[pid]["last_run_at"] = int(time.time())
                    _state[pid]["next_run_at"] = int(time.time()) + interval_secs

        # After all playlist scans/downloads are done, refresh cache to pick up new downloads
        _refresh_library_after_scans(len(due))


def start():
    global _scheduler_thread, _stop_event
    _stop_event = threading.Event()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, daemon=True, name="auto-scan-scheduler"
    )
    _scheduler_thread.start()
    logger.info("[auto-scan] Scheduler started")


def restart():
    logger.info("[auto-scan] Restarting scheduler")
    _stop_event.set()
    start()
