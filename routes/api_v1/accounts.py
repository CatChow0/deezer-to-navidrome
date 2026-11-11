"""The Navidrome accounts (the profiles) and the Deezer accounts. A device picks
its profile with the X-Navidrome-Account header: it has no "active account"
to set, unlike a browser (POST /api/navidrome/active)."""
from routes import account as deezer
from routes import navidrome_accounts as navidrome
from routes.api_v1 import expose

N = "/navidrome/accounts"
expose(N, navidrome.accounts, name="navidrome_accounts")
expose(N, navidrome.create, ("POST",), name="navidrome_account_create")
expose(f"{N}/test", navidrome.test_unsaved, ("POST",), name="navidrome_account_test_unsaved")
expose(f"{N}/<account_id>", navidrome.update, ("PATCH",), name="navidrome_account_update")
expose(f"{N}/<account_id>", navidrome.delete, ("DELETE",), name="navidrome_account_delete")
expose(f"{N}/<account_id>/default", navidrome.make_default, ("POST",), name="navidrome_account_default")
expose(f"{N}/<account_id>/test", navidrome.test_saved, ("POST",), name="navidrome_account_test")
expose(f"{N}/<account_id>/switch", navidrome.switch_preview, name="navidrome_account_switch_preview")
expose(f"{N}/<account_id>/switch", navidrome.switch_start, ("POST",), name="navidrome_account_switch")

D = "/deezer/accounts"
expose("/deezer/account", deezer.account_route, name="deezer_account")
expose(D, deezer.accounts_route, name="deezer_accounts")
expose(D, deezer.add_account_route, ("POST",), name="deezer_account_create")
expose(f"{D}/<account_id>", deezer.edit_account_route, ("PATCH",), name="deezer_account_update")
expose(f"{D}/<account_id>", deezer.remove_account_route, ("DELETE",), name="deezer_account_delete")
expose(f"{D}/<account_id>/check", deezer.check_account_route, ("POST",), name="deezer_account_check")
expose(f"{D}/<account_id>/default", deezer.default_account_route, ("POST",), name="deezer_account_default")
expose(f"{D}/<account_id>/download", deezer.download_account_route, ("POST",), name="deezer_account_download")
expose(f"{D}/<account_id>/share", deezer.share_account_route, ("PUT",), name="deezer_account_share")
