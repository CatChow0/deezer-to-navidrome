"""Navidrome accounts: one per Navidrome user this app works for.

What is shared stays shared (library, downloads, folders, Deezer account). What
belongs to a user (their playlists in Navidrome, history, mixes) follows the
account. The first account, nd1, is made at start-up from the existing install
and keeps everything it had.

Kept in DATA_DIR/navidrome_accounts.json. The password or API key is encrypted
(core/crypto.py) and only leaves this module in clear to talk to Navidrome:
public() never includes it."""
import json
import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from core import config, crypto, files

logger = logging.getLogger(__name__)

AUTH_TYPES = ("password", "apikey")
PUBLISH_MODES = ("m3u8", "api")
MAX_LABEL = 40
_lock = threading.RLock()


class AccountError(ValueError):
    """Shown to the user as it is."""


def _path() -> Path:
    return Path(config.DATA_DIR) / "navidrome_accounts.json"


def _empty() -> dict:
    return {"version": 1, "default": None, "next": 1, "accounts": []}


def _read() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    except (OSError, ValueError) as e:
        raise AccountError(f"navidrome_accounts.json could not be read: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise AccountError("navidrome_accounts.json is not in the expected format.")
    return data


def _write(data: dict) -> None:
    files.write_json(_path(), data, private=True)


def clean_url(value) -> str:
    """http(s)://host[:port][/path], without a trailing slash or "/rest"."""
    text = (value or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AccountError("The server address must start with http:// or https://")
    if parts.username or parts.password:
        raise AccountError("Put the user name and password in their own fields, not in the address.")
    if parts.query or parts.fragment:
        raise AccountError("The server address cannot have a query (?…) or a fragment (#…).")
    path = re.sub(r"/rest/?$", "", parts.path.rstrip("/"))
    return f"{parts.scheme}://{parts.netloc}{path}"


def _clean_label(value, fallback) -> str:
    label = " ".join(str(value or "").split())
    if len(label) > MAX_LABEL:
        raise AccountError(f"The name can have {MAX_LABEL} characters at most.")
    return label or fallback


# --- Reading ---------------------------------------------------------------------

def list_accounts() -> list:
    with _lock:
        return [dict(a) for a in _read()["accounts"]]


def get(account_id):
    for account in list_accounts():
        if account["id"] == account_id:
            return account
    return None


def default_id():
    with _lock:
        data = _read()
    ids = [a["id"] for a in data["accounts"]]
    return data["default"] if data["default"] in ids else (ids[0] if ids else None)


def accounts_of(user_id) -> list:
    """The profiles of an account of this app: the Navidrome accounts it owns."""
    from core import users

    return [a for a in list_accounts() if users.effective_owner(a.get("owner")) == user_id]


def set_owner(account_ids, owner) -> None:
    """Gives these Navidrome accounts to another account of this app."""
    with _lock:
        data = _read()
        for account in data["accounts"]:
            if account["id"] in account_ids:
                account["owner"] = owner
        _write(data)


def public(account) -> dict:
    """Everything the interface may show: never the secret."""
    last = account.get("last_test") or {}
    return {
        "id": account["id"],
        "label": account["label"],
        "url": account["url"],
        "username": account["username"],
        "auth_type": account["auth_type"],
        "has_secret": bool(account.get("secret")),
        "navidrome_user_id": account.get("navidrome_user_id") or "",
        "publish_mode": account["publish_mode"],
        "deezer_account": account.get("deezer_account") or "",
        "owner": account.get("owner") or "",
        "is_default": account["id"] == default_id(),
        "complete": bool(account["url"] and account["username"] and account.get("secret")),
        "legacy": bool(account.get("legacy")),
        "created_at": account["created_at"],
        "updated_at": account["updated_at"],
        "last_test": {k: last.get(k) for k in ("ok", "at", "error", "server_version", "admin", "libraries",
                                                "api_keys", "navidrome_user")} if last else None,
    }


def credentials(account_id) -> dict:
    """In clear, for talking to Navidrome. Not for the interface."""
    account = get(account_id)
    if account is None:
        raise AccountError("Unknown Navidrome account.")
    return {"url": account["url"], "username": account["username"], "auth_type": account["auth_type"],
            "secret": crypto.decrypt(account.get("secret") or "")}


# --- Changes ---------------------------------------------------------------------

def same_server(a, b) -> bool:
    """Same host and port: http to https, or another path, is still the same
    server; another host may be anyone's, and must not get a saved password."""
    def where(url):
        parts = urlsplit(url or "")
        return (parts.hostname or "").lower(), parts.port or {"http": 80, "https": 443}.get(parts.scheme)

    first, second = where(a), where(b)
    if first[0] != second[0]:
        return False
    # http and https on their default ports: the same server.
    return first[1] == second[1] or {first[1], second[1]} == {80, 443}


def _check_unique(data, username, url, ignore=None):
    for account in data["accounts"]:
        if account["id"] != ignore and username and account["username"].lower() == username.lower() \
                and account["url"].lower() == url.lower():
            raise AccountError(f"The Navidrome user {username} already has an account here ({account['label']}).")


def _deezer_account(value) -> str:
    """"" (the default Deezer account) or a Deezer account that exists."""
    from core import deezer_accounts

    value = str(value or "").strip()
    if value and deezer_accounts.get(value) is None:
        raise AccountError("Unknown Deezer account.")
    return value


def create(fields: dict, now=None) -> dict:
    now = int(now or time.time())
    url = clean_url(fields.get("url"))
    username = str(fields.get("username") or "").strip()
    auth_type = fields.get("auth_type") or "password"
    secret = str(fields.get("secret") or "")
    if not url:
        raise AccountError("Enter the address of your Navidrome.")
    if not username:
        raise AccountError("Enter the Navidrome user name.")
    if auth_type not in AUTH_TYPES:
        raise AccountError("Unknown way of signing in.")
    if not secret:
        raise AccountError("Enter the password or the API key of this Navidrome user.")
    with _lock:
        data = _read()
        _check_unique(data, username, url)
        number = int(data.get("next") or 1)
        account = {
            "id": f"nd{number}",
            "label": _clean_label(fields.get("label"), username),
            "url": url,
            "username": username,
            "auth_type": auth_type,
            "secret": crypto.encrypt(secret),
            "navidrome_user_id": "",
            # New accounts can only publish through the API: a .m3u8 file always
            # belongs to Navidrome's first admin.
            "publish_mode": "api",
            "deezer_account": _deezer_account(fields.get("deezer_account")),
            "owner": str(fields.get("owner") or ""),
            "legacy": False,
            "created_at": now,
            "updated_at": now,
            "last_test": None,
        }
        data["accounts"].append(account)
        data["next"] = number + 1
        if not data.get("default"):
            data["default"] = account["id"]
        _write(data)
    return dict(account)


def update(account_id, fields: dict, now=None) -> dict:
    """Only the fields given change. An empty secret keeps the current one."""
    now = int(now or time.time())
    with _lock:
        data = _read()
        account = next((a for a in data["accounts"] if a["id"] == account_id), None)
        if account is None:
            raise AccountError("Unknown Navidrome account.")
        changed_identity = False
        if "label" in fields:
            account["label"] = _clean_label(fields["label"], account["username"] or account["id"])
        if "url" in fields:
            url = clean_url(fields["url"])
            if not url:
                raise AccountError("Enter the address of your Navidrome.")
            if account.get("secret") and not same_server(url, account["url"]) and not fields.get("secret"):
                # The saved password would otherwise be sent to the new address.
                raise AccountError("The address is another server: enter the password again.")
            changed_identity |= url != account["url"]
            account["url"] = url
        if "username" in fields:
            username = str(fields["username"] or "").strip()
            if not username:
                raise AccountError("Enter the Navidrome user name.")
            changed_identity |= username.lower() != account["username"].lower()
            account["username"] = username
        if "auth_type" in fields:
            if fields["auth_type"] not in AUTH_TYPES:
                raise AccountError("Unknown way of signing in.")
            if fields["auth_type"] != account["auth_type"] and not fields.get("secret"):
                raise AccountError("Enter the new password or API key.")
            account["auth_type"] = fields["auth_type"]
        if fields.get("secret"):
            account["secret"] = crypto.encrypt(str(fields["secret"]))
            changed_identity = True
        if "deezer_account" in fields:
            account["deezer_account"] = _deezer_account(fields["deezer_account"])
        _check_unique(data, account["username"], account["url"], ignore=account_id)
        if changed_identity:
            # Another user or server: what was learnt about the old one no longer holds.
            account["navidrome_user_id"] = ""
            account["last_test"] = None
        account["updated_at"] = now
        _write(data)
        return dict(account)


_removing = set()


def delete(account_id) -> None:
    """Removes an account. Its playlists first leave its Navidrome, while its
    password is still known, and its tracks in quarantine go to the install's
    account; then its history is kept aside."""
    with _lock:
        data = _read()
        if not any(a["id"] == account_id for a in data["accounts"]):
            raise AccountError("Unknown Navidrome account.")
        if account_id in _removing:
            raise AccountError("This Navidrome account is being removed already.")
        # Those being removed at this moment count as gone: two removals at once
        # must not leave no account at all.
        if len([a for a in data["accounts"] if a["id"] not in _removing]) <= 1:
            raise AccountError("The last Navidrome account cannot be removed.")
        _removing.add(account_id)
    try:
        _before_removal(account_id)
        with _lock:
            data = _read()
            data["accounts"] = [a for a in data["accounts"] if a["id"] != account_id]
            if data["accounts"] and data.get("default") == account_id:
                data["default"] = data["accounts"][0]["id"]
            _write(data)
    finally:
        with _lock:
            _removing.discard(account_id)
    _after_removal(account_id)


def _heir(account_id):
    """Who takes over what a removed account leaves: the install's account, else
    the default one, else the first."""
    others = [a for a in list_accounts() if a["id"] != account_id]
    legacy = next((a["id"] for a in others if a.get("legacy")), None)
    default = default_id()
    return legacy or (default if default != account_id else None) or (others[0]["id"] if others else None)


def _before_removal(account_id) -> None:
    from core import mix_builder, publish

    try:
        report = publish.forget_account(account_id)
        logger.info("Playlists of %s: %s", account_id, report)
    except Exception as e:
        logger.error("The playlists of %s could not all leave Navidrome: %s", account_id, e)
    heir = _heir(account_id)
    if heir:
        try:
            mix_builder.forget_account(account_id, heir)
        except Exception as e:
            logger.error("The quarantine of %s could not go to %s: %s", account_id, heir, e)


def _after_removal(account_id) -> None:
    """Its listening history goes to backups/removed-accounts/, and its
    ListenBrainz token stops working. A history that cannot be moved stays
    where it is."""
    from core import stats_db, stats_ingest

    try:
        archived = stats_db.archive(account_id)
        if archived:
            logger.info("The history of %s was moved to %s", account_id, archived)
    except Exception as e:
        logger.error("The history of %s could not be moved, it stays in place: %s", account_id, e)
    try:
        stats_ingest.forget_token(account_id)
    except Exception as e:
        logger.error("The ListenBrainz token of %s could not be removed: %s", account_id, e)


def forget_deezer_account(deezer_id) -> None:
    """The profiles that chose a Deezer account now removed go back to the
    default one."""
    with _lock:
        data = _read()
        changed = False
        for account in data["accounts"]:
            if account.get("deezer_account") == deezer_id:
                account["deezer_account"] = ""
                changed = True
        if changed:
            _write(data)


def owner_fallback():
    """Who a playlist saved before 1.16, without accounts, belongs to: the
    account made from the install, else the default one."""
    accounts = list_accounts()
    legacy = next((a["id"] for a in accounts if a.get("legacy")), None)
    return legacy or default_id()


def set_publish_mode(account_id, mode) -> None:
    if mode not in PUBLISH_MODES:
        raise AccountError("Unknown way of publishing playlists.")
    with _lock:
        data = _read()
        account = next((a for a in data["accounts"] if a["id"] == account_id), None)
        if account is None:
            raise AccountError("Unknown Navidrome account.")
        account["publish_mode"] = mode
        account["updated_at"] = int(time.time())
        _write(data)


def set_default(account_id) -> None:
    with _lock:
        data = _read()
        if not any(a["id"] == account_id for a in data["accounts"]):
            raise AccountError("Unknown Navidrome account.")
        data["default"] = account_id
        _write(data)


def record_test(account_id, result: dict, navidrome_user=None, now=None) -> dict:
    """Keeps what the last test learnt; a known Navidrome user ties the account to
    its plays and stars."""
    with _lock:
        data = _read()
        account = next((a for a in data["accounts"] if a["id"] == account_id), None)
        if account is None:
            raise AccountError("Unknown Navidrome account.")
        account["last_test"] = {**{k: result.get(k) for k in ("ok", "error", "server_version", "admin", "libraries",
                                                                "api_keys")},
                                "at": int(now or time.time()),
                                "navidrome_user": navidrome_user["user_name"] if navidrome_user else None}
        if navidrome_user:
            account["navidrome_user_id"] = navidrome_user["id"]
        _write(data)
        return dict(account)


# --- Start-up ---------------------------------------------------------------------

def ensure_initial(now=None):
    """The first account, from the install as it was: it keeps the .m3u8
    playlists, the history and the mixes. Without credentials yet: the existing
    features never needed any. Returns it when it was just made."""
    from core import navidrome_db

    now = int(now or time.time())
    with _lock:
        data = _read()
        if data["accounts"]:
            return None
        users = navidrome_db.users() or []
        only = users[0] if len(users) == 1 else None
        account = {
            "id": "nd1",
            "label": "Navidrome",
            "url": "",
            "username": only["user_name"] if only else "",
            "auth_type": "password",
            "secret": "",
            "navidrome_user_id": only["id"] if only else "",
            "publish_mode": "m3u8",
            "legacy": True,
            "created_at": now,
            "updated_at": now,
            "last_test": None,
        }
        data.update(accounts=[account], default="nd1", next=2)
        _write(data)
        return dict(account)
