from functools import wraps

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for

from core import auth, devices, users, webhook

auth_bp = Blueprint("auth", __name__)


# --- Who is asking, and what they may do ---------------------------------------------

def me():
    """The account of this request (set by app.require_sign_in)."""
    return g.get("user")


def refused(message="Only an Admin can do this.", status=403):
    from routes import api_v1

    if request.path.startswith(api_v1.PREFIX):
        return api_v1.error("forbidden", message, status)
    return jsonify({"ok": False, "error": message}), status


def admin_only(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        return view(*args, **kwargs) if users.can(me(), "admin") else refused()
    return guarded


def subject():
    """The account whose Navidrome and Deezer accounts a request is about: the
    one asking, or for an Admin the one named by ?user= (or "user" in the
    body). None when the asker may not manage that one."""
    body = request.get_json(silent=True) if request.is_json else None
    wanted = request.args.get("user") or (body.get("user") if isinstance(body, dict) else None)
    target = users.get(wanted) if wanted else me()
    return target if target and users.can(me(), "edit", target) else None


def my_download_account():
    """The Deezer account the downloads of the asker go through."""
    from core import account_context

    return account_context.download_account_of(me()["id"]) if me() else None


def owner_only(lookup, what):
    """For a route about one account (Navidrome or Deezer, `lookup(id)`): only
    who may manage its owner; for a route about the list, only who may manage
    the account of this app it is about (subject()). On the view itself, so
    the same check runs under /api/v1."""
    def decorate(view):
        @wraps(view)
        def guarded(*args, **kwargs):
            found = lookup(kwargs["account_id"]) if kwargs.get("account_id") else None
            if found is not None and not may_manage(found.get("owner")):
                return refused(f"This {what} account is not yours.")
            if found is None and subject() is None:
                return refused(f"You cannot manage this account's {what} accounts.")
            return view(*args, **kwargs)
        return guarded
    return decorate


def may_manage(owner_id) -> bool:
    """Whether the asker may change what this account owns."""
    owner_id = users.effective_owner(owner_id)
    if me() and owner_id == me()["id"]:
        return True
    owner = users.get(owner_id)
    return bool(owner and users.can(me(), "edit", owner))


# --- Pages ---------------------------------------------------------------------------

def _safe_next(target):
    """Only local paths, so the login page cannot send you to another site.
    Browsers read a backslash as a slash and drop tabs, so a path starting
    with a slash then a backslash, or a slash then a tab, means another host."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return url_for("playlists.home")
    if "\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        return url_for("playlists.home")
    return target


def _sign_in(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["stamp"] = users.stamp(users.get(user["id"]))


def _page(mode, status=200, **context):
    return render_template("login.html", mode=mode, **context), status


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """The first visit: the Super-Admin."""
    if auth.account_exists() or auth.auth_disabled():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        if request.form.get("password") != request.form.get("confirm"):
            return _page("setup", error="The two passwords differ.")
        try:
            user = users.create(request.form.get("username"), request.form.get("password") or "",
                                users.SUPERADMIN, must_change=False)
        except users.UserError as e:
            return _page("setup", error=str(e))
        _sign_in(user)
        return _page("recovery", code=users.new_recovery_code(user["id"]))
    return _page("setup")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if auth.auth_disabled():
        return redirect(url_for("playlists.home"))
    if not auth.account_exists():
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        user, wait = auth.attempt_login(request.form.get("username"), request.form.get("password"), request.remote_addr)
        if wait:
            return _page("login", 429, error=f"Too many attempts, try again in {wait} s.", next=request.form.get("next", ""))
        if user:
            _sign_in(user)
            return redirect(url_for("auth.first_password") if user.get("must_change")
                            else _safe_next(request.form.get("next")))
        return _page("login", 401, error="Wrong username or password.", next=request.form.get("next", ""))
    return _page("login", next=request.values.get("next", ""))


@auth_bp.route("/first-password", methods=["GET", "POST"])
def first_password():
    """An account made by an Admin has a temporary password: its user chooses
    their own, then gets their recovery code."""
    user = me()
    if not user:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        if request.form.get("password") != request.form.get("confirm"):
            return _page("first", error="The two passwords differ.")
        try:
            users.set_password(user["id"], request.form.get("password") or "")
        except users.UserError as e:
            return _page("first", error=str(e))
        _sign_in(user)
        return _page("recovery", code=users.new_recovery_code(user["id"]))
    return _page("first")


def recover(name, code, password, ip):
    """(new recovery code, error, status), with the limits on failed sign-ins:
    a recovery code must not be guessed either."""
    def attempt(found):
        # The Super-Admin may also use the code the app wrote on the server.
        result = _try(lambda: users.recover(found, code, password))
        if not result and (users.by_name(found) or {}).get("role") == users.SUPERADMIN:
            result = _try(lambda: users.recover_superadmin(code, password))
        return result

    if len(password or "") < users.MIN_PASSWORD:
        return None, f"Choose a password of at least {users.MIN_PASSWORD} characters.", 400
    result, wait = auth.attempt_login(name, password, ip, check=attempt)
    if wait:
        return None, f"Too many attempts, try again in {wait} s.", 429
    if not result:
        return None, "This username and recovery code do not match.", 400
    return result, None, 200


def _try(action):
    try:
        return action()
    except users.UserError:
        return None


@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        code, error, status = recover(request.form.get("username"), request.form.get("code"),
                                      request.form.get("password"), request.remote_addr)
        if error:
            return _page("forgot", status, error=error)
        return _page("recovery", code=code, recovered=True)
    return _page("forgot")


@auth_bp.post("/forgot/superadmin")
def forgot_superadmin():
    try:
        path = users.write_superadmin_code()
    except users.UserError as e:
        return _page("forgot", 400, error=str(e))
    return _page("forgot", notice=f"A code valid {users.RECOVERY_SECONDS // 60} minutes is in {path.name}, "
                                  f"in the app's data folder on the server. Enter it below as the recovery code.")


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# --- Settings: your password, recovery code, API token, webhook ----------------------

@auth_bp.get("/api/auth/status")
def status_route():
    user = me()
    from core import nd_accounts

    return jsonify({
        "ok": True,
        "disabled": auth.auth_disabled(),
        "user": users.public(user) if user else None,
        "username": user["username"] if user else "",
        "account_from_env": bool(user and user.get("from_env")),
        "token": users.field(user, "api_token"),
        "token_from_env": users.token_from_env(user),
        "webhook_url": users.field(user, "webhook_url"),
        "catboard_profiles": webhook.catboard_profiles(user) if user else [],
        "profiles": [{"id": a["id"], "label": a["label"]} for a in nd_accounts.accounts_of(user["id"])] if user else [],
    })


@auth_bp.post("/api/auth/password")
def password_route():
    user = me()
    if user.get("from_env"):
        return jsonify({"ok": False, "error": "The account is set by APP_USERNAME / APP_PASSWORD: change it there"}), 400
    data = request.get_json(silent=True) or {}
    if not users.check(user["username"], str(data.get("current") or "")):
        return jsonify({"ok": False, "error": "The current password is wrong"}), 400
    try:
        users.set_password(user["id"], str(data.get("new") or ""))
    except users.UserError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    # Its other browsers and devices are signed out; this one stays signed in.
    session["stamp"] = users.stamp(users.get(user["id"]))
    devices.revoke_all(user["id"])
    return jsonify({"ok": True})


@auth_bp.post("/api/auth/recovery")
def recovery_route():
    """A new recovery code for yourself, shown once."""
    return jsonify({"ok": True, "code": users.new_recovery_code(me()["id"])})


@auth_bp.post("/api/auth/token")
def token_route():
    import secrets

    user = me()
    if users.token_from_env(user):
        return jsonify({"ok": False, "error": "The token is set by API_TOKEN: change it there"}), 400
    token = secrets.token_urlsafe(32)
    users.set_field(user["id"], "api_token", token)
    return jsonify({"ok": True, "token": token})


@auth_bp.put("/api/auth/catboard")
def catboard_route():
    """The profiles your API token and webhook are about (CatBoard)."""
    from core import nd_accounts

    own = {a["id"] for a in nd_accounts.accounts_of(me()["id"])}
    chosen = [p for p in (request.get_json(silent=True) or {}).get("profiles") or [] if p in own]
    users.set_field(me()["id"], "catboard_profiles", chosen)
    return jsonify({"ok": True, "catboard_profiles": webhook.catboard_profiles(users.get(me()["id"]))})


@auth_bp.route("/api/webhook", methods=["PUT", "DELETE"])
def webhook_route():
    url = "" if request.method == "DELETE" else str((request.get_json(silent=True) or {}).get("url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "Enter a full URL, starting with http:// or https://"}), 400
    users.set_field(me()["id"], "webhook_url", url)
    return jsonify({"ok": True, "webhook_url": url})


@auth_bp.post("/api/webhook/test")
def webhook_test_route():
    ok, message = webhook.send(users.get(me()["id"]), "test")
    return jsonify({"ok": ok, "message": message}), 200 if ok else 502
