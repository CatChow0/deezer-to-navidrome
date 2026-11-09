"""Deezer accounts in Settings, and what each profile gets from its Deezer account:
the release feed of its favorite artists and its mixes (Flow, made for you).

No answer ever carries an ARL: deezer_accounts.public() leaves it out."""
import threading

from flask import Blueprint, jsonify, request, session

from core import account_context, deezer_accounts
from core.config import create_task, push_task_event
from core.deezer import follow_mix, give_to_account, load_playlists, mix_id
from core.deezer_account import DeezerAccountError, account_status, available_mixes
from core.releases import is_stale, load_prefs, load_releases, lock_for, refresh_hours, refresh_releases, set_muted
from core.webhook import notify

account_bp = Blueprint("account", __name__)


def _profile():
    return account_context.resolve(request, session)


def _deezer_account():
    """The Deezer account of this browser's profile, else the default one."""
    return account_context.deezer_account(request, session)


def _download_status():
    """What the account used for the downloads can do."""
    from core import deezer_dl

    account_id = deezer_accounts.download_id()
    account = deezer_accounts.get(account_id) if account_id else None
    info = deezer_dl.account_info()
    return {
        "account": account_id,
        "label": account["label"] if account else "",
        "connected": bool(info.get("connected")),
        "premium": bool(info.get("premium")),
        "format": info.get("format"),
        "country": info.get("country"),
        "error": info.get("error"),
    }


def _accounts_state():
    return {
        "ok": True,
        "accounts": [deezer_accounts.public(a) for a in deezer_accounts.list_accounts()],
        "default": deezer_accounts.default_id(),
        "download": deezer_accounts.download_id(),
        "profile_account": _deezer_account(),
    }


def _error(e, status=400):
    return jsonify({"ok": False, "error": str(e)}), status


def _fields():
    body = request.get_json(silent=True)
    return {k: body[k] for k in ("label", "arl") if k in body} if isinstance(body, dict) else None


@account_bp.get("/api/deezer/accounts")
def accounts_route():
    # Accounts never checked (moved from an older install): signed in once, so
    # the list shows who they are and what they can download.
    for account in deezer_accounts.list_accounts():
        if not account.get("checked_at") and deezer_accounts.arl(account["id"]):
            try:
                deezer_accounts.check(account["id"])
            except deezer_accounts.DeezerAccountsError:
                pass
    state = _accounts_state()
    state["downloads"] = _download_status()
    return jsonify(state)


@account_bp.post("/api/deezer/accounts")
def add_account_route():
    fields = _fields()
    if fields is None:
        return _error("Expected an account")
    try:
        account = deezer_accounts.create(fields)
    except deezer_accounts.DeezerAccountsError as e:
        return _error(e)
    return jsonify({**_accounts_state(), "created": account["id"]})


@account_bp.patch("/api/deezer/accounts/<account_id>")
def edit_account_route(account_id):
    fields = _fields()
    if fields is None:
        return _error("Expected an account")
    try:
        deezer_accounts.update(account_id, fields)
    except deezer_accounts.DeezerAccountsError as e:
        return _error(e, 404 if deezer_accounts.get(account_id) is None else 400)
    return jsonify(_accounts_state())


@account_bp.delete("/api/deezer/accounts/<account_id>")
def remove_account_route(account_id):
    try:
        deezer_accounts.delete(account_id)
    except deezer_accounts.DeezerAccountsError as e:
        return _error(e, 404 if deezer_accounts.get(account_id) is None else 409)
    return jsonify(_accounts_state())


@account_bp.post("/api/deezer/accounts/<account_id>/default")
def default_account_route(account_id):
    try:
        deezer_accounts.set_default(account_id)
    except deezer_accounts.DeezerAccountsError as e:
        return _error(e, 404)
    return jsonify(_accounts_state())


@account_bp.post("/api/deezer/accounts/<account_id>/download")
def download_account_route(account_id):
    try:
        deezer_accounts.set_download(account_id)
    except deezer_accounts.DeezerAccountsError as e:
        return _error(e, 404)
    state = _accounts_state()
    state["downloads"] = _download_status()
    return jsonify(state)


@account_bp.post("/api/deezer/accounts/<account_id>/check")
def check_account_route(account_id):
    try:
        deezer_accounts.check(account_id)
    except deezer_accounts.DeezerAccountsError as e:
        return _error(e, 404)
    return jsonify(_accounts_state())


