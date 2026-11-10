"""The API the Android app, and any other client, uses: /api/v1/….

- Every answer is a JSON object. A failure is {"error": {"code", "message"}}
  with the matching HTTP status.
- Reads carry an ETag: a client sends it back in If-None-Match and gets a 304
  when nothing changed, which is what its offline cache relies on. They vary
  on X-Navidrome-Account, so that cache keeps each profile's copy apart.
- A request is for the profile named in the X-Navidrome-Account header, else
  the default Navidrome account.
- A device signs in once (POST /api/v1/auth/login) and sends its token as
  "Authorization: Bearer d2n_…" (core/devices.py); the web session works too.

Everything a phone needs lives under this prefix, media and task streams
included, so that a reverse proxy can let the app through with one rule.

Most resources are the web interface's own functions, answering in this
format (expose()): the two cannot drift apart. What the web does in a form or a
page has its function shared with the web route instead (replaces())."""
import hashlib
import json

from flask import Blueprint, current_app, request

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
API_VERSION = 1
PREFIX = "/api/v1/"

# The web interface's functions this API covers, for the test that each has an
# equivalent here.
COVERED = set()

_CODES = {400: "invalid", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
          409: "conflict", 413: "too_large", 429: "too_many_requests", 502: "upstream_error", 503: "unavailable"}

# Pictures and audio, linked under this prefix in every answer.
_MEDIA = (("/stats/cover/", "/api/v1/stats/cover/"), ("/stats/audio/", "/api/v1/stats/audio/"),
          ("/covers/", "/api/v1/covers/"), ("/navidrome/cover/", "/api/v1/navidrome/cover/"),
          ("/api/mixes/trial/", "/api/v1/mixes/trial/"))


def ok(payload=None, status=200, cache=False):
    """A JSON answer. `cache`: a read the client may keep, with its ETag."""
    text = json.dumps(payload if payload is not None else {}, ensure_ascii=False, separators=(",", ":"), default=str)
    response = current_app.response_class(text, status=status, mimetype="application/json")
    if cache and status == 200:
        response.set_etag(hashlib.sha256(text.encode()).hexdigest()[:24])
        # Stale at once, so each read asks again (a 304 when unchanged), but
        # not no-cache: with it, a client's cache refuses to show the saved
        # copy while the server is unreachable.
        response.headers["Cache-Control"] = "private, max-age=0"
        # The answer depends on the profile: a client's cache keeps one copy
        # per profile, and never shows one profile's saved data to another.
        response.vary.add("X-Navidrome-Account")
        response.make_conditional(request)
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


def error(code, message, status=400, **extra):
    return ok({"error": {"code": code, "message": message, **extra}}, status=status)


def code_for(status) -> str:
    return _CODES.get(status, "server_error" if status >= 500 else "invalid")


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def media(value):
    """Links to pictures and audio, moved under this prefix."""
    if isinstance(value, str):
        for old, new in _MEDIA:
            if value.startswith(old):
                return new + value[len(old):]
        return value
    if isinstance(value, list):
        return [media(item) for item in value]
    if isinstance(value, dict):
        return {key: media(item) for key, item in value.items()}
    return value


def translate(response):
    """A web route's answer in this API's format. Files, pictures, audio and
    streams pass as they are."""
    response = current_app.make_response(response)
    if response.mimetype != "application/json" or response.direct_passthrough:
        return response
    data = response.get_json(silent=True)
    status = response.status_code
    if isinstance(data, dict) and (data.get("ok") is False or status >= 400):
        message = data.get("error") or data.get("message") or "The request failed."
        if isinstance(message, dict):
            return ok(data, status=status)
        status = status if status >= 400 else 400
        code = data.get("code") if isinstance(data.get("code"), str) else code_for(status)
        # What else the web route said, such as the task already running.
        extra = {k: media(v) for k, v in data.items() if k not in ("ok", "error", "message", "code")}
        return error(code, str(message), status, **extra)
    if isinstance(data, dict):
        data = {key: item for key, item in data.items() if key != "ok"}
    elif isinstance(data, list):
        data = {"items": data}
    return ok(media(data), status=status, cache=request.method == "GET" and status == 200)


def _answer_of_its_blueprint(view, e):
    """What the web route's own blueprint answers to this error (its
    errorhandler), or None: those handlers only run for the blueprint's URLs."""
    endpoint = next((name for name, function in current_app.view_functions.items() if function is view), "")
    handlers = current_app.error_handler_spec.get(endpoint.rpartition(".")[0], {}).get(None, {})
    for kind in type(e).__mro__:
        if kind in handlers:
            return handlers[kind](e)
    return None


def expose(rule, view, methods=("GET",), name=None):
    """A web route's function under this prefix, in this API's format."""
    def handler(**kwargs):
        try:
            answer = view(**kwargs)
        except Exception as e:
            answer = _answer_of_its_blueprint(view, e)
            if answer is None:
                raise
        return translate(answer)

    endpoint = name or f"{view.__module__.rsplit('.', 1)[-1]}_{view.__name__}"
    handler.__name__ = endpoint
    api_v1_bp.add_url_rule(rule, endpoint, handler, methods=list(methods))
    COVERED.add(view)


def replaces(*views):
    """A route of this API doing what these web routes do (a form, a page)."""
    def mark(handler):
        COVERED.update(views)
        return handler
    return mark


# The resources register their routes on the blueprint.
from routes.api_v1 import (  # noqa: E402,F401
    accounts, app, auth, info, library, mixes, playlists, releases, settings, stats, tasks,
)
