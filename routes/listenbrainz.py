"""The part of the ListenBrainz API Navidrome uses to send plays: point its
ND_LISTENBRAINZ_BASEURL here. It has no session, so it checks its own tokens:
each Navidrome account has one, and the token says whose play it is."""
import logging
import sqlite3

from flask import Blueprint, jsonify, request

from core import auth, nd_accounts, stats_ingest

logger = logging.getLogger(__name__)

listenbrainz_bp = Blueprint("listenbrainz", __name__)
BASE = "/apis/listenbrainz/1"

# These routes are open to anyone who has the address: an address that keeps
# sending wrong tokens waits, so a token cannot be guessed. Navidrome, sending
# the right one, is never slowed down.
_limiter = auth.LoginLimiter(max_failures=20)


def _account():
    """(account, None), or (None, the answer refusing the request)."""
    key = f"ip:{request.remote_addr}"
    wait = _limiter.retry_after(key)
    if wait:
        response = jsonify({"code": 429, "error": f"Too many invalid tokens, try again in {wait} s"})
        response.headers["Retry-After"] = str(wait)
        return None, (response, 429)
    account = stats_ingest.account_for(request.headers.get("Authorization"))
    if account is None:
        _limiter.failure(key)
    return account, None


@listenbrainz_bp.post(f"{BASE}/submit-listens", endpoint="submit")
@listenbrainz_bp.post(f"{BASE}/submit-listens/", endpoint="submit_slash")
def submit():
    account, refused = _account()
    if refused:
        return refused
    if account is None:
        return jsonify({"code": 401, "error": "Invalid token"}), 401
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("payload", []), list):
        return jsonify({"code": 400, "error": "Expected a listen submission"}), 400
    if str(body.get("listen_type") or "").strip().lower() == "playing_now":
        return jsonify({"status": "ok"})
    try:
        stats_ingest.record_listens(account, body.get("payload") or [])
    except sqlite3.Error as e:
        # Not saved: an error tells Navidrome to keep the play and try again.
        logger.warning("Could not save a play: %s", e)
        return jsonify({"code": 503, "error": "Try again later"}), 503
    return jsonify({"status": "ok"})


@listenbrainz_bp.get(f"{BASE}/validate-token", endpoint="validate")
@listenbrainz_bp.get(f"{BASE}/validate-token/", endpoint="validate_slash")
def validate():
    account, refused = _account()
    if refused:
        return refused
    if account:
        found = nd_accounts.get(account) or {}
        name = found.get("username") or found.get("label") or auth.username() or "navidrome"
        return jsonify({"code": 200, "message": "Token valid.", "valid": True, "user_name": name})
    return jsonify({"code": 200, "message": "Token invalid.", "valid": False})
