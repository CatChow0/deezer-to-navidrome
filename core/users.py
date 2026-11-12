"""The accounts of this app: a Super-Admin (the one made at first start, or
from APP_USERNAME / APP_PASSWORD), Admins and Standard users, in
DATA_DIR/users.json.

Each owns its Navidrome accounts (its profiles) and Deezer accounts; what one
may do to another is decided by can() alone. Passwords and recovery codes are
kept as hashes; the API token and the CatBoard webhook URL encrypted."""
import hmac
import os
import secrets
import threading
import time
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from core import config, crypto, files

SUPERADMIN, ADMIN, STANDARD = "superadmin", "admin", "standard"
ROLES = (SUPERADMIN, ADMIN, STANDARD)
MIN_PASSWORD = 8
RECOVERY_FILE = "recovery-code.txt"
RECOVERY_SECONDS = 15 * 60
_lock = threading.RLock()
_dummy = []
# DISABLE_AUTH with no account yet: one person behind the proxy, who has the
# whole app, and owns what has no owner (as before 1.20).
OPEN = {"id": "", "username": "", "role": SUPERADMIN, "open": True}


class UserError(Exception):
    """Shown to the user as it is."""


def _path() -> Path:
    return Path(config.DATA_DIR) / "users.json"


def _read() -> dict:
    data = files.read_json(_path(), {})
    users = data.get("users") if isinstance(data, dict) else None
    return {"version": 1, "users": [u for u in users if isinstance(u, dict)] if isinstance(users, list) else []}


def _write(data) -> None:
    files.write_json(_path(), data, private=True)


def from_env() -> bool:
    return bool(os.environ.get("APP_USERNAME") and os.environ.get("APP_PASSWORD"))


def _with_env(user):
    """The Super-Admin's name and password come from the environment when set."""
    if user and user["role"] == SUPERADMIN and from_env():
        return {**user, "username": os.environ["APP_USERNAME"].strip(), "from_env": True}
    return user


def _env_superadmin() -> dict:
    """The Super-Admin of APP_USERNAME / APP_PASSWORD before anything was saved for it."""
    return {"id": "u1", "username": os.environ["APP_USERNAME"].strip(), "role": SUPERADMIN, "password_hash": "",
            "recovery_hash": "", "must_change": False, "created_at": 0}


def _stored(data):
    users = data["users"]
    if from_env() and not any(u["role"] == SUPERADMIN for u in users):
        users = [_env_superadmin(), *users]
    return users


def list_users() -> list:
    return [_with_env(u) for u in _stored(_read())]


def get(user_id):
    return next((u for u in list_users() if u["id"] == user_id), None)


def superadmin():
    return next((u for u in list_users() if u["role"] == SUPERADMIN), None)


def exists() -> bool:
    return superadmin() is not None


def effective_owner(owner_id) -> str:
    """Who owns a Navidrome or Deezer account: the one saved, else the
    Super-Admin (accounts made before any account of this app, as nd1 on a
    first start)."""
    return owner_id or (superadmin() or OPEN)["id"]


def public(user) -> dict:
    return {"id": user["id"], "username": user["username"], "role": user["role"],
            "must_change": bool(user.get("must_change")), "from_env": bool(user.get("from_env")),
            "created_at": user.get("created_at")}


def _same(a, b) -> bool:
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


def _named(users, name):
    name = str(name or "").strip().lower()
    return next((u for u in users if _same(u["username"].lower(), name)), None) if name else None


def by_name(name):
    return _named(list_users(), name)


def check(name, password):
    """The account these credentials open, or None. A wrong name costs as long
    as a wrong password: the time taken does not tell which one was wrong."""
    user = by_name(name)
    if user and user.get("from_env"):
        return user if password and _same(password, os.environ["APP_PASSWORD"]) else None
    stored = (user or {}).get("password_hash")
    if not stored or not password:
        if not _dummy:
            _dummy.append(generate_password_hash(secrets.token_hex(16)))
        check_password_hash(_dummy[0], password or "")
        return None
    return user if check_password_hash(stored, password) else None


