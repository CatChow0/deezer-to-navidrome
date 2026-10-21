#!/usr/bin/env python3
import os
from datetime import timedelta

from flask import Flask, jsonify, redirect, request, session, url_for

from core import auth
from core.config import ensure_dirs
from core import scheduler
from routes.account import account_bp
from routes.auth import auth_bp
from routes.cache import cache_bp
from routes.dedup import dedup_bp
from routes.playlists import playlists_bp
from routes.search import search_bp
from routes.system import system_bp

ensure_dirs()
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
app.register_blueprint(account_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(cache_bp)
app.register_blueprint(dedup_bp)
app.register_blueprint(search_bp)
app.register_blueprint(system_bp)

PUBLIC_ENDPOINTS = {"auth.login", "auth.setup", "static", "system.favicon", "system.health"}


@app.before_request
def require_sign_in():
    if auth.auth_disabled() or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if session.get("user") and session.get("stamp") == auth.session_stamp() and auth.account_exists():
        return None
    if auth.token_ok(request.headers.get("Authorization"), request.method, request.path):
        return None
    wants_page = request.method == "GET" and "text/html" in request.headers.get("Accept", "")
    if wants_page:
        target = "auth.login" if auth.account_exists() else "auth.setup"
        return redirect(url_for(target, next=request.full_path.rstrip("?")))
    return jsonify({"ok": False, "error": "Sign in first"}), 401


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
