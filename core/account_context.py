"""Which Navidrome account a request is about.

Each device keeps its own choice: the browser in its session, the mobile app in
the X-Navidrome-Account header. Without either, the default account. The
account is then passed explicitly to the code it concerns: background threads
do not inherit a request, so nothing relies on an implicit current account."""
from core import nd_accounts

HEADER = "X-Navidrome-Account"
SESSION_KEY = "nd_account"


def resolve(request, session):
    known = {a["id"] for a in nd_accounts.list_accounts()}
    for candidate in (request.headers.get(HEADER), session.get(SESSION_KEY)):
        if candidate and candidate in known:
            return candidate
    return nd_accounts.default_id()


def select(session, account_id) -> None:
    if nd_accounts.get(account_id) is None:
        raise nd_accounts.AccountError("Unknown Navidrome account.")
    session[SESSION_KEY] = account_id
