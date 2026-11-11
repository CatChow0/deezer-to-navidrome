"""The generated playlists: which versions run, and the tracks in quarantine, for
the profile of this browser. Each profile has its own."""
import logging
import time
from contextlib import contextmanager

from flask import Blueprint, Response, jsonify, request, session

from core import account_context, mix_builder, metadata_fix, mixes_db, nd_accounts, stats_db, stats_import, trial

logger = logging.getLogger(__name__)

mixes_bp = Blueprint("mixes", __name__)


def _profile():
    return account_context.resolve(request, session)


def _source(mix_id) -> str:
    from core.deezer import parse_auto_id

    parsed = parse_auto_id(mix_id)
    return {"discover": "Discover", "blend": "Daily Mix+"}.get(parsed[1] if parsed else "", "Other")


def _track(row, plays, now, rules, shared=None) -> dict:
    return {
        "id": row["deezer_id"],
        # The other profiles that also have it on trial: one file, a verdict each.
        "shared_with": [trial.label(a) for a in (shared or {}).get(row["deezer_id"], [])],
        "artist": row["artist"],
        "title": row["title"],
        "album": row["album"],
        "plays": plays.get(row["deezer_id"], 0),
        "reason": row["reason"],
        "source": _source(row["mix_id"]),
        "cover": f"/api/mixes/trial/{row['deezer_id']}/cover",
        "downloaded_at": row["downloaded_at"],
        "state_at": row["state_at"],
        "days_left": max(0, (trial.trial_ends_at(row, rules) - now + 86399) // 86400),
        "trash_days_left": max(0, (row["state_at"] + rules.trash_days * 86400 - now + 86399) // 86400),
    }


def _state(conn, account) -> dict:
    now = int(time.time())
    stats = stats_db.connect(account)
    try:
        plays = trial.plays_since_download(conn, stats, account)
    finally:
        stats.close()
    entries = mix_builder.library_entries()
    analysis = metadata_fix.status(conn, entries)
    analysis["running"] = metadata_fix.is_running()
    settings = mix_builder.load_settings(conn, account)
    rules = trial.rules_from(settings)
    profile = nd_accounts.get(account) or {}
    shared = trial.shared_with(conn, account)
    return {
        "profile": {"id": account, "label": profile.get("label") or account, "several": len(mix_builder.accounts()) > 1},
        "settings": settings,
        "downloads_blocked": mix_builder.downloads_possible(),
        "analysis": analysis,
        "running": mix_builder.is_running(),
        "last_run": mix_builder.last_run(conn, account),
        "navidrome_mounted": stats_import._navidrome_path().is_file(),
        # The disk limits are every profile's: so is what they count.
        "usage": trial.usage(conn, trial.plays_of_everyone(conn)),
        "on_trial": [_track(r, plays, now, rules, shared) for r in trial.listing(conn, trial.ON_TRIAL, account)],
        "pending": [_track(r, plays, now, rules, shared) for r in trial.listing(conn, trial.PENDING, account)],
        "trash": [_track(r, plays, now, rules, shared) for r in trial.listing(conn, trial.TRASH, account)],
    }


@mixes_bp.get("/api/mixes")
def state():
    conn = mixes_db.connect()
    try:
        return jsonify(_state(conn, _profile()))
    finally:
        conn.close()


@mixes_bp.post("/api/mixes/settings")
def settings():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "Expected settings"}), 400
    mode = body.pop("mix_mode", None)
    discover = body.pop("discover", None)
    if mode is not None and mode not in mix_builder.MIX_MODES:
        return jsonify({"ok": False, "error": "Choose off, Daily Mix or Daily Mix+"}), 400
    if mode == "blend" or discover:
        blocked = mix_builder.downloads_possible()
        if blocked:
            return jsonify({"ok": False, "error": blocked}), 400
    account = _profile()
    conn = mixes_db.connect()
    try:
        try:
            mix_builder.save_settings(conn, account, body)
        except (TypeError, ValueError, OverflowError):
            return jsonify({"ok": False, "error": "Limits must be numbers"}), 400
        if mode is not None:
            mix_builder.set_mix_mode(conn, account, mode)
        if discover is not None:
            mix_builder.set_discover(conn, account, bool(discover))
        if mix_builder.TRIAL_KEYS & set(body):
            # New rules apply to what is already in this quarantine, now.
            conn.close()
            mix_builder.review_quarantine(accounts=[account])
            conn = mixes_db.connect()
        if mode in ("daily", "blend") or discover:
            mixes_db.set_meta(conn, "metadata_fix_paused", False)
            metadata_fix.start_background(mix_builder.library_entries)
        return jsonify({"ok": True, **_state(conn, account)})
    finally:
        conn.close()


@mixes_bp.post("/api/metadata/fix")
def fix_metadata():
    """Asked for once, it then also takes care of new files on its own."""
    from core.config import create_task

    if metadata_fix.is_running() and metadata_fix.current_task():
        return jsonify({"ok": True, "task_id": metadata_fix.current_task()})
    conn = mixes_db.connect()
    try:
        mixes_db.set_meta(conn, "metadata_fix_on", True)
        mixes_db.set_meta(conn, "metadata_write_off", False)
        mixes_db.set_meta(conn, "metadata_fix_paused", False)
    finally:
        conn.close()
    task_id = create_task("Fix missing metadata", kind="metadata", cancellable=True)
    metadata_fix.start_background(mix_builder.library_entries, task_id=task_id)
    return jsonify({"ok": True, "task_id": task_id})


