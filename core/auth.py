"""Sign-in for the web interface and an API token for other apps (CatBoard).

The accounts are in core/users.py: the Super-Admin made at the first visit (or
from APP_USERNAME / APP_PASSWORD), and those it and the Admins add.
DISABLE_AUTH=true turns all of it off, for setups where a reverse proxy
already asks for a login. Each account's API token only opens the read-only
routes other apps need (release feed, library check)."""
import os
import secrets
import threading
import time

from core.config import load_secret, save_secret

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


# --- Accounts (core/users.py) ------------------------------------------------------

def account_exists():
    from core import users

    return users.exists()


def token_user(header, method, path):
    """The account whose API token this is, for the few routes the token opens, or None."""
    from core import users

    if (method, path) not in TOKEN_ROUTES:
        return None
    return users.by_token((header or "").removeprefix("Bearer ").strip())


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


def attempt_login(name, password, ip, check=None):
    """(result, wait): a sign-in checked against the limits; the account, or
    None. wait > 0: refused without checking, try again in that many seconds.
    `check(name)` replaces the password check, for a recovery code say."""
    from core import users

    name = (name or "").strip()[:256]
    check = check or (lambda found: users.check(found, password or ""))
    pair = [f"ip:{ip}", f"user-ip:{name.lower()}|{ip}"]
    user_key = f"user:{name.lower()}"
    wait = max([limiter.retry_after(k) for k in pair] + [user_limiter.retry_after(user_key)])
    if wait:
        return None, wait
    result = check(name)
    if result:
        for key in pair:
            limiter.success(key)
        user_limiter.success(user_key)
        return result, 0
    for key in pair:
        limiter.failure(key)
    user_limiter.failure(user_key)
    return None, 0
