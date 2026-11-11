"""Signing in from a device, and the devices signed in."""
from flask import g, request, session

from core import auth, devices, users
from routes import auth as sign_in
from routes.api_v1 import API_VERSION, api_v1_bp, body, error, ok, replaces


def _mode() -> str:
    if auth.auth_disabled():
        return "disabled"
    return "required" if auth.account_exists() else "setup"


def _signed_in(data, user, **extra):
    token, device = devices.create(data.get("device"), request.remote_addr or "", user["id"])
    user = users.get(user["id"])
    return ok({"token": token, "device": device, "username": user["username"], "user": users.public(user), **extra},
              status=201)


@api_v1_bp.get("/auth/status")
def auth_status():
    """Public: that this is the app, and how to get in. "disabled": no sign-in
    (DISABLE_AUTH, a proxy is expected to ask); "setup": no account yet."""
    return ok({"service": "deezer-to-navidrome", "api": API_VERSION, "auth": _mode()})


@api_v1_bp.get("/me")
def me():
    """The account signed in: its role, and whether it must choose its password."""
    user = sign_in.me()
    return ok({"user": users.public(user) if user else None, "is_admin": users.can(user, "admin")})


@api_v1_bp.post("/auth/login")
@replaces(sign_in.login)
def auth_login():
    """An account's username and password, and a name for this device. The
    same limit on failed attempts as the web sign-in. An account with a
    temporary password gets `user.must_change`: it then calls
    /auth/first-password before anything else."""
    if auth.auth_disabled():
        return error("auth_disabled", "Sign-in is turned off on this server (DISABLE_AUTH): no token is needed.", 409)
    if not auth.account_exists():
        return error("setup_needed", "This server has no account yet: create it first.", 409)
    data = body()
    user, wait = auth.attempt_login(str(data.get("username") or ""), str(data.get("password") or ""),
                                    request.remote_addr)
    if wait:
        response = error("too_many_attempts", f"Too many attempts, try again in {wait} s.", 429, retry_after=wait)
        response.headers["Retry-After"] = str(wait)
        return response
    if not user:
        return error("wrong_credentials", "Wrong username or password.", 401)
    return _signed_in(data, user)


@api_v1_bp.post("/auth/setup")
@replaces(sign_in.setup)
def auth_setup():
    """First run from the app: the Super-Admin, then this device's token and
    the account's recovery code, shown once. Only while the server has no account."""
    if auth.auth_disabled():
        return error("auth_disabled", "Sign-in is turned off on this server (DISABLE_AUTH).", 409)
    if auth.account_exists():
        return error("account_exists", "This server already has an account: sign in.", 409)
    data = body()
    try:
        user = users.create(data.get("username"), str(data.get("password") or ""), users.SUPERADMIN, must_change=False)
    except users.UserError as e:
        return error("invalid", str(e), 400)
    return _signed_in(data, user, recovery_code=users.new_recovery_code(user["id"]))


@api_v1_bp.post("/auth/first-password")
@replaces(sign_in.first_password)
def auth_first_password():
    """The password of an account made by an Admin, chosen by its user; answers
    the recovery code, shown once. This device stays signed in."""
    user = sign_in.me()
    try:
        users.set_password(user["id"], str(body().get("password") or ""))
    except users.UserError as e:
        return error("invalid", str(e), 400)
    devices.revoke_all(user["id"])
    data = {"device": (g.get("device") or {}).get("name")}
    return _signed_in(data, user, recovery_code=users.new_recovery_code(user["id"]))


@api_v1_bp.post("/auth/forgot")
@replaces(sign_in.forgot)
def auth_forgot():
    """A new password with the account's recovery code; answers the new
    recovery code, shown once. The Super-Admin may use the code from /auth/forgot/superadmin."""
    data = body()
    code, message, status = sign_in.recover(data.get("username"), data.get("code"), data.get("password"),
                                            request.remote_addr)
    if message:
        return error("too_many_attempts" if status == 429 else "invalid", message, status)
    return ok({"recovery_code": code})


@api_v1_bp.post("/auth/forgot/superadmin")
@replaces(sign_in.forgot_superadmin)
def auth_forgot_superadmin():
    """Writes a one-time code in the server's data folder, for the Super-Admin."""
    try:
        path = users.write_superadmin_code()
    except users.UserError as e:
        return error("invalid", str(e), 400)
    return ok({"file": path.name, "minutes": users.RECOVERY_SECONDS // 60})


@api_v1_bp.post("/auth/logout")
@replaces(sign_in.logout)
def auth_logout():
    """Signs this device out: its token stops working. Signed in with the web
    session instead, that session ends."""
    device = getattr(g, "device", None)
    if device:
        devices.revoke(device["id"], device.get("user"))
        return ok({"signed_out": True})
    signed_out = bool(session.get("user_id"))
    session.clear()
    return ok({"signed_out": signed_out})


@api_v1_bp.get("/devices")
def devices_list():
    current = getattr(g, "device", None)
    found = devices.list_devices(sign_in.me()["id"])
    for device in found:
        device["current"] = bool(current and current["id"] == device["id"])
    return ok({"devices": found})


@api_v1_bp.delete("/devices/<device_id>")
def device_revoke(device_id):
    if not devices.revoke(device_id, sign_in.me()["id"]):
        return error("not_found", "No such device.", 404)
    return ok({"revoked": device_id})
