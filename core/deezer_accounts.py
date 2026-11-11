"""Deezer accounts: one per Deezer user whose favorites and mixes the app reads.

Each Navidrome profile picks the account its releases and Deezer mixes come
from, the default one otherwise. One account, marked "Use for download",
fetches the files for everyone (the default one when none is marked).

Kept in DATA_DIR/deezer_accounts.json. The ARL is encrypted (core/crypto.py)
and never leaves this module in clear except to sign in to Deezer. An account
can also come from DEEZER_ARL or DEEZER_ARL_PREMIUM: its ARL is then read
there and never saved. The first account, dz1, keeps the files of the single
account of older versions (releases.json, release_prefs.json) and the IDs of
the mixes it followed."""
import json
import os
import threading
import time
from pathlib import Path

from core import config, crypto, files

ENV_MAIN = "DEEZER_ARL"
ENV_DOWNLOAD = "DEEZER_ARL_PREMIUM"
MAX_LABEL = 40
_lock = threading.RLock()


class DeezerAccountsError(ValueError):
    """Shown to the user as it is."""


def _path() -> Path:
    return Path(config.DATA_DIR) / "deezer_accounts.json"


def exists() -> bool:
    return _path().exists()


def _empty() -> dict:
    return {"version": 1, "default": None, "download": None, "next": 1, "accounts": []}