@account_bp.get("/api/deezer/account")
def account_route():
    """The Deezer account of this browser's profile: whether it is connected."""
    account_id = _deezer_account()
    if not account_id:
        return jsonify({"ok": True, "connected": False, "name": "", "error": None, "premium": False,
                        "downloads": _download_status()})
    status = account_status(account_id)
    return jsonify({"ok": True, **status, "account": account_id, "downloads": _download_status()})


@account_bp.get("/api/deezer/mixes")
def mixes_route():
    deezer_account = _deezer_account()
    try:
        found = available_mixes(deezer_account)
    except DeezerAccountError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    profile = _profile()
    followed = {p["id"] for p in load_playlists() if not profile or not p.get("accounts") or profile in p["accounts"]}
    for mix in found["mixes"]:
        mix["id"] = mix_id(mix["kind"], mix["source_id"], deezer_account)
        mix["followed"] = mix["id"] in followed
    for playlist in found["playlists"]:
        playlist["followed"] = playlist["id"] in followed
    return jsonify({"ok": True, **found})


@account_bp.post("/api/deezer/mixes/follow")
def follow_mix_route():
    data = request.get_json(silent=True) or {}
    kind, source_id = data.get("kind"), str(data.get("source_id") or "")
    if kind not in ("stl", "flow") or not source_id:
        return jsonify({"ok": False, "error": "Unknown mix"}), 400
    profile = _profile()
    try:
        pid, added = follow_mix(kind, source_id, str(data.get("title") or "Mix"),
                                accounts=[profile] if profile else None, deezer_account=_deezer_account())
    except DeezerAccountError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not added and profile:
        added = give_to_account(pid, profile)
    return jsonify({"ok": True, "id": pid, "added": added})


@account_bp.get("/api/releases")
def releases_route():
    """The feed of the Deezer account of this browser's profile. An app with the
    API token has no profile: it gets the default one's."""
    account_id = _deezer_account()
    account = deezer_accounts.get(account_id) if account_id else None
    return jsonify({
        "ok": True,
        "connected": bool(account_id and deezer_accounts.arl(account_id)),
        "deezer_account": {"id": account_id, "label": account["label"], "name": account.get("name") or ""} if account else None,
        "refresh_hours": refresh_hours(),
        "muted": load_prefs(account_id)["muted"],
        **load_releases(account_id),
    })


@account_bp.post("/api/releases/mute")
def mute_artist_route():
    data = request.get_json(silent=True) or {}
    artist_id = str(data.get("artist_id") or "")
    if not artist_id.isdigit():
        return jsonify({"ok": False, "error": "Unknown artist"}), 400
    prefs = set_muted(artist_id, str(data.get("name") or ""), bool(data.get("muted")), account=_deezer_account())
    notify("releases.updated", reason="muted")
    return jsonify({"ok": True, "muted": prefs["muted"]})


def start_release_refresh(title="Release feed refresh", account=None):
    """Runs the refresh of one account's feed in the background unless one is
    already running for it; returns the task ID or None."""
    account = account or deezer_accounts.default_id()
    lock = lock_for(account)
    if not lock.acquire(blocking=False):
        return None
    task_id = create_task(title, kind="releases", cancellable=True)

    def runner():
        try:
            feed = refresh_releases(
                progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                    task_id, message=message, progress=progress, stage=stage
                ),
                account=account,
            )
            push_task_event(
                task_id,
                f"{len(feed['releases'])} releases from {feed['artists']} artists",
                stage="done",
                progress=100,
                done=True,
            )
            notify("releases.updated", releases=len(feed["releases"]), artists=feed["artists"])
        except Exception as e:
            push_task_event(task_id, f"Release feed failed: {e}", stage="error", done=True, error=True)
        finally:
            lock.release()

    threading.Thread(target=runner, daemon=True).start()
    return task_id


def accounts_with_stale_feeds() -> list:
    """The Deezer accounts some profile reads its releases from, whose feed is
    old. For the scheduler."""
    from core import nd_accounts

    used = {account_context.deezer_account_of(a["id"]) for a in nd_accounts.list_accounts()}
    used.add(deezer_accounts.default_id())
    return [a for a in used if a and deezer_accounts.arl(a) and is_stale(a)]


@account_bp.post("/api/releases/refresh")
def refresh_releases_route():
    account_id = _deezer_account()
    if not account_id or not deezer_accounts.arl(account_id):
        return jsonify({"ok": False, "error": "Add a Deezer account in Settings → Deezer accounts first"}), 400
    label = deezer_accounts.get(account_id)["label"]
    task_id = start_release_refresh(f"Release feed refresh: {label}", account=account_id)
    if task_id is None:
        return jsonify({"ok": False, "error": "This release feed is already refreshing"}), 409
    return jsonify({"ok": True, "task_id": task_id})