def stamp(user) -> str:
    """Changes with the account's name and password: a new password signs out
    its other sessions and devices. Keyed, so it shows nothing of the hash."""
    from core import auth

    source = os.environ["APP_PASSWORD"] if user.get("from_env") else user.get("password_hash") or ""
    return hmac.new(auth.secret_key().encode(), f"{user['id']}\0{user['username']}\0{source}".encode(),
                    "sha256").hexdigest()[:32]


# --- What one account may do to another ------------------------------------------

def can(actor, action, target=None) -> bool:
    """actions: "admin" (server settings, user list, shared limits), "edit"
    (a target's name, password, recovery code and accounts), "delete",
    "promote" (Standard to Admin), "demote" (Admin to Standard)."""
    if not actor:
        return False
    role = actor["role"]
    if action == "admin":
        return role in (SUPERADMIN, ADMIN)
    if not target:
        return False
    mine, theirs = actor["id"] == target["id"], target["role"]
    if action == "edit":
        return mine or role == SUPERADMIN or (role == ADMIN and theirs == STANDARD)
    if action == "delete":
        return not mine and theirs != SUPERADMIN and (role == SUPERADMIN or (role == ADMIN and theirs == STANDARD))
    if action == "promote":
        return theirs == STANDARD and role in (SUPERADMIN, ADMIN)
    if action == "demote":
        return theirs == ADMIN and role == SUPERADMIN
    return False


# --- Changes -------------------------------------------------------------------

def _check_password(password) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise UserError(f"Choose a password of at least {MIN_PASSWORD} characters.")


def _clean_name(data, name, ignore=None) -> str:
    name = " ".join(str(name or "").split())[:64]
    if not name:
        raise UserError("Choose a username.")
    other = _named([u for u in data["users"] if u["id"] != ignore], name)
    if other:
        raise UserError(f"The username {name} is taken.")
    return name


def _change(user_id, change):
    with _lock:
        data = _read()
        data["users"] = _stored(data)
        user = next((u for u in data["users"] if u["id"] == user_id), None)
        if user is None:
            raise UserError("Unknown account.")
        result = change(data, user)
        _write(data)
        return result


def create(username, password, role=STANDARD, must_change=True, now=None) -> dict:
    """An account. One made by an Admin has a temporary password: its user
    chooses their own at the first sign-in, and gets their recovery code then."""
    if role not in ROLES:
        raise UserError("Unknown privilege.")
    _check_password(password)
    with _lock:
        data = _read()
        data["users"] = _stored(data)
        if role == SUPERADMIN and any(u["role"] == SUPERADMIN for u in data["users"]):
            raise UserError("There is one Super-Admin.")
        number = max([int(u["id"][1:]) for u in data["users"] if u["id"][1:].isdigit()] or [0]) + 1
        user = {"id": f"u{number}", "username": _clean_name(data, username), "role": role,
                "password_hash": generate_password_hash(password), "recovery_hash": "",
                "must_change": bool(must_change), "created_at": int(now or time.time())}
        data["users"].append(user)
        _write(data)
    return public(user)


def rename(user_id, username) -> None:
    def change(data, user):
        if _with_env(user).get("from_env"):
            raise UserError("This account is set by APP_USERNAME / APP_PASSWORD: change it there.")
        user["username"] = _clean_name(data, username, ignore=user_id)
    _change(user_id, change)


def set_role(user_id, role) -> None:
    if role not in (ADMIN, STANDARD):
        raise UserError("Unknown privilege.")

    def change(data, user):
        if user["role"] == SUPERADMIN:
            raise UserError("The Super-Admin stays Super-Admin.")
        user["role"] = role
    _change(user_id, change)


def set_password(user_id, password, must_change=False) -> None:
    _check_password(password)

    def change(data, user):
        if _with_env(user).get("from_env"):
            raise UserError("This account is set by APP_USERNAME / APP_PASSWORD: change it there.")
        user["password_hash"] = generate_password_hash(password)
        user["must_change"] = bool(must_change)
    _change(user_id, change)


def new_recovery_code(user_id) -> str:
    """A new recovery code, shown once; the old one stops working."""
    code = "-".join(secrets.token_hex(3).upper() for _ in range(4))

    def change(data, user):
        user["recovery_hash"] = generate_password_hash(code)
    _change(user_id, change)
    return code


