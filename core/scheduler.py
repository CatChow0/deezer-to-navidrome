import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_stop_event = threading.Event()
_scheduler_thread = None

# Per-playlist schedule: {playlist_id: {"next_run_at": int, "last_run_at": int|None}}.
# The last runs are also kept on disk, so a daily scan still runs when the
# container restarts every night.
_state: dict = {}
# Playlists being scanned: a scheduler restarted meanwhile does not scan them twice.
_running: set = set()


def _last_runs_file():
    from core.config import DATA_DIR

    return DATA_DIR / "scheduler.json"


def _load_last_runs() -> dict:
    from core import files

    try:
        data = files.read_json(_last_runs_file(), {})
    except OSError:
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))} if isinstance(data, dict) else {}


def _save_last_run(playlist_id, at) -> None:
    from core import files

    try:
        runs = _load_last_runs()
        runs[str(playlist_id)] = int(at)
        files.write_json(_last_runs_file(), runs)
    except OSError as e:
        logger.warning("[auto-scan] Could not save when %s was scanned: %s", playlist_id, e)


def _interval(pl) -> int:
    try:
        return max(1, int(pl.get("auto_scan_interval_minutes") or 60)) * 60
    except (TypeError, ValueError):
        return 3600


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
            prev_last = (_state.get(playlist_id) or {}).get("last_run_at")
            _state[playlist_id] = {
                "next_run_at": int(time.time()) + _interval(pl),
                "last_run_at": prev_last,
            }


def _sync_state_from_playlists(playlists, last_runs=None):
    """Ensure _state is consistent with current playlist list (adds new, removes deleted)."""
    now = int(time.time())
    enabled = {pl["id"]: pl for pl in playlists if pl.get("auto_scan_enabled")}
    with _lock:
        for pid in list(_state):
            if pid not in enabled:
                del _state[pid]
        for pid, pl in enabled.items():
            if pid in _state:
                continue
            if last_runs is None:
                last_runs = _load_last_runs()
            last = last_runs.get(pid)
            # Known from before a restart: due when it would have been, else at once.
            _state[pid] = {"next_run_at": max(now, last + _interval(pl)) if last else now + _interval(pl),
                           "last_run_at": last}


def _run_playlist(pl, cfg):
    from core.config import create_task, push_task_event, push_task_row_update
    from core.deezer import convert_playlist, submit_missing_downloads

    pid = pl["id"]
    task_id = create_task(f"Auto scan: {pl.get('title') or pid}", kind="scan", playlist_id=pid, cancellable=True)

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
        from core import deezer_dl

        from core import account_context
        from core.deezer import accounts_for

        owners = accounts_for(pid)
        if deezer_dl.download_arl(account_context.download_account_of_profile(owners[0]) if owners else None):
            try:
                n = submit_missing_downloads(pid)
                if n:
                    summary += f", {n} queued for download"
                    logger.info(f"[auto-scan] Queued {n} download(s) for playlist {pid}")
            except Exception as e:
                summary += ", download request failed"
                logger.error(f"[auto-scan] Download submit failed for {pid}: {e}")
        else:
            logger.warning("[auto-scan] auto_download_after_scan enabled but no Deezer account is connected")

    push_task_event(task_id, f"Done: {summary}", stage="done", progress=100, done=True)


def _refresh_library_after_scans(count):
    from core.config import create_task, push_task_event
    from core.library import refresh_library_cache_incremental_with_progress

    logger.info(f"[auto-scan] {count} playlist(s) processed — running incremental cache refresh")
    task_id = create_task("Library refresh (after auto scan)", kind="library", cancellable=True)
    try:
        refresh_library_cache_incremental_with_progress(
            progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                task_id, message=message, progress=progress, stage=stage
            )
        )
        push_task_event(task_id, "Library refreshed", stage="done", progress=100, done=True)
        from core.webhook import notify
        notify("library.updated")
    except Exception as e:
        logger.error(f"[auto-scan] Cache refresh failed: {e}")
        push_task_event(task_id, f"Library refresh failed: {e}", stage="error", done=True, error=True)