@mixes_bp.post("/api/metadata/undo")
def undo_metadata():
    from core.config import create_task

    if metadata_fix.is_running():
        return jsonify({"ok": False, "error": "Fix missing metadata is running: wait for it to finish"}), 409
    task_id = create_task("Undo metadata fix", kind="metadata", cancellable=True)
    metadata_fix.start_undo(task_id)
    return jsonify({"ok": True, "task_id": task_id})


@mixes_bp.post("/api/mixes/generate")
def generate():
    if mix_builder.is_running():
        return jsonify({"ok": False, "error": "Mixes are already being generated: try again when they are done"}), 409
    account = _profile()
    conn = mixes_db.connect()
    try:
        current = mix_builder.load_settings(conn, account)
    finally:
        conn.close()
    versions = mix_builder.enabled_versions(current)
    if not versions:
        return jsonify({"ok": False, "error": "Turn on at least one version first"}), 400
    return jsonify({"ok": True, "task_id": mix_builder.start_task(account, versions)})


def _update_trial_playlists(conn, profiles=None) -> None:
    """The decision is made and the file has moved: the On trial playlists of
    the profiles that had the track change. One that cannot be written (an
    unmapped folder, say) must not make it look like a failure."""
    mix_builder.refresh_trial_playlists(conn, profiles)


# The review moves files on its own (core/mix_builder.py): a decision taken
# meanwhile would be overwritten by its older view of the quarantine.
QUARANTINE_WAIT = 30


class _Busy(Exception):
    pass


@contextmanager
def _quarantine_held():
    if not mix_builder._review_lock.acquire(timeout=QUARANTINE_WAIT):
        raise _Busy()
    try:
        yield
    finally:
        mix_builder._review_lock.release()


def _busy():
    return jsonify({"ok": False, "error": "The quarantine is being reviewed: try again in a moment"}), 409


def _decide(action, deezer_id):
    try:
        with _quarantine_held():
            return _decide_now(action, deezer_id)
    except _Busy:
        return _busy()


def _decide_now(action, deezer_id):
    account = _profile()
    conn = mixes_db.connect()
    try:
        if trial.get(conn, deezer_id, account) is None:
            return jsonify({"ok": False, "error": "This track is not in this profile's quarantine"}), 404
        concerned = trial.accounts_of(conn, deezer_id)
        action(conn, deezer_id, account, int(time.time()))
        _update_trial_playlists(conn, concerned)
        return jsonify({"ok": True, **_state(conn, account)})
    except (trial.TrialError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


def _keep(conn, deezer_id, account, now) -> None:
    """Kept by hand: into the library, unless the library has it already, in
    which case the library's copy is used and no second one is made."""
    row = trial.get(conn, deezer_id, account)
    library = mix_builder.library_copies().get(row["track_key"]) if row else None
    if library and row["state"] in trial.ACTIVE:
        trial.replace_by_library(conn, deezer_id, library, now)
    else:
        trial.keep(conn, deezer_id, account, now)


@mixes_bp.post("/api/mixes/trial/<deezer_id>/keep")
def keep(deezer_id):
    return _decide(_keep, deezer_id)


@mixes_bp.post("/api/mixes/trial/<deezer_id>/remove")
def remove(deezer_id):
    return _decide(trial.remove, deezer_id)


@mixes_bp.post("/api/mixes/trial/<deezer_id>/restore")
def restore(deezer_id):
    return _decide(trial.restore, deezer_id)


@mixes_bp.get("/api/mixes/trial/<deezer_id>/cover")
def cover(deezer_id):
    """The picture inside the downloaded file."""
    from core import stats_covers

    conn = mixes_db.connect()
    try:
        row = trial.file_row(conn, deezer_id)
    finally:
        conn.close()
    data = stats_covers._embedded_art(row["path"]) if row and row["path"] else None
    if not data:
        return Response(status=404)
    mimetype = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    response = Response(data, mimetype=mimetype)
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@mixes_bp.post("/api/mixes/trial/keep-pending")
def keep_pending():
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list):
        return jsonify({"ok": False, "error": "Expected the tracks to keep"}), 400
    account = _profile()
    try:
        with _quarantine_held():
            conn = mixes_db.connect()
            try:
                kept = trial.keep_all_pending(conn, account, int(time.time()), [str(i) for i in ids])
                _update_trial_playlists(conn)
                return jsonify({"ok": True, "kept": kept, **_state(conn, account)})
            finally:
                conn.close()
    except _Busy:
        return _busy()


@mixes_bp.post("/api/mixes/trial/empty-trash")
def empty_trash():
    account = _profile()
    try:
        with _quarantine_held():
            conn = mixes_db.connect()
            try:
                deleted = trial.empty_trash(conn, account, int(time.time()))
                _update_trial_playlists(conn)
                return jsonify({"ok": True, "deleted": deleted, **_state(conn, account)})
            finally:
                conn.close()
    except _Busy:
        return _busy()


@mixes_bp.post("/api/mixes/trial/remove-pending")
def remove_pending():
    account = _profile()
    try:
        with _quarantine_held():
            conn = mixes_db.connect()
            try:
                removed = trial.remove_all_pending(conn, account, int(time.time()))
                _update_trial_playlists(conn)
                return jsonify({"ok": True, "removed": removed, **_state(conn, account)})
            finally:
                conn.close()
    except _Busy:
        return _busy()
