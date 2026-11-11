import threading

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for

from core.patch_notes import RELEASES
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
    rematch_track,
)
from core import account_context, android_app, crossplatform, nd_accounts, publish
from core.deezer import accounts_for, add_entry, give_to_account, is_auto_id, modify_playlists, remove_entries, set_accounts
from core.utils import extract_playlist_id
from routes.auth import my_download_account, refused
from core.xp_sources import MAX_CSV_BYTES, SourceError, spotify_playlist_id
from core import scheduler

import time

playlists_bp = Blueprint("playlists", __name__)


def _log_dl(msg):
    print(f"[download-missing] {msg}", flush=True)


def _active():
    return account_context.resolve(request, session)


def _label(account_id):
    account = nd_accounts.get(account_id)
    return account["label"] if account else account_id


class PlaylistError(ValueError):
    """Shown to the user as it is."""


def playlist_refused(playlist_id):
    """A playlist of another account's profiles is not reached by its ID (here and under /api/v1)."""
    playlist = next((p for p in load_playlists() if p["id"] == playlist_id), None) if playlist_id else None
    if playlist is not None and not account_context.may_see_playlist(playlist):
        return refused("This playlist is not on your profiles.")
    return None


@playlists_bp.before_request
def _only_your_playlists():
    return playlist_refused((request.view_args or {}).get("playlist_id"))


def dashboard_playlists(account):
    """The playlists of this profile, with the names its user gave them in
    Navidrome, and the ones the user made there. For the dashboard and the API.
    An account of this app without a profile yet has none."""
    if not account:
        return [], []
    playlists = [p for p in load_playlists() if not p.get("accounts") or account in p["accounts"]]
    handmade = []
    if account:
        names = publish.custom_titles(account)
        playlists = [{**p, "title": names[p["id"]], "deezer_title": p["title"]} if p["id"] in names else p
                     for p in playlists]
        handmade = publish.handmade(account)
        publish.sync_soon(account)
    return playlists, handmade


def render_app(view):
    """Dashboard and settings live on the same page; `view` picks the one shown
    first. The dashboard shows the playlists of this browser's account."""
    active = _active()
    playlists, handmade = dashboard_playlists(active)
    return render_template(
        "home.html",
        playlists=playlists,
        navidrome_playlists=handmade,
        nd_profile=active,
        config=load_config(),
        view=view,
        download_dir=deezer_dl.download_dir_status(),
        android_app=android_app.info(),
        whats_new=whats_new_state(),
        releases=RELEASES,
    )


@playlists_bp.get("/")
def home():
    return render_app("dashboard")


@playlists_bp.get("/releases")
def releases_view():
    return render_app("releases")


def _open_playlist(playlist_id):
    """The dashboard with this playlist's drawer open."""
    return redirect(url_for("playlists.home", playlist=playlist_id))


def _share_existing(playlist_id, account_id):
    """A playlist already saved for other accounts now also goes to this one,
    from its last scan. Returns the message to show."""
    if not give_to_account(playlist_id, account_id):
        return "Playlist already saved"
    state = get_preview_state(playlist_id) or {}
    if isinstance(state.get("rows"), list):
        publish.publish(playlist_id, state.get("playlist_title") or playlist_title(playlist_id), state["rows"],
                        accounts=[account_id])
    return f"Playlist added to {_label(account_id)}"


def add_playlist_for(value, account) -> dict:
    """Adds a Deezer playlist by its link or ID, or a Spotify playlist by its
    link, for this profile. {"id", "added", "message", "task_id", "open"}: a
    Spotify playlist is scanned at once, and `open` says its drawer should open."""
    if spotify_playlist_id(value):
        try:
            pid, added = crossplatform.add_spotify(value, accounts=[account] if account else None)
        except SourceError as e:
            raise PlaylistError(str(e)) from e
        if not added:
            return {"id": pid, "added": False, "open": True, "task_id": None,
                    "message": _share_existing(pid, account) if account else "Playlist already saved"}
        task_id = _start_scan(pid, quick=True, title=f"Finding on Deezer: {playlist_title(pid)}")
        return {"id": pid, "added": True, "open": True, "task_id": task_id,
                "message": "Spotify playlist added: its tracks are being found on Deezer"}

    pid = extract_playlist_id(value)
    if not pid:
        raise PlaylistError("Invalid ID or URL")
    if any(p["id"] == pid for p in load_playlists()):
        return {"id": pid, "added": False, "open": False, "task_id": None,
                "message": _share_existing(pid, account) if account else "Playlist already saved"}
    try:
        # Read with this profile's Deezer account first: a private playlist of its own works.
        info = fetch_deezer_playlist_info(pid, profiles=[account] if account else None)
    except RuntimeError as e:
        # Deezer answered with an error: no such playlist, or a private one of another account.
        raise PlaylistError("Deezer has no playlist with this ID that your Deezer account can read") from e
    if account:
        info["accounts"] = [account]
    add_entry(info)
    cache_cover(info)
    return {"id": pid, "added": True, "open": False, "task_id": None, "message": "Playlist added"}


