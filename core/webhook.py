"""Tells CatBoard (or any app) when the release feed or the library index
changed, so it reloads them at once instead of polling. The URL, with its
secret, comes from CatBoard (Settings > Integrations > Deezer to Navidrome)."""
import logging
import threading
import time

import requests

from core.config import load_secret, save_secret

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10


def webhook_url():
    return load_secret("catboard_webhook_url")


def set_webhook_url(url):
    save_secret("catboard_webhook_url", (url or "").strip() or None)


def send(event, **data):
    """POSTs {"event", "at", ...data} to the webhook; returns (ok, message)."""
    url = webhook_url()
    if not url:
        return False, "No webhook URL"
    try:
        resp = requests.post(url, json={"event": event, "at": int(time.time()), **data}, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        return False, f"Cannot reach the webhook: {e.__class__.__name__}"
    if resp.status_code >= 300:
        return False, f"The webhook answered HTTP {resp.status_code}"
    return True, "Delivered"


def notify(event, **data):
    """Sends in the background; a failure is only logged."""
    if not webhook_url():
        return

    def run():
        ok, message = send(event, **data)
        if not ok:
            logger.warning(f"[webhook] {event}: {message}")

    threading.Thread(target=run, daemon=True).start()