def recover(name, code, password) -> str:
    """A new password with the account's recovery code. The code is used up:
    the new one is returned, to be shown once."""
    _check_password(password)
    user = by_name(name)
    stored = (user or {}).get("recovery_hash")
    if not user or not stored or user.get("from_env") or not check_password_hash(stored, str(code or "").strip().upper()):
        raise UserError("This username and recovery code do not match.")
    set_password(user["id"], password)
    return new_recovery_code(user["id"])


def write_superadmin_code(now=None) -> Path:
    """The Super-Admin's way back in: a one-time code in DATA_DIR, which only
    someone with access to the server can read, valid RECOVERY_SECONDS."""
    if not superadmin() or superadmin().get("from_env"):
        raise UserError("No Super-Admin password to recover here.")
    path = Path(config.DATA_DIR) / RECOVERY_FILE
    expires = int(now or time.time()) + RECOVERY_SECONDS
    files.write_atomic(path, f"{secrets.token_hex(8).upper()}\n{expires}\n", private=True)
    return path


def recover_superadmin(code, password, now=None) -> str:
    _check_password(password)
    path = Path(config.DATA_DIR) / RECOVERY_FILE
    try:
        saved, expires = path.read_text(encoding="utf-8").split()[:2]
    except (OSError, ValueError):
        raise UserError("No recovery code is waiting: ask for one first.") from None
    if int(now or time.time()) > int(expires):
        path.unlink(missing_ok=True)
        raise UserError("This recovery code expired: ask for a new one.")
    if not _same(saved, str(code or "").strip().upper()):
        raise UserError("This recovery code is wrong.")
    path.unlink(missing_ok=True)
    set_password(superadmin()["id"], password)
    return new_recovery_code(superadmin()["id"])


# --- CatBoard and downloads, per account -------------------------------------------

def set_field(user_id, name, value) -> None:
    """api_token and webhook_url are kept encrypted; catboard_profiles and
    download_deezer as they are."""
    stored = crypto.encrypt(value) if name in ("api_token", "webhook_url") and value else value

    def change(data, user):
        user[name] = stored
    _change(user_id, change)


def token_from_env(user) -> bool:
    """API_TOKEN is the Super-Admin's token, as before 1.20."""
    return bool(user and user["role"] == SUPERADMIN and os.environ.get("API_TOKEN", "").strip())


def field(user, name, default=""):
    if name == "api_token" and token_from_env(user):
        return os.environ["API_TOKEN"].strip()
    value = (user or {}).get(name, default)
    if name in ("api_token", "webhook_url") and value:
        try:
            return crypto.decrypt(value)
        except crypto.DecryptError:
            return ""
    return value


def by_token(token):
    """The account whose API token this is, or None."""
    if not token:
        return None
    return next((u for u in list_users() if field(u, "api_token") and _same(field(u, "api_token"), token)), None)


# --- Start-up -------------------------------------------------------------------

def ensure_initial(now=None) -> bool:
    """1.20: the account of older versions becomes the Super-Admin, with its API
    token and webhook. True when it was made now."""
    with _lock:
        data = _read()
        if any(u["role"] == SUPERADMIN for u in data["users"]):
            return False
        name, hashed = config.load_secret("app_username"), config.load_secret("app_password_hash")
        if not (from_env() or (name and hashed)):
            return False
        user = {"id": "u1", "username": name or os.environ.get("APP_USERNAME", "").strip(), "role": SUPERADMIN,
                "password_hash": hashed or "", "recovery_hash": "", "must_change": False,
                "created_at": int(now or time.time())}
        token, webhook = config.load_secret("api_token"), config.load_secret("catboard_webhook_url")
        if token:
            user["api_token"] = crypto.encrypt(token)
        if webhook:
            user["webhook_url"] = crypto.encrypt(webhook)
        data["users"].insert(0, user)
        _write(data)
    return True


def remove(user_id) -> None:
    """The account's record only: what it owned is the caller's (routes/users.py)."""
    with _lock:
        data = _read()
        target = next((u for u in data["users"] if u["id"] == user_id), None)
        if target is None:
            raise UserError("Unknown account.")
        if target["role"] == SUPERADMIN:
            raise UserError("The Super-Admin cannot be removed.")
        data["users"] = [u for u in data["users"] if u["id"] != user_id]
        _write(data)
