"""A small client for the Subsonic API of Navidrome, acting as one Navidrome user.

Credentials travel in the body of POST requests, never in a URL: a URL ends up
in proxy logs and in error messages. Every error is a SubsonicError whose text
has had the credentials removed (core/crypto.redact)."""
import hashlib
import secrets
from urllib.parse import urlsplit

import requests

from core.crypto import redact

API_VERSION = "1.16.1"
CLIENT_NAME = "deezer-to-navidrome"
TIMEOUT = 15

# Subsonic error codes worth a sentence of their own.
_MESSAGES = {
    10: "A required parameter is missing.",
    20: "This server is too old for this app.",
    30: "This server is too recent for this app.",
    40: "Wrong user name or password.",
    41: "This server does not accept this way of signing in (token authentication).",
    42: "This server does not accept API keys.",
    43: "Use either an API key or a user name, not both.",
    44: "This API key is not valid.",
    50: "This Navidrome user is not allowed to do that.",
    70: "Not found.",
}


class SubsonicError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Client:
    def __init__(self, url, username, auth_type, secret, timeout=TIMEOUT, session=None):
        self.url = (url or "").rstrip("/")
        self.username = username or ""
        self.auth_type = auth_type
        self.secret = secret or ""
        self.timeout = timeout
        self.session = session or requests.Session()

    def _auth(self) -> dict:
        if self.auth_type == "apikey":
            return {"apiKey": self.secret}
        salt = secrets.token_hex(8)
        return {"u": self.username, "t": hashlib.md5((self.secret + salt).encode()).hexdigest(), "s": salt}

    def _clean(self, text) -> str:
        return redact(text, self.secret)

    def _send(self, endpoint: str, params: dict):
        """The HTTP answer to this call. Credentials go in a form POST, never in
        the URL, where proxies and Navidrome's own log would keep them."""
        if not self.url:
            raise SubsonicError(0, "No server address.")
        data = {"v": API_VERSION, "c": CLIENT_NAME, "f": "json", **self._auth()}
        data.update({key: value for key, value in params.items() if value is not None})
        target = f"{self.url}/rest/{endpoint}"
        try:
            response = self.session.post(target, data=data, timeout=self.timeout)
            if response.status_code == 405 and self.auth_type != "apikey":
                # An old server without form POST: the parameters go in the URL.
                # Only with a password, which travels there as a salted digest
                # used once; an API key is long-lived. (Servers with API keys
                # all take form POST.)
                response = self.session.get(target, params=data, timeout=self.timeout)
        except requests.RequestException as e:
            host = urlsplit(self.url).netloc or self.url
            raise SubsonicError(0, self._clean(f"Could not reach {host}: {type(e).__name__}")) from None
        return response

    def call(self, endpoint: str, **params) -> dict:
        """The body of the "subsonic-response" for this call. List values are
        sent as repeated parameters (songId=1&songId=2)."""
        response = self._send(endpoint, params)
        if response.status_code in (401, 403):
            raise SubsonicError(40, "The server refused the credentials (HTTP %s)." % response.status_code)
        if response.status_code == 404:
            raise SubsonicError(0, "No Subsonic API at this address. Check the URL of your Navidrome.")
        if response.status_code >= 400:
            raise SubsonicError(0, f"The server answered HTTP {response.status_code}.")
        try:
            body = response.json()["subsonic-response"]
        except (ValueError, KeyError, TypeError):
            raise SubsonicError(0, "The answer is not from a Subsonic server. Check the URL of your Navidrome.") from None
        if body.get("status") != "ok":
            error = body.get("error") or {}
            code = int(error.get("code") or 0)
            raise SubsonicError(code, _MESSAGES.get(code) or self._clean(error.get("message") or "The server refused the request."))
        return body

    def binary(self, endpoint: str, **params):
        """(bytes, content type) for a call that answers a file, like getCoverArt.
        An error answer is raised as a SubsonicError, as with call()."""
        response = self._send(endpoint, params)
        kind = response.headers.get("Content-Type", "")
        if response.status_code >= 400 or "json" in kind or "xml" in kind:
            message = "Not found."
            try:
                error = response.json()["subsonic-response"].get("error") or {}
                message = _MESSAGES.get(int(error.get("code") or 0)) or message
            except (ValueError, KeyError, TypeError):
                pass
            raise SubsonicError(70, message)
        return response.content, kind or "application/octet-stream"

    # --- Calls -------------------------------------------------------------------

    def ping(self) -> dict:
        return self.call("ping")

    def user(self) -> dict:
        """This user's rights. With an API key the name goes as "username", which
        is allowed, never as "u"."""
        if not self.username:
            return {}
        return self.call("getUser", username=self.username).get("user") or {}

    def music_folders(self) -> list:
        folders = (self.call("getMusicFolders").get("musicFolders") or {}).get("musicFolder") or []
        return folders if isinstance(folders, list) else [folders]

    def extensions(self) -> list:
        try:
            items = self.call("getOpenSubsonicExtensions").get("openSubsonicExtensions") or []
        except SubsonicError:
            return []
        return [item.get("name") for item in items if isinstance(item, dict) and item.get("name")]


def test_connection(url, username, auth_type, secret, timeout=TIMEOUT) -> dict:
    """What the Settings test shows: whether signing in works, and what this user
    can do. Never raises: a failure is in "error"."""
    result = {"ok": False, "error": "", "server_version": "", "server_type": "", "open_subsonic": False,
              "admin": None, "libraries": [], "api_keys": False, "form_post": False}
    client = Client(url, username, auth_type, secret, timeout=timeout)
    try:
        info = client.ping()
        result.update(server_version=str(info.get("serverVersion") or ""), server_type=str(info.get("type") or ""),
                      open_subsonic=bool(info.get("openSubsonic")))
        extensions = client.extensions()
        result.update(api_keys="apiKeyAuthentication" in extensions, form_post="formPost" in extensions)
        if username:
            result["admin"] = bool(client.user().get("adminRole"))
        result["libraries"] = [{"id": f.get("id"), "name": f.get("name")} for f in client.music_folders()]
        result["ok"] = True
    except SubsonicError as e:
        result["error"] = e.message
    return result
