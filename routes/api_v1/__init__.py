"""The API the Android app, and any other client, uses: /api/v1/….

- Every answer is a JSON object. A failure is {"error": {"code", "message"}}
  with the matching HTTP status.
- Reads carry an ETag: a client sends it back in If-None-Match and gets a 304
  when nothing changed, which is what its offline cache relies on.
- A request is for the profile named in the X-Navidrome-Account header, else
  the default Navidrome account.
- A device signs in once (POST /api/v1/auth/login) and sends its token as
  "Authorization: Bearer d2n_…" (core/devices.py); the web session works too.

Everything a phone needs lives under this prefix, media and task streams
included, so that a reverse proxy can let the app through with one rule."""
import hashlib
import json

from flask import Blueprint, current_app, request

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
API_VERSION = 1
PREFIX = "/api/v1/"


def ok(payload=None, status=200, cache=False):
    """A JSON answer. `cache`: a read the client may keep, with its ETag."""
    text = json.dumps(payload if payload is not None else {}, ensure_ascii=False, separators=(",", ":"), default=str)
    response = current_app.response_class(text, status=status, mimetype="application/json")
    if cache and status == 200:
        response.set_etag(hashlib.sha256(text.encode()).hexdigest()[:24])
        response.headers["Cache-Control"] = "private, no-cache"
        response.make_conditional(request)
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


def error(code, message, status=400, **extra):
    return ok({"error": {"code": code, "message": message, **extra}}, status=status)


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# The resources register their routes on the blueprint.
from routes.api_v1 import auth, info, tasks  # noqa: E402,F401