def import_csv_for(filename, data, account) -> dict:
    """Imports a CSV export for this profile, and starts finding its tracks."""
    try:
        pid = crossplatform.add_csv(filename, data, accounts=[account] if account else None)
    except SourceError as e:
        raise PlaylistError(str(e)) from e
    task_id = _start_scan(pid, quick=True, title=f"Finding on Deezer: {playlist_title(pid)}")
    return {"id": pid, "task_id": task_id, "message": "Playlist imported: its tracks are being found on Deezer"}


@playlists_bp.post("/playlist/add")
def add_playlist():
    try:
        result = add_playlist_for(request.form.get("playlist_input", ""), _active())
    except PlaylistError as e:
        flash(str(e))
        return redirect(url_for("playlists.home"))
    flash(result["message"])
    return _open_playlist(result["id"]) if result["open"] else redirect(url_for("playlists.home"))


@playlists_bp.post("/playlist/import-csv")
def import_csv_playlist():
    upload = request.files.get("csv_file")
    if upload is None or not upload.filename:
        flash("Choose a CSV file to import")
        return redirect(url_for("playlists.home"))
    try:
        result = import_csv_for(upload.filename, upload.read(MAX_CSV_BYTES + 1), _active())
    except PlaylistError as e:
        flash(str(e))
        return redirect(url_for("playlists.home"))
    flash(result["message"])
    return _open_playlist(result["id"])


@playlists_bp.post("/playlist/<playlist_id>/source-match")
def source_match_route(playlist_id):
    """"Find on Deezer": picks the Deezer track of one imported track by hand."""
    if not crossplatform.parse_xp_id(playlist_id):
        return jsonify({"ok": False, "error": "Only imported playlists have source tracks"}), 400
    data = request.get_json(silent=True) or {}
    key = str(data.get("key") or "")
    choice = data.get("deezer_id")
    if choice not in (None, "auto") and not str(choice).isdigit():
        return jsonify({"ok": False, "error": "Invalid Deezer track"}), 400
    try:
        track = crossplatform.set_pick(playlist_id, key, None if choice is None else str(choice))
        row = rematch_track(playlist_id, track)
    except LookupError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Deezer did not answer: {e}"}), 502
    return jsonify({"ok": True, "row": row, "xp": crossplatform.summary(playlist_id)})


def delete_playlist_for(playlist_id, account) -> dict:
    """Removes the playlist from this profile. Saved for other profiles too, it
    stays for them; otherwise it is deleted. {"deleted", "complete", "message"}:
    `complete` is False when Navidrome may keep a copy it imported."""
    members = accounts_for(playlist_id)
    if account and members and account not in members:
        # Another profile's playlist: never deleted from here.
        raise PlaylistError("This playlist is not on this account")
    title = playlist_title(playlist_id)
    left_in_navidrome = " Navidrome keeps the copy it imported from the .m3u8: delete it there."
    if account in members and len(members) > 1:
        set_accounts(playlist_id, [a for a in members if a != account])
        complete = publish.remove_from(playlist_id, title, [account])
        return {"deleted": False, "complete": complete,
                "message": f"Playlist removed from {_label(account)}." + ("" if complete else left_in_navidrome)}
    complete = publish.remove_from(playlist_id, title, members)
    remove_entries([playlist_id])
    delete_playlist_cache(playlist_id)
    return {"deleted": True, "complete": complete, "message": "Playlist deleted." + ("" if complete else left_in_navidrome)}


