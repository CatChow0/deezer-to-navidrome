"""Devices signed in through the API, the Android app first: each has its own
token, sent as "Authorization: Bearer d2n_…".

Only a SHA-256 digest of the token is kept, in DATA_DIR/devices.json, with the
device's name, when it signed in and when it was last used. A token stops
working when its device is removed in Settings, or signs out, and for every
device of an account of this app when its password changes: each device keeps
its account's stamp at sign-in (core/users.stamp()), as the web sessions do."""
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from core import config, files

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
    files.write_json(_path(), data, private=True)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _stamp(user_id) -> str:
    from core import users

    user = users.get(user_id)
    return users.stamp(user) if user else ""


def _alive(device) -> bool:
    stamp = _stamp(device.get("user"))
    return bool(stamp) and hmac.compare_digest(str(device.get("stamp") or ""), stamp)


def public(device: dict) -> dict:
    """What the interface may show: never the digest."""
    return {k: device.get(k) for k in ("id", "name", "user", "created_at", "last_used_at", "last_ip")}


def create(name, ip="", user_id="", now=None) -> tuple:
    """A new device of an account of this app: (its token, shown once, its public record)."""
    now = int(now or time.time())
    name = " ".join(str(name or "").split())[:MAX_NAME] or "Device"
    token = PREFIX + secrets.token_urlsafe(32)
    device = {"id": secrets.token_hex(6), "name": name, "user": user_id, "token_sha256": _digest(token),
              "stamp": _stamp(user_id), "created_at": now, "last_used_at": now, "last_ip": ip or ""}
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
    digest = _digest(token)
    now = int(now or time.time())
    with _lock:
        data = _read()
        device = next((d for d in data["devices"] if hmac.compare_digest(str(d.get("token_sha256") or ""), digest)), None)
        if device is None or not _alive(device):
            return None
        if now - int(device.get("last_used_at") or 0) >= TOUCH_EVERY or (ip and device.get("last_ip") != ip):
            device["last_used_at"] = now
            device["last_ip"] = ip or device.get("last_ip") or ""
            _write(data)
        return public(device)


def list_devices(user_id) -> list:
    """The devices of this account still signed in, the last used first. Those
    signed in before a password changed can never sign in again: they are forgotten."""
    with _lock:
        data = _read()
        alive = [d for d in data["devices"] if _alive(d)]
        if len(alive) != len(data["devices"]):
            data["devices"] = alive
            _write(data)
    mine = [d for d in alive if d.get("user") == user_id]
    return [public(d) for d in sorted(mine, key=lambda d: d.get("last_used_at") or 0, reverse=True)]


def revoke(device_id, user_id) -> bool:
    """Only a device of this account."""
    with _lock:
        data = _read()
        kept = [d for d in data["devices"] if not (d.get("id") == device_id and d.get("user") == user_id)]
        if len(kept) == len(data["devices"]):
            return False
        data["devices"] = kept
        _write(data)
    return True


def revoke_all(user_id) -> int:
    """Every device of this account."""
    with _lock:
        data = _read()
        kept = [d for d in data["devices"] if d.get("user") != user_id]
        count = len(data["devices"]) - len(kept)
        if count:
            data["devices"] = kept
            _write(data)
    return count


def claim_unowned(user_id) -> int:
    """1.20: the devices signed in before accounts existed are the Super-Admin's,
    and stay signed in."""
    stamp = _stamp(user_id)
    with _lock:
        data = _read()
        orphans = [d for d in data["devices"] if not d.get("user")]
        for device in orphans:
            device.update(user=user_id, stamp=stamp)
        if orphans:
            _write(data)
    return len(orphans)
