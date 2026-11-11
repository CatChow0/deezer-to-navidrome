"""The accounts of this app, for the Admins (Settings → Users), and the clears
each account may run on its own profiles. What one may do to another is
core/users.can()'s; every route here asks it."""
from flask import Blueprint, jsonify, request

from core import deezer_accounts, devices, nd_accounts, users
from routes.auth import admin_only, me, refused

users_bp = Blueprint("users", __name__)


def _row(user) -> dict:
    actor = me()
    return {**users.public(user),
            "navidrome_accounts": len(nd_accounts.accounts_of(user["id"])),
            "deezer_accounts": sum(1 for a in deezer_accounts.list_accounts()
                                   if users.effective_owner(a.get("owner")) == user["id"]),
            "can": {action: users.can(actor, action, user) for action in ("edit", "delete", "promote", "demote")}}


def _state():
    return {"ok": True, "users": [_row(u) for u in users.list_users()], "me": me()["id"]}


def _target(user_id, action):
    target = users.get(user_id)
    if target is None:
        return None, (jsonify({"ok": False, "error": "Unknown account."}), 404)
    if not users.can(me(), action, target):
        return None, refused("You cannot change this account.")
    return target, None


def _fail(e):
    return jsonify({"ok": False, "error": str(e)}), 400


@users_bp.get("/api/users")
@admin_only
def list_route():
    return jsonify(_state())


@users_bp.post("/api/users")
@admin_only
def create_route():
    """A Standard or Admin account, with a temporary password its user changes
    at the first sign-in."""
    body = request.get_json(silent=True) or {}
    role = body.get("role") or users.STANDARD
    if role not in (users.STANDARD, users.ADMIN):
        return _fail("Choose Standard or Admin.")
    try:
        created = users.create(body.get("username"), str(body.get("password") or ""), role)
    except users.UserError as e:
        return _fail(e)
    return jsonify({**_state(), "created": created["id"]})


@users_bp.patch("/api/users/<user_id>")
def update_route(user_id):
    """Its username, and its privilege: Standard to Admin, or back (Super-Admin only)."""
    target, error = _target(user_id, "edit")
    if error:
        return error
    body = request.get_json(silent=True) or {}
    role = body.get("role")
    if role and role != target["role"]:
        if not users.can(me(), "promote" if role == users.ADMIN else "demote", target):
            return refused("You cannot give this account that privilege.")
    try:
        if body.get("username") is not None:
            users.rename(user_id, body["username"])
        if role and role != target["role"]:
            users.set_role(user_id, role)
    except users.UserError as e:
        return _fail(e)
    return jsonify(_state())


@users_bp.post("/api/users/<user_id>/password")
def password_route(user_id):
    """A temporary password, set by an Admin: its user chooses their own at the
    next sign-in, and every device of the account is signed out."""
    target, error = _target(user_id, "edit")
    if error:
        return error
    if target["id"] == me()["id"]:
        return refused("Change your own password in Sign-in and other apps.", 400)
    try:
        users.set_password(user_id, str((request.get_json(silent=True) or {}).get("password") or ""), must_change=True)
    except users.UserError as e:
        return _fail(e)
    devices.revoke_all(user_id)
    return jsonify(_state())


@users_bp.post("/api/users/<user_id>/recovery")
def recovery_route(user_id):
    """A new recovery code for this account, shown once, to give to its user."""
    _, error = _target(user_id, "edit")
    return error or jsonify({"ok": True, "code": users.new_recovery_code(user_id)})


@users_bp.delete("/api/users/<user_id>")
def delete_route(user_id):
    """Its Navidrome and Deezer accounts go to `heir` when one is named, else
    they are removed with it (one that cannot be, the last of its kind, goes to
    the Super-Admin). Its devices are signed out."""
    target, error = _target(user_id, "delete")
    if error:
        return error
    heir = (request.get_json(silent=True) or {}).get("heir") or request.args.get("heir")
    if heir and (heir == user_id or users.get(heir) is None):
        return _fail("Choose another account to give them to.")
    owned_nd = [a["id"] for a in nd_accounts.accounts_of(user_id)]
    owned_dz = [a["id"] for a in deezer_accounts.list_accounts() if a.get("owner") == user_id]
    keep_for = heir or users.superadmin()["id"]
    if heir:
        nd_accounts.set_owner(owned_nd, heir)
        deezer_accounts.set_owner(owned_dz, heir)
    else:
        for account_id in owned_nd:
            try:
                nd_accounts.delete(account_id)
            except nd_accounts.AccountError:
                nd_accounts.set_owner([account_id], keep_for)
        for account_id in owned_dz:
            try:
                deezer_accounts.delete(account_id)
            except deezer_accounts.DeezerAccountsError:
                deezer_accounts.set_owner([account_id], keep_for)
    deezer_accounts.forget_user(user_id)
    devices.revoke_all(user_id)
    users.remove(user_id)
    return jsonify(_state())


# --- Clears of your own profiles -----------------------------------------------------

PROFILE_CLEARS = ("matches", "playlists", "covers")


@users_bp.post("/api/profiles/clear/<what>")
def clear_profiles_route(what):
    """Reset data limited to the asker's own profiles: the match results or the
    covers of the playlists only they have, or their playlists (one another
    account's profile also has stays for it)."""
    from core import config
    from core.deezer import load_playlists
    from routes.playlists import delete_playlist_for

    if what not in PROFILE_CLEARS:
        return _fail("Choose matches, playlists or covers.")
    mine = {a["id"] for a in nd_accounts.accounts_of(me()["id"])}
    cleared = 0
    for playlist in load_playlists():
        profiles = set(playlist.get("accounts") or [])
        if not profiles & mine:
            continue
        if what == "playlists":
            for profile in profiles & mine:
                delete_playlist_for(playlist["id"], profile)
            cleared += 1
        elif profiles <= mine:
            if what == "matches":
                config.forget_preview(playlist["id"])
            else:
                (config.COVERS_DIR / f"{playlist['id']}.jpg").unlink(missing_ok=True)
            cleared += 1
    return jsonify({"ok": True, "cleared": cleared, "what": what})