_last_mix_check = 0.0
MIX_CHECK_SECONDS = 600
_last_release_attempt = 0.0
RELEASE_RETRY_SECONDS = 3600


def _refresh_releases_if_stale():
    """Keeps the release feed fresh when a Deezer account is connected; after
    a failed attempt, waits an hour before trying again."""
    global _last_release_attempt
    from core import deezer_accounts
    from routes.account import accounts_with_stale_feeds, start_release_refresh

    if time.time() - _last_release_attempt < RELEASE_RETRY_SECONDS:
        return
    try:
        stale = accounts_with_stale_feeds()
        if stale:
            _last_release_attempt = time.time()
        for account_id in stale:
            label = (deezer_accounts.get(account_id) or {}).get("label") or account_id
            start_release_refresh(f"Release feed refresh (automatic): {label}", account=account_id)
    except Exception as e:
        logger.error(f"[releases] Automatic refresh failed to start: {e}")


def _scheduler_loop(stop):
    """`stop` is this thread's own event: after a restart, a pass still running
    ends the old thread instead of going on next to the new one."""
    while not stop.wait(timeout=30):
        try:
            _one_pass(stop)
        except Exception:
            # Never the end of the scheduler: the next pass tries again.
            logger.exception("[auto-scan] A scheduler pass failed")


def _one_pass(stop):
    from core.deezer import load_playlists
    from core.config import load_config
    from core.stats_enrich import start_background_batch

    try:
        start_background_batch()
    except Exception as e:
        logger.error(f"[stats] Could not start the lookups: {e}")

    playlists = load_playlists()
    _sync_state_from_playlists(playlists)

    _refresh_releases_if_stale()

    # Reading the library index is not free: every few minutes is plenty.
    global _last_mix_check
    if time.time() - _last_mix_check >= MIX_CHECK_SECONDS:
        _last_mix_check = time.time()
        try:
            from core import mix_builder

            mix_builder.tick()
        except Exception as e:
            logger.error(f"[mixes] Could not check the generated playlists: {e}")
        try:
            from core import publish

            publish.sync_all()
            publish.retry_pending()
        except Exception as e:
            logger.error(f"[navidrome] Could not sync the playlists with Navidrome: {e}")

    now = int(time.time())
    with _lock:
        due = [pl for pl in playlists
               if pl["id"] in _state and _state[pl["id"]]["next_run_at"] <= now and pl["id"] not in _running]
        _running.update(pl["id"] for pl in due)

    if not due:
        return

    cfg = load_config()
    try:
        for pl in due:
            if stop.is_set():
                break
            pid = pl["id"]
            try:
                _run_playlist(pl, cfg)
            finally:
                finished = int(time.time())
                with _lock:
                    _running.discard(pid)
                    if pid in _state:
                        _state[pid]["last_run_at"] = finished
                        _state[pid]["next_run_at"] = finished + _interval(pl)
                _save_last_run(pid, finished)
    finally:
        with _lock:
            _running.difference_update(pl["id"] for pl in due)

    # Picks up what the scans found in the library. Downloads they queued
    # refresh the library themselves when they finish.
    _refresh_library_after_scans(len(due))


_recovered = False


def start():
    global _scheduler_thread, _stop_event, _recovered
    # The tests import the app: a real scheduler would open their databases while
    # they delete them.
    if os.environ.get("D2N_SCHEDULER") == "off":
        logger.info("[auto-scan] Scheduler not started (D2N_SCHEDULER=off)")
        return
    if not _recovered:
        # Once per process: a restart after saving Settings must not touch the
        # files a metadata pass is writing at that moment.
        _recovered = True
        try:
            from core.metadata_fix import recover_at_start

            recover_at_start()
        except Exception as e:
            logger.error(f"[metadata] Could not clear temporary files: {e}")
    stop = threading.Event()
    _stop_event = stop
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, args=(stop,), daemon=True, name="auto-scan-scheduler"
    )
    _scheduler_thread.start()
    logger.info("[auto-scan] Scheduler started")


def restart():
    logger.info("[auto-scan] Restarting scheduler")
    _stop_event.set()
    start()
