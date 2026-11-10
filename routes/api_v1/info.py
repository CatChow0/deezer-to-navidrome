"""What an app needs to know once signed in: the server, the profiles, the
Deezer accounts and what this install can do."""
from flask import g, request, session

from core import account_context, auth, deezer_accounts, deezer_dl, navidrome_db, nd_accounts
from core.version import get_app_version
from routes.api_v1 import API_VERSION, api_v1_bp, ok


@api_v1_bp.get("/info")
def info():
    profile = account_context.resolve(request, session)
    return ok({
        "service": "deezer-to-navidrome",
        "api": API_VERSION,
        "version": get_app_version(),
        "username": auth.username(),
        "auth_disabled": auth.auth_disabled(),
        "device": getattr(g, "device", None),
        "profile": profile,
        "profiles": [nd_accounts.public(a) for a in nd_accounts.list_accounts()],
        "deezer": {
            "accounts": [deezer_accounts.public(a) for a in deezer_accounts.list_accounts()],
            "default": deezer_accounts.default_id(),
            "download": deezer_accounts.download_id(),
            "profile_account": account_context.deezer_account_of(profile),
        },
        "features": {
            "downloads": bool(deezer_dl.download_arl()),
            "navidrome_db": navidrome_db.mounted(),
        },
    }, cache=True)
