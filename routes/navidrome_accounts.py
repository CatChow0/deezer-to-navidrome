"""Navidrome accounts in Settings, and the account each device works on.

No answer ever carries a password or an API key: nd_accounts.public() leaves
them out, and test errors are redacted by core/subsonic."""
from flask import Blueprint, jsonify, request, session

from core import account_context, crypto, navidrome_db, nd_accounts, subsonic

navidrome_accounts_bp = Blueprint("navidrome_accounts", __name__)
BASE = "/api/navidrome"


def _state():
    users = navidrome_db.users()
    return {
        "ok": True,
        "accounts": [nd_accounts.public(a) for a in nd_accounts.list_accounts()],
        "active": account_context.resolve(request, session),
        "default": nd_accounts.default_id(),
        "encryption": {"source": crypto.key_source()},
        "navidrome_db": {"mounted": users is not None, "users": [u["user_name"] for u in users or []]},
    }


def _error(e, status=400):
    return jsonify({"ok": False, "error": str(e)}), status


def _fields():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    allowed = ("label", "url", "username", "auth_type", "secret")
    return {key: body[key] for key in allowed if key in body}


@navidrome_accounts_bp.get(f"{BASE}/accounts")
def accounts():
    return jsonify(_state())


@navidrome_accounts_bp.post(f"{BASE}/accounts")
def create():
    fields = _fields()
    if fields is None:
        return _error("Expected an account")
    try:
        account = nd_accounts.create(fields)
    except nd_accounts.AccountError as e:
        return _error(e)
    return jsonify({**_state(), "created": account["id"]})


@navidrome_accounts_bp.patch(f"{BASE}/accounts/<account_id>")
def update(account_id):
    fields = _fields()
    if fields is None:
        return _error("Expected an account")
    try:
        nd_accounts.update(account_id, fields)
    except nd_accounts.AccountError as e:
        return _error(e, 404 if nd_accounts.get(account_id) is None else 400)
    return jsonify(_state())


@navidrome_accounts_bp.delete(f"{BASE}/accounts/<account_id>")
def delete(account_id):
    try:
        nd_accounts.delete(account_id)
    except nd_accounts.AccountError as e:
        return _error(e, 404 if nd_accounts.get(account_id) is None else 409)
    if session.get(account_context.SESSION_KEY) == account_id:
        session.pop(account_context.SESSION_KEY, None)
    return jsonify(_state())


@navidrome_accounts_bp.post(f"{BASE}/accounts/<account_id>/default")
def make_default(account_id):
    try:
        nd_accounts.set_default(account_id)
    except nd_accounts.AccountError as e:
        return _error(e, 404)
    return jsonify(_state())


def _run_test(creds):
    result = subsonic.test_connection(creds["url"], creds["username"], creds["auth_type"], creds["secret"])
    user = navidrome_db.find_user(creds["username"]) if result["ok"] else None
    if result["ok"] and navidrome_db.mounted() and user is None:
        result["warning"] = ("This user is not in the mounted Navidrome database: its plays and stars "
                             "cannot be read from it.")
    result["navidrome_user"] = user["user_name"] if user else None
    return result, user


@navidrome_accounts_bp.post(f"{BASE}/accounts/<account_id>/test")
def test_saved(account_id):
    """Tests the account as saved, and keeps what was learnt."""
    try:
        creds = nd_accounts.credentials(account_id)
    except nd_accounts.AccountError as e:
        return _error(e, 404)
    except crypto.DecryptError:
        return _error("The password of this account was encrypted with another key: enter it again.", 409)
    if not (creds["url"] and creds["username"] and creds["secret"]):
        return _error("Enter the address, the user name and the password of this account first.")
    result, user = _run_test(creds)
    nd_accounts.record_test(account_id, result, user if result["ok"] else None)
    return jsonify({**_state(), "test": result})


@navidrome_accounts_bp.post(f"{BASE}/accounts/test")
def test_unsaved():
    """Tests what is typed in the form, before saving. Editing an account, an
    empty password field means the saved one."""
    body = request.get_json(silent=True) or {}
    creds = {"url": "", "username": str(body.get("username") or "").strip(),
             "auth_type": body.get("auth_type") or "password", "secret": str(body.get("secret") or "")}
    try:
        creds["url"] = nd_accounts.clean_url(body.get("url"))
        if not creds["secret"] and body.get("id"):
            saved = nd_accounts.credentials(body["id"])
            if saved["auth_type"] == creds["auth_type"]:
                creds["secret"] = saved["secret"]
    except nd_accounts.AccountError as e:
        return _error(e)
    except crypto.DecryptError:
        return _error("The saved password was encrypted with another key: enter it again.", 409)
    if creds["auth_type"] not in nd_accounts.AUTH_TYPES:
        return _error("Unknown way of signing in.")
    if not (creds["url"] and creds["username"] and creds["secret"]):
        return _error("Enter the address, the user name and the password first.")
    result, _ = _run_test(creds)
    return jsonify({"ok": True, "test": result})


@navidrome_accounts_bp.post(f"{BASE}/active")
def choose_active():
    """This browser now works on this account. The mobile app sends the
    X-Navidrome-Account header instead."""
    body = request.get_json(silent=True) or {}
    try:
        account_context.select(session, str(body.get("id") or ""))
    except nd_accounts.AccountError as e:
        return _error(e, 404)
    return jsonify(_state())
