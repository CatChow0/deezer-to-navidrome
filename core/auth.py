"""Sign-in for the web interface and an API token for other apps (CatBoard).

One account. Its credentials come from APP_USERNAME / APP_PASSWORD when set,
otherwise from the first-run setup page (password hashed in secrets.json).
DISABLE_AUTH=true turns all of it off, for setups where a reverse proxy
already asks for a login. The API token only opens the read-only routes
other apps need (release feed, library check)."""
import hmac
import os
import secrets
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

from core.config import load_secret, save_secret, secret_from_env

MIN_PASSWORD = 8

# Routes the API token may call (method, path).
TOKEN_ROUTES = {("GET", "/api/releases"), ("POST", "/search/library-check"), ("GET", "/api/version")}


def auth_disabled():
    return os.environ.get("DISABLE_AUTH", "").strip().lower() in ("1", "true", "yes")


def secret_key():
    """Flask session key: SECRET_KEY, else a random one kept in secrets.json."""
    key = os.environ.get("SECRET_KEY", "").strip()
    if key and key != "change-me":
        return key
    key = load_secret("flask_secret_key")
    if not key:
        key = secrets.token_hex(32)
        save_secret("flask_secret_key", key)
    return key


# --- Account -------------------------------------------------------------------

def account_from_env():
    return bool(os.environ.get("APP_USERNAME") and os.environ.get("APP_PASSWORD"))


def username():
    return os.environ.get("APP_USERNAME", "").strip() if account_from_env() else load_secret("app_username")


def account_exists():
    return account_from_env() or bool(load_secret("app_username") and load_secret("app_password_hash"))


_dummy_hash = []


def _same(a: str, b: str) -> bool:
    # Bytes: compare_digest refuses str holding anything but ASCII ("Hélène").
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def check_credentials(name, password):
    if not account_exists() or not name or not password:
        return False
    name_ok = _same(name.strip().lower(), username().lower())
    if account_from_env():
        return _same(password, os.environ["APP_PASSWORD"]) and name_ok
    stored = load_secret("app_password_hash")
    if not name_ok or not stored:
        # The same work as a real check, so the time taken does not tell
        # whether the username was right.
        if not _dummy_hash:
            _dummy_hash.append(generate_password_hash(secrets.token_hex(16)))
        check_password_hash(_dummy_hash[0], password)
        return False
    return check_password_hash(stored, password)


def set_account(name, password):
    save_secret("app_username", name.strip())
    save_secret("app_password_hash", generate_password_hash(password))


def session_stamp():
    """Changes with the account, so a new password signs out the other sessions.
    A keyed digest: the session cookie is readable, it must not carry any part
    of the password hash."""
    source = os.environ["APP_PASSWORD"] if account_from_env() else (load_secret("app_password_hash") or "")
    return hmac.new(secret_key().encode(), f"{username()}\0{source}".encode(), "sha256").hexdigest()[:32]


# --- API token -----------------------------------------------------------------

def api_token():
    return load_secret("api_token")


def token_from_env():
    return secret_from_env("api_token")


def new_api_token():
    token = secrets.token_urlsafe(32)
    save_secret("api_token", token)
    return token


def token_ok(header, method, path):
    token = api_token()
    if not token or (method, path) not in TOKEN_ROUTES:
        return False
    sent = (header or "").removeprefix("Bearer ").strip()
    return bool(sent) and hmac.compare_digest(sent.encode(), token.encode())


# --- Failed sign-ins -----------------------------------------------------------

class LoginLimiter:
    """After 5 failures in 15 min a key waits 30 s, doubling up to 15 min."""

    MAX_KEYS = 5000

    def __init__(self, max_failures=5, window=900, base_block=30, max_block=900):
        self.max_failures, self.window, self.base_block, self.max_block = max_failures, window, base_block, max_block
        self._entries = {}
        self._lock = threading.Lock()

    def retry_after(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return 0
            return max(0, int(entry.get("blocked_until", 0) - time.time() + 0.999))

    def failure(self, key):
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if not entry or now - entry["first"] > self.window:
                entry = {"first": now, "count": 0, "blocks": 0}
            entry["count"] += 1
            if entry["count"] >= self.max_failures:
                entry["blocked_until"] = now + min(self.max_block, self.base_block * 2 ** entry["blocks"])
                entry["blocks"] += 1
            self._entries[key] = entry
            # forget old entries now and then, and never keep more than MAX_KEYS
            if len(self._entries) > 1000:
                self._entries = {k: v for k, v in self._entries.items()
                                 if now - v["first"] < self.window or v.get("blocked_until", 0) > now}
            if len(self._entries) > self.MAX_KEYS:
                newest = sorted(self._entries.items(), key=lambda kv: kv[1]["first"])[-self.MAX_KEYS:]
                self._entries = dict(newest)

    def success(self, key):
        with self._lock:
            self._entries.pop(key, None)


limiter = LoginLimiter()
# Every address at once, on one username: far more attempts allowed, so that
# someone guessing from the internet cannot lock the owner out with a few tries.
user_limiter = LoginLimiter(max_failures=50)


def attempt_login(name, password, ip):
    """(ok, wait): a sign-in checked against the limits. wait > 0: refused
    without checking, try again in that many seconds."""
    name = (name or "").strip()[:256]
    pair = [f"ip:{ip}", f"user-ip:{name.lower()}|{ip}"]
    user_key = f"user:{name.lower()}"
    wait = max([limiter.retry_after(k) for k in pair] + [user_limiter.retry_after(user_key)])
    if wait:
        return False, wait
    if check_credentials(name, password or ""):
        for key in pair:
            limiter.success(key)
        user_limiter.success(user_key)
        return True, 0
    for key in pair:
        limiter.failure(key)
    user_limiter.failure(user_key)
    return False, 0