def _read() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    except (OSError, ValueError) as e:
        raise DeezerAccountsError(f"deezer_accounts.json could not be read: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise DeezerAccountsError("deezer_accounts.json is not in the expected format.")
    return data


def _write(data: dict) -> None:
    files.write_json(_path(), data, private=True)


def _label(value, fallback) -> str:
    label = " ".join(str(value or "").split())
    if len(label) > MAX_LABEL:
        raise DeezerAccountsError(f"The name can have {MAX_LABEL} characters at most.")
    return label or fallback


# --- Reading ---------------------------------------------------------------------

def list_accounts() -> list:
    with _lock:
        return [dict(a) for a in _read()["accounts"]]


def get(account_id):
    return next((a for a in list_accounts() if a["id"] == account_id), None)


def default_id():
    with _lock:
        data = _read()
    ids = [a["id"] for a in data["accounts"]]
    return data.get("default") if data.get("default") in ids else (ids[0] if ids else None)


def download_id():
    """The account that downloads: the one marked, else the default one."""
    with _lock:
        data = _read()
    ids = [a["id"] for a in data["accounts"]]
    return data.get("download") if data.get("download") in ids else default_id()


def arl(account_id) -> str:
    """In clear, to sign in to Deezer. Not for the interface."""
    account = get(account_id)
    if account is None:
        return ""
    if account.get("env"):
        return os.environ.get(account["env"], "").strip()
    return crypto.decrypt(account.get("arl") or "").strip()


def public(account) -> dict:
    """What the interface may show: never the ARL."""
    return {
        "id": account["id"],
        "label": account["label"],
        "name": account.get("name") or "",
        "user_id": account.get("user_id") or "",
        "country": account.get("country") or "",
        "premium": bool(account.get("premium")),
        "format": account.get("format") or "",
        "from_env": account.get("env") or "",
        "has_arl": bool(account.get("arl") or (account.get("env") and os.environ.get(account["env"]))),
        "is_default": account["id"] == default_id(),
        "is_download": account["id"] == download_id(),
        "checked_at": account.get("checked_at") or 0,
        "error": account.get("error") or "",
    }


# --- Changes ---------------------------------------------------------------------

def _apply_check(account: dict, result: dict, now: int) -> None:
    """A failed check (an expired ARL, Deezer out of reach) only records why: the
    account keeps who it is, so that a user cannot be added twice meanwhile."""
    account["checked_at"] = now
    if not result.get("connected"):
        account["error"] = result.get("error") or "Deezer did not accept this ARL."
        return
    account.update(name=result.get("name") or account.get("name") or "", user_id=result.get("user_id") or "",
                   country=result.get("country") or "", premium=bool(result.get("premium")),
                   format=result.get("format") or "", error="")


def _signed_in(arl_value) -> dict:
    """Signs in with this ARL, raising the reason Deezer refused it."""
    from core.deezer_account import check_arl

    result = check_arl(arl_value)
    if not result.get("connected"):
        raise DeezerAccountsError(result.get("error") or "Deezer did not accept this ARL.")
    return result


def _same_user(data, user_id, ignore=None):
    for account in data["accounts"]:
        if account["id"] != ignore and user_id and account.get("user_id") == user_id:
            raise DeezerAccountsError(f"This Deezer user already has an account here ({account['label']}).")


def create(fields: dict, now=None, check=True) -> dict:
    now = int(now or time.time())
    arl_value = str(fields.get("arl") or "").strip()
    if not arl_value:
        raise DeezerAccountsError("Paste the ARL of this Deezer account.")
    result = _signed_in(arl_value) if check else {"connected": True}
    with _lock:
        data = _read()
        _same_user(data, result.get("user_id"))
        number = int(data.get("next") or 1)
        account = {"id": f"dz{number}", "label": "", "arl": crypto.encrypt(arl_value), "env": "",
                   "legacy": False, "created_at": now, "updated_at": now}
        _apply_check(account, result, now)
        account["label"] = _label(fields.get("label"), account.get("name") or f"Deezer {number}")
        data["accounts"].append(account)
        data["next"] = number + 1
        if not data.get("default"):
            data["default"] = account["id"]
        _write(data)
    _forget(account["id"])
    return dict(account)


def update(account_id, fields: dict, now=None) -> dict:
    """Only what is given changes. A new ARL is checked by signing in."""
    now = int(now or time.time())
    new_arl = str(fields.get("arl") or "").strip()
    result = _signed_in(new_arl) if new_arl else None
    with _lock:
        data = _read()
        account = next((a for a in data["accounts"] if a["id"] == account_id), None)
        if account is None:
            raise DeezerAccountsError("Unknown Deezer account.")
        if "label" in fields:
            account["label"] = _label(fields["label"], account.get("name") or account_id)
        if new_arl:
            if account.get("env"):
                raise DeezerAccountsError(f"This ARL is set by {account['env']}: change it there.")
            _same_user(data, result.get("user_id"), ignore=account_id)
            account["arl"] = crypto.encrypt(new_arl)
            _apply_check(account, result, now)
        account["updated_at"] = now
        _write(data)
    if new_arl:
        _forget(account_id)
    return dict(account)


def delete(account_id) -> None:
    with _lock:
        data = _read()
        account = next((a for a in data["accounts"] if a["id"] == account_id), None)
        if account is None:
            raise DeezerAccountsError("Unknown Deezer account.")
        if len(data["accounts"]) == 1:
            raise DeezerAccountsError("The last Deezer account cannot be removed.")
        data["accounts"] = [a for a in data["accounts"] if a["id"] != account_id]
        if data.get("default") == account_id:
            data["default"] = data["accounts"][0]["id"]
        if data.get("download") == account_id:
            data["download"] = None
        _write(data)
    _forget(account_id)
    # Its release feed goes, and the profiles that read it read the default one.
    # An ID is never given again, so nothing else will ever read these files.
    from core import nd_accounts, releases

    releases.forget_account(account_id)
    nd_accounts.forget_deezer_account(account_id)


def set_default(account_id) -> None:
    _set_role("default", account_id)


def set_download(account_id) -> None:
    _set_role("download", account_id)
    from core import deezer_dl

    deezer_dl.forget_sessions()


def _set_role(role, account_id) -> None:
    with _lock:
        data = _read()
        if not any(a["id"] == account_id for a in data["accounts"]):
            raise DeezerAccountsError("Unknown Deezer account.")
        data[role] = account_id
        _write(data)


def check(account_id, now=None) -> dict:
    """Signs in again and keeps what Deezer says about the account."""
    from core.deezer_account import account_status

    now = int(now or time.time())
    result = account_status(account_id)
    with _lock:
        data = _read()
        account = next((a for a in data["accounts"] if a["id"] == account_id), None)
        if account is None:
            raise DeezerAccountsError("Unknown Deezer account.")
        _apply_check(account, result, now)
        _write(data)
        return dict(account)


def _forget(account_id) -> None:
    try:
        from core import deezer_account, deezer_dl

        deezer_account.forget_session(account_id)
        deezer_dl.forget_sessions()
    except Exception:
        pass


# --- Start-up --------------------------------------------------------------------

def _from_env(data, env, now):
    number = int(data.get("next") or 1)
    account = {"id": f"dz{number}", "label": "Deezer" if env == ENV_MAIN else "Downloads", "arl": "", "env": env,
               "legacy": number == 1, "created_at": now, "updated_at": now}
    data["accounts"].append(account)
    data["next"] = number + 1
    return account


def ensure_initial(stored_main="", stored_download="", now=None) -> int:
    """The accounts of an older install, or of the environment. The single
    account becomes dz1, the default; the premium one used for the downloads
    stays the account that downloads. Returns how many were made."""
    now = int(now or time.time())
    made = 0
    with _lock:
        fresh = not exists()
        data = _read()
        envs = {a.get("env") for a in data["accounts"]}
        if os.environ.get(ENV_MAIN, "").strip() and ENV_MAIN not in envs:
            account = _from_env(data, ENV_MAIN, now)
            data["default"] = data.get("default") or account["id"]
            made += 1
        elif fresh and stored_main:
            number = int(data.get("next") or 1)
            account = {"id": f"dz{number}", "label": "Deezer", "arl": crypto.encrypt(stored_main), "env": "",
                       "legacy": number == 1, "created_at": now, "updated_at": now}
            data["accounts"].append(account)
            data["next"] = number + 1
            data["default"] = data.get("default") or account["id"]
            made += 1
        if os.environ.get(ENV_DOWNLOAD, "").strip() and ENV_DOWNLOAD not in envs:
            account = _from_env(data, ENV_DOWNLOAD, now)
            data["download"] = account["id"]
            data["default"] = data.get("default") or account["id"]
            made += 1
        elif fresh and stored_download and stored_download != stored_main:
            # The same ARL twice was one account doing both: it stays one.
            number = int(data.get("next") or 1)
            account = {"id": f"dz{number}", "label": "Downloads", "arl": crypto.encrypt(stored_download), "env": "",
                       "legacy": False, "created_at": now, "updated_at": now}
            data["accounts"].append(account)
            data["next"] = number + 1
            data["download"] = account["id"]
            data["default"] = data.get("default") or account["id"]
            made += 1
        if made or fresh:
            _write(data)
    return made
