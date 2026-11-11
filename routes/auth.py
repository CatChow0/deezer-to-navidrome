from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from core import auth, devices, webhook

auth_bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only local paths, so the login page cannot send you to another site.
    Browsers read a backslash as a slash and drop tabs, so a path starting
    with a slash then a backslash, or a slash then a tab, means another host."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return url_for("playlists.home")
    if "\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        return url_for("playlists.home")
    return target


def _sign_in(name):
    session.clear()
    session.permanent = True
    session["user"] = name
    session["stamp"] = auth.session_stamp()


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    if auth.account_exists() or auth.auth_disabled():
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        name = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not name or len(password) < auth.MIN_PASSWORD:
            error = f"Choose a username and a password of at least {auth.MIN_PASSWORD} characters."
        elif password != request.form.get("confirm"):
            error = "The two passwords differ."
        else:
            auth.set_account(name, password)
            _sign_in(name)
            return redirect(url_for("playlists.home"))
    return render_template("login.html", mode="setup", error=error)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if auth.auth_disabled():
        return redirect(url_for("playlists.home"))
    if not auth.account_exists():
        return redirect(url_for("auth.setup"))
    error, status = None, 200
    if request.method == "POST":
        signed_in, wait = auth.attempt_login(request.form.get("username"), request.form.get("password"),
                                             request.remote_addr)
        if wait:
            error, status = f"Too many attempts, try again in {wait} s.", 429
        elif signed_in:
            _sign_in(auth.username())
            return redirect(_safe_next(request.form.get("next")))
        else:
            error, status = "Wrong username or password.", 401
    return render_template("login.html", mode="login", error=error, next=request.values.get("next", "")), status


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# --- Settings: account, API token, webhook --------------------------------------

@auth_bp.get("/api/auth/status")
def status_route():
    return jsonify({
        "ok": True,
        "disabled": auth.auth_disabled(),
        "username": auth.username(),
        "account_from_env": auth.account_from_env(),
        "token": auth.api_token(),
        "token_from_env": auth.token_from_env(),
        "webhook_url": webhook.webhook_url(),
    })


@auth_bp.post("/api/auth/password")
def password_route():
    if auth.account_from_env():
        return jsonify({"ok": False, "error": "The account is set by APP_USERNAME / APP_PASSWORD: change it there"}), 400
    data = request.get_json(silent=True) or {}
    current, new = str(data.get("current") or ""), str(data.get("new") or "")
    if not auth.check_credentials(auth.username(), current):
        return jsonify({"ok": False, "error": "The current password is wrong"}), 400
    if len(new) < auth.MIN_PASSWORD:
        return jsonify({"ok": False, "error": f"The new password needs at least {auth.MIN_PASSWORD} characters"}), 400
    auth.set_account(auth.username(), new)
    # Other browsers and every device are signed out; this one stays signed in.
    session["stamp"] = auth.session_stamp()
    devices.revoke_all()
    return jsonify({"ok": True})


@auth_bp.post("/api/auth/token")
def token_route():
    if auth.token_from_env():
        return jsonify({"ok": False, "error": "The token is set by API_TOKEN: change it there"}), 400
    return jsonify({"ok": True, "token": auth.new_api_token()})


@auth_bp.route("/api/webhook", methods=["PUT", "DELETE"])
def webhook_route():
    url = "" if request.method == "DELETE" else str((request.get_json(silent=True) or {}).get("url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "Enter a full URL, starting with http:// or https://"}), 400
    webhook.set_webhook_url(url)
    return jsonify({"ok": True, "webhook_url": webhook.webhook_url()})


@auth_bp.post("/api/webhook/test")
def webhook_test_route():
    ok, message = webhook.send("test")
    return jsonify({"ok": ok, "message": message}), 200 if ok else 502