@playlists_bp.post("/playlist/<playlist_id>/delete")
def delete_playlist(playlist_id):
    try:
        flash(delete_playlist_for(playlist_id, _active())["message"])
    except PlaylistError as e:
        flash(str(e))
    return redirect(url_for("playlists.home"))


@playlists_bp.post("/playlist/<playlist_id>/accounts")
def playlist_accounts_route(playlist_id):
    """The Navidrome accounts this playlist goes to."""
    body = request.get_json(silent=True) or {}
    wanted = body.get("accounts")
    if is_auto_id(playlist_id):
        return jsonify({"ok": False, "error": "A generated playlist belongs to its profile"}), 409
    own = set(account_context.own_profiles(g.get("user")))
    if not isinstance(wanted, list) or not wanted or any(a not in own for a in wanted):
        return jsonify({"ok": False, "error": "Choose at least one of your Navidrome accounts"}), 400
    if not any(p["id"] == playlist_id for p in load_playlists()):
        return jsonify({"ok": False, "error": "Playlist not found"}), 404
    members = accounts_for(playlist_id)
    wanted = wanted + [a for a in members if a not in own]  # other accounts' profiles keep it
    added = [a for a in wanted if a not in members]
    removed = [a for a in members if a not in wanted]
    set_accounts(playlist_id, wanted)
    title = playlist_title(playlist_id)
    if removed:
        publish.remove_from(playlist_id, title, removed)
    state = get_preview_state(playlist_id) or {}
    if added and isinstance(state.get("rows"), list):
        publish.publish(playlist_id, state.get("playlist_title") or title, state["rows"], accounts=added)
    return jsonify({"ok": True, "navidrome": publish.status(playlist_id)})


@playlists_bp.get("/playlist/<playlist_id>/navidrome")
def playlist_navidrome_route(playlist_id):
    """Where the playlist is in Navidrome, without reading it again from Deezer."""
    return jsonify({"ok": True, "navidrome": publish.status(playlist_id)})


@playlists_bp.post("/playlist/<playlist_id>/publish")
def publish_now_route(playlist_id):
    """Publishes again now, even unchanged: for a playlist edited in Navidrome."""
    state = get_preview_state(playlist_id) or {}
    if not isinstance(state.get("rows"), list):
        return jsonify({"ok": False, "error": "Scan this playlist first"}), 400
    publish.publish(playlist_id, state.get("playlist_title") or playlist_title(playlist_id), state["rows"], force=True)
    return jsonify({"ok": True, "navidrome": publish.status(playlist_id)})


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
    return jsonify({"task_id": _start_scan(playlist_id, quick=data.get("mode") == "quick")})


def _start_scan(playlist_id, quick, title=None):
    """Runs a scan as a task (Activity follows it) and returns its ID."""
    task_id = create_task(
        title or f"{'Quick' if quick else 'Full'} scan: {playlist_title(playlist_id)}",
        kind="scan",
        playlist_id=playlist_id,
        cancellable=True,
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
    return task_id


@playlists_bp.get("/playlist/<playlist_id>/preview")
def playlist_preview_route(playlist_id):
    try:
        data = build_playlist_preview(playlist_id)
        return jsonify({"ok": True, "playlist": data, "navidrome": publish.status(playlist_id)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@playlists_bp.post("/playlist/<playlist_id>/automation")
def update_playlist_automation(playlist_id):
    data = request.get_json(silent=True) or {}
    try:
        interval = max(1, int(data.get("auto_scan_interval_minutes") or 60))
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "The interval must be a number of minutes"}), 400
    pl = {"auto_scan_enabled": bool(data.get("auto_scan_enabled")), "auto_scan_interval_minutes": interval,
          "auto_download_after_scan": bool(data.get("auto_download_after_scan"))}
    found = []

    def change(entries):
        for entry in entries:
            if str(entry.get("id")) == playlist_id:
                entry.update(pl)
                found.append(entry)
        return entries

    modify_playlists(change)
    if not found:
        return jsonify({"error": "Playlist not found"}), 404
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

    account = my_download_account()
    if not deezer_dl.download_arl(account):
        return jsonify({"error": "No Deezer account for the downloads: add one in Settings → Deezer accounts."}), 400

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
                    enqueue_download("track", track_id, on_done=on_track_done, deezer_account=account)
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
