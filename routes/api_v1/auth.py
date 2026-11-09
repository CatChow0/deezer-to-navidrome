"""Signing in from a device, and the devices signed in."""
from flask import g, request

from core import auth, devices
from routes import auth as sign_in
from routes.api_v1 import API_VERSION, api_v1_bp, body, error, ok, replaces


def _mode() -> str:
    if auth.auth_disabled():
        return "disabled"
    return "required" if auth.account_exists() else "setup"


def _signed_in(data):
    token, device = devices.create(data.get("device"), request.remote_addr or "")
    return ok({"token": token, "device": device, "username": auth.username()}, status=201)


@api_v1_bp.get("/auth/status")
def auth_status():
    """Public: that this is the app, and how to get in. "disabled": no sign-in
    (DISABLE_AUTH, a proxy is expected to ask); "setup": no account yet."""
    return ok({"service": "deezer-to-navidrome", "api": API_VERSION, "auth": _mode()})


@api_v1_bp.post("/auth/login")
@replaces(sign_in.login)
def auth_login():
    """The account's username and password, and a name for this device. The
    same limit on failed attempts as the web sign-in."""
    if auth.auth_disabled():
        return error("auth_disabled", "Sign-in is turned off on this server (DISABLE_AUTH): no token is needed.", 409)
    if not auth.account_exists():
        return error("setup_needed", "This server has no account yet: create it first.", 409)
    data = body()
    name = str(data.get("username") or "").strip()
    keys = [f"user:{name.lower()}", f"ip:{request.remote_addr}"]
    wait = max(auth.limiter.retry_after(k) for k in keys)
    if wait:
        response = error("too_many_attempts", f"Too many attempts, try again in {wait} s.", 429, retry_after=wait)
        response.headers["Retry-After"] = str(wait)
        return response
    if not auth.check_credentials(name, str(data.get("password") or "")):
        for k in keys:
            auth.limiter.failure(k)
        return error("wrong_credentials", "Wrong username or password.", 401)
    for k in keys:
        auth.limiter.success(k)
    return _signed_in(data)


@api_v1_bp.post("/auth/setup")
@replaces(sign_in.setup)
def auth_setup():
    """First run from the app: the account, then this device's token. Only while
    the server has no account, as the web setup page."""
    if auth.auth_disabled():
        return error("auth_disabled", "Sign-in is turned off on this server (DISABLE_AUTH).", 409)
    if auth.account_exists():
        return error("account_exists", "This server already has an account: sign in.", 409)
    data = body()
    name, password = str(data.get("username") or "").strip(), str(data.get("password") or "")
    if not name or len(password) < auth.MIN_PASSWORD:
        return error("invalid", f"Choose a username and a password of at least {auth.MIN_PASSWORD} characters.", 400)
    auth.set_account(name, password)
    return _signed_in(data)


@api_v1_bp.post("/auth/logout")
@replaces(sign_in.logout)
def auth_logout():
    """Signs this device out: its token stops working."""
    device = getattr(g, "device", None)
    if device:
        devices.revoke(device["id"])
    return ok({"signed_out": bool(device)})


@api_v1_bp.get("/devices")
def devices_list():
    current = getattr(g, "device", None)
    found = devices.list_devices()
    for device in found:
        device["current"] = bool(current and current["id"] == device["id"])
    return ok({"devices": found})


@api_v1_bp.delete("/devices/<device_id>")
def device_revoke(device_id):
    if not devices.revoke(device_id):
        return error("not_found", "No such device.", 404)
    return ok({"revoked": device_id})
