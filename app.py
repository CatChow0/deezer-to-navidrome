#!/usr/bin/env python3
import os
from datetime import timedelta

from flask import Flask, g, jsonify, redirect, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from core import auth, content, devices, users
from core.config import ensure_dirs
from core import migrations
from core import scheduler
from routes import api_v1
from routes.account import account_bp
from routes.android import android_bp
from routes.auth import auth_bp
from routes.cache import cache_bp
from routes.dedup import dedup_bp
from routes.listenbrainz import listenbrainz_bp
from routes.mixes import mixes_bp
from routes.navidrome_accounts import navidrome_accounts_bp
from routes.navidrome_playlists import navidrome_playlists_bp
from routes.playlists import playlists_bp
from routes.search import search_bp
from routes.stats import stats_bp
from routes.system import SETTING_CHOICES, system_bp
from routes.users import users_bp

ensure_dirs()
migrations.run()
scheduler.start()

app = Flask(__name__)
app.secret_key = auth.secret_key()
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    # Cross-site requests carry no session: forms cannot be posted from another site.
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes"),
    # The largest body any route reads is a CSV import (5 MB): without a limit,
    # anyone could make the server read gigabytes before signing in.
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)


def _trusted_proxies() -> int:
    try:
        return max(0, int(os.environ.get("TRUSTED_PROXIES", "0").strip() or 0))
    except ValueError:
        return 0


# Behind a reverse proxy every request comes from the proxy's address, so the
# limit on failed sign-ins would count everyone together. TRUSTED_PROXIES=1
# (one proxy in front) reads the client's address from X-Forwarded-For. Left at
# 0 when nothing is in front: anyone could then send that header.
if _trusted_proxies():
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_trusted_proxies(), x_proto=_trusted_proxies(),
                            x_host=_trusted_proxies())

app.jinja_env.globals["doc_sections"] = content.HELP_SECTIONS
app.jinja_env.globals["setting_choices"] = SETTING_CHOICES

app.register_blueprint(playlists_bp)
app.register_blueprint(api_v1.api_v1_bp)
app.register_blueprint(account_bp)
app.register_blueprint(android_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(cache_bp)
app.register_blueprint(dedup_bp)
app.register_blueprint(listenbrainz_bp)
app.register_blueprint(mixes_bp)
app.register_blueprint(navidrome_accounts_bp)
app.register_blueprint(navidrome_playlists_bp)
app.register_blueprint(search_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(system_bp)
app.register_blueprint(users_bp)

# The ListenBrainz routes check their own token: Navidrome has no session.
PUBLIC_ENDPOINTS = {
    "auth.login", "auth.setup", "static", "system.favicon", "system.health",
    "listenbrainz.submit", "listenbrainz.submit_slash", "listenbrainz.validate", "listenbrainz.validate_slash",
    "api_v1.auth_status", "api_v1.auth_login", "api_v1.auth_setup",
    "auth.forgot", "auth.forgot_superadmin", "api_v1.auth_forgot", "api_v1.auth_forgot_superadmin",
}


@app.context_processor
def navidrome_accounts_for_pages():
    """The account picker in the top bar. Only for a signed-in page."""
    from core import account_context, nd_accounts

    user = g.get("user")
    if not user:
        return {}
    try:
        # Each account picks among its own profiles only, Admins too.
        accounts = [nd_accounts.public(a) for a in nd_accounts.accounts_of(user["id"])]
        return {"nd_accounts": accounts, "nd_active": account_context.resolve(request, session),
                "me": users.public(user), "is_admin": users.can(user, "admin")}
    except Exception:
        return {}


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.before_request
def refuse_other_sites():
    """A form or a script on another site cannot change anything here, even
    with DISABLE_AUTH or a proxy's login, which the browser sends along.
    Browsers say where a request comes from (Sec-Fetch-Site); the Android app,
    Navidrome and CatBoard send no such header and are not concerned."""
    if request.method in SAFE_METHODS:
        return None
    if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        if request.path.startswith(api_v1.PREFIX):
            return api_v1.error("forbidden", "Requests from another site are refused.", 403)
        return jsonify({"ok": False, "error": "Requests from another site are refused."}), 403
    return None


# What an account with a temporary password may still do: choose its own.
WHILE_CHANGING = {"auth.first_password", "auth.logout", "api_v1.auth_first_password", "api_v1.auth_logout",
                  "api_v1.auth_status", "api_v1.me", "static", "system.favicon", "system.health"}


def _signed_in_user():
    """The account of this request: its web session, its device, or (on the few
    routes it opens) its API token. None when there is none."""
    user = users.get(session.get("user_id")) if session.get("user_id") else None
    if user and session.get("stamp") == users.stamp(user):
        return user
    # A device signed in through the API: its token opens every route of its account.
    device = devices.verify(request.headers.get("Authorization"), request.remote_addr or "")
    if device:
        g.device = device
        return users.get(device.get("user"))
    user = auth.token_user(request.headers.get("Authorization"), request.method, request.path)
    g.token = bool(user)
    return user


@app.before_request
def require_sign_in():
    if auth.auth_disabled():
        # One person behind the proxy's login: the whole app, as the Super-Admin.
        g.user = users.superadmin() or users.OPEN
        return None
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    user = _signed_in_user()
    if user:
        g.user = user
        if user.get("must_change") and request.endpoint not in WHILE_CHANGING:
            if request.path.startswith(api_v1.PREFIX):
                return api_v1.error("password_change_needed", "Choose your own password first.", 403)
            return redirect(url_for("auth.first_password"))
        return None
    if request.path.startswith(api_v1.PREFIX):
        return api_v1.error("unauthorized", "Sign in first: send this device's token.", 401)
    wants_page = request.method == "GET" and "text/html" in request.headers.get("Accept", "")
    if wants_page:
        target = "auth.login" if auth.account_exists() else "auth.setup"
        return redirect(url_for(target, next=request.full_path.rstrip("?")))
    return jsonify({"ok": False, "error": "Sign in first"}), 401


# Under /api/v1, even a missing route, a body too large or a crash answers in
# the API's format.
_HTTP_MESSAGES = {404: "No such resource.", 405: "This resource does not take that method."}


@app.errorhandler(HTTPException)
def http_error(e):
    if not request.path.startswith(api_v1.PREFIX) or e.code is None:
        return e
    return api_v1.error(api_v1.code_for(e.code), _HTTP_MESSAGES.get(e.code, e.description), e.code)


@app.errorhandler(500)
def server_error(e):
    return api_v1.error("server_error", "Something went wrong on the server.", 500) \
        if request.path.startswith(api_v1.PREFIX) else e


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
