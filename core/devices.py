"""Devices signed in through the API, the Android app first: each has its own
token, sent as "Authorization: Bearer d2n_…".

Only a SHA-256 digest of the token is kept, in DATA_DIR/devices.json, with the
device's name, when it signed in and when it was last used. A token stops
working when its device is removed in Settings, or signs out, and for every
device when the account's password changes: each device keeps the account
stamp of its sign-in (core/auth.session_stamp()), as the web sessions do."""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from core import config

PREFIX = "d2n_"
MAX_NAME = 60
TOUCH_EVERY = 60  # seconds: "last used" is written at most this often
_lock = threading.RLock()


def _path() -> Path:
    return Path(config.DATA_DIR) / "devices.json"


def _read() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Missing or unreadable: no device is signed in, each signs in again.
        return {"version": 1, "devices": []}
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return {"version": 1, "devices": []}
    return data


def _write(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.part")
    partial.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        partial.chmod(0o600)
    except OSError:
        pass
    os.replace(partial, path)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _stamp() -> str:
    from core import auth

    return auth.session_stamp()


def public(device: dict) -> dict:
    """What the interface may show: never the digest."""
    return {k: device.get(k) for k in ("id", "name", "created_at", "last_used_at", "last_ip")}


def create(name, ip="", now=None) -> tuple:
    """A new device: (its token, shown once, its public record)."""
    now = int(now or time.time())
    name = " ".join(str(name or "").split())[:MAX_NAME] or "Device"
    token = PREFIX + secrets.token_urlsafe(32)
    device = {"id": secrets.token_hex(6), "name": name, "token_sha256": _digest(token), "stamp": _stamp(),
              "created_at": now, "last_used_at": now, "last_ip": ip or ""}
    with _lock:
        data = _read()
        data["devices"].append(device)
        _write(data)
    return token, public(device)


def verify(header, ip="", now=None):
    """The device whose token this Authorization header carries, or None."""
    sent = str(header or "").strip()
    if sent[:7].lower() != "bearer ":
        return None
    token = sent[7:].strip()
    if not token.startswith(PREFIX):
        return None
    digest, stamp = _digest(token), _stamp()
    now = int(now or time.time())
    with _lock:
        data = _read()
        device = next((d for d in data["devices"] if hmac.compare_digest(str(d.get("token_sha256") or ""), digest)), None)
        if device is None or not hmac.compare_digest(str(device.get("stamp") or ""), stamp):
            return None
        if now - int(device.get("last_used_at") or 0) >= TOUCH_EVERY or (ip and device.get("last_ip") != ip):
            device["last_used_at"] = now
            device["last_ip"] = ip or device.get("last_ip") or ""
            _write(data)
        return public(device)


def list_devices() -> list:
    """The devices still signed in, the last used first. Those signed in before
    the password changed can never sign in again: they are forgotten."""
    stamp = _stamp()
    with _lock:
        data = _read()
        alive = [d for d in data["devices"] if d.get("stamp") == stamp]
        if len(alive) != len(data["devices"]):
            data["devices"] = alive
            _write(data)
    return [public(d) for d in sorted(alive, key=lambda d: d.get("last_used_at") or 0, reverse=True)]


def revoke(device_id) -> bool:
    with _lock:
        data = _read()
        kept = [d for d in data["devices"] if d.get("id") != device_id]
        if len(kept) == len(data["devices"]):
            return False
        data["devices"] = kept
        _write(data)
    return True


def revoke_all() -> int:
    with _lock:
        data = _read()
        count = len(data["devices"])
        if count:
            data["devices"] = []
            _write(data)
    return count
