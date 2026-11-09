#!/usr/bin/env python3
import os
from datetime import timedelta

from flask import Flask, g, jsonify, redirect, request, session, url_for

from core import auth, devices
from core.config import ensure_dirs
from core import migrations
from core import scheduler
from routes import api_v1
from routes.account import account_bp
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
from routes.system import system_bp

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
)

app.register_blueprint(playlists_bp)
app.register_blueprint(api_v1.api_v1_bp)
app.register_blueprint(account_bp)
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

# The ListenBrainz routes check their own token: Navidrome has no session.
PUBLIC_ENDPOINTS = {
    "auth.login", "auth.setup", "static", "system.favicon", "system.health",
    "listenbrainz.submit", "listenbrainz.submit_slash", "listenbrainz.validate", "listenbrainz.validate_slash",
    "api_v1.auth_status", "api_v1.auth_login", "api_v1.auth_setup",
}


@app.context_processor
def navidrome_accounts_for_pages():
    """The account picker in the top bar. Only for a signed-in page."""
    from core import account_context, nd_accounts

    if not (auth.auth_disabled() or session.get("user")):
        return {}
    try:
        accounts = [nd_accounts.public(a) for a in nd_accounts.list_accounts()]
        return {"nd_accounts": accounts, "nd_active": account_context.resolve(request, session)}
    except Exception:
        return {}


@app.before_request
def require_sign_in():
    if auth.auth_disabled() or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if session.get("user") and session.get("stamp") == auth.session_stamp() and auth.account_exists():
        return None
    # A device signed in through the API: its token opens every route.
    device = devices.verify(request.headers.get("Authorization"), request.remote_addr or "")
    if device:
        g.device = device
        return None
    if auth.token_ok(request.headers.get("Authorization"), request.method, request.path):
        return None
    if request.path.startswith(api_v1.PREFIX):
        return api_v1.error("unauthorized", "Sign in first: send this device's token.", 401)
    wants_page = request.method == "GET" and "text/html" in request.headers.get("Accept", "")
    if wants_page:
        target = "auth.login" if auth.account_exists() else "auth.setup"
        return redirect(url_for(target, next=request.full_path.rstrip("?")))
    return jsonify({"ok": False, "error": "Sign in first"}), 401


# Under /api/v1, even a missing route or a crash answers in the API's format.
@app.errorhandler(404)
def not_found(e):
    return api_v1.error("not_found", "No such resource.", 404) if request.path.startswith(api_v1.PREFIX) else e


@app.errorhandler(405)
def method_not_allowed(e):
    return api_v1.error("method_not_allowed", "This resource does not take that method.", 405) \
        if request.path.startswith(api_v1.PREFIX) else e


@app.errorhandler(500)
def server_error(e):
    return api_v1.error("server_error", "Something went wrong on the server.", 500) \
        if request.path.startswith(api_v1.PREFIX) else e


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
