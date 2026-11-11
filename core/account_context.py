"""Which Navidrome account a request is about: one of the profiles of the
account of this app signed in (flask.g.user), never another's.

Each device keeps its own choice: the browser in its session, the mobile app in
the X-Navidrome-Account header. Without either, the account's first profile.
The profile is then passed explicitly to the code it concerns: background
threads do not inherit a request, so nothing relies on an implicit current one."""
from flask import g

from core import nd_accounts

HEADER = "X-Navidrome-Account"
SESSION_KEY = "nd_account"


def own_profiles(user) -> list:
    from core import auth

    if auth.auth_disabled():
        return [a["id"] for a in nd_accounts.list_accounts()]  # one person behind the proxy's login
    return [a["id"] for a in nd_accounts.accounts_of(user["id"])] if user else []


def resolve(request, session):
    own = own_profiles(g.get("user"))
    for candidate in (request.headers.get(HEADER), session.get(SESSION_KEY)):
        if candidate and candidate in own:
            return candidate
    default = nd_accounts.default_id()
    return default if default in own else (own[0] if own else None)


def deezer_account_of(profile_id):
    """The Deezer account a Navidrome profile reads its releases and mixes with:
    the one it chose, else the first its owner may use (the default one first)."""
    from core import deezer_accounts

    profile = nd_accounts.get(profile_id) if profile_id else None
    if profile is None:
        return None
    from core import users

    usable = [a["id"] for a in deezer_accounts.usable_by(users.effective_owner(profile.get("owner")))]
    chosen = profile.get("deezer_account")
    if chosen in usable:
        return chosen
    default = deezer_accounts.default_id()
    return default if default in usable else (usable[0] if usable else None)


def download_account_of(user_id):
    """The Deezer account that downloads for an account of this app: the one it
    chose, else the first it may use."""
    from core import deezer_accounts, users

    usable = [a["id"] for a in deezer_accounts.usable_by(user_id)]
    chosen = users.field(users.get(user_id), "download_deezer")
    return chosen if chosen in usable else (usable[0] if usable else None)


def download_account_of_profile(profile_id):
    """For what a profile downloads by itself (Made for you, automatic scans): its owner's."""
    from core import users

    profile = nd_accounts.get(profile_id)
    return download_account_of(users.effective_owner(profile.get("owner"))) if profile else None


def deezer_account(request, session):
    return deezer_account_of(resolve(request, session))


def select(session, account_id) -> None:
    if account_id not in own_profiles(g.get("user")):
        raise nd_accounts.AccountError("Unknown Navidrome account.")
    session[SESSION_KEY] = account_id
