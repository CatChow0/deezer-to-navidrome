"""Tells CatBoard (or any app) when the release feed or the library index
changed, so it reloads them at once instead of polling. Each account of this
app has its own webhook, whose URL, with its secret, comes from its CatBoard
(Settings > Integrations > Deezer to Navidrome)."""
import logging
import threading
import time

import requests

from core import users

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10


def catboard_profiles(user) -> list:
    """The profiles this account's token reads: those it chose, every one of its own otherwise."""
    from core import nd_accounts

    own = [a["id"] for a in nd_accounts.accounts_of(user["id"])]
    chosen = [p for p in users.field(user, "catboard_profiles", []) or [] if p in own]
    return chosen or own


def catboard_deezer_accounts(user) -> set:
    from core import account_context

    return {account_context.deezer_account_of(p) for p in catboard_profiles(user)} - {None}


def send(user, event, **data):
    """POSTs {"event", "at", ...data} to this account's webhook; returns (ok, message)."""
    url = users.field(user, "webhook_url")
    if not url:
        return False, "No webhook URL"
    try:
        resp = requests.post(url, json={"event": event, "at": int(time.time()), **data}, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        return False, f"Cannot reach the webhook: {e.__class__.__name__}"
    if resp.status_code >= 300:
        return False, f"The webhook answered HTTP {resp.status_code}"
    return True, "Delivered"


def notify(event, deezer_account=None, **data):
    """Sends in the background to every account concerned: for the feed of a
    Deezer account, those whose CatBoard reads it; for the library, all.
    A failure is only logged."""
    concerned = [u for u in users.list_users() if users.field(u, "webhook_url")
                 and (deezer_account is None or deezer_account in catboard_deezer_accounts(u))]
    if not concerned:
        return

    def run():
        for user in concerned:
            ok, message = send(user, event, **data)
            if not ok:
                logger.warning(f"[webhook] {event} for {user['id']}: {message}")

    threading.Thread(target=run, daemon=True).start()
