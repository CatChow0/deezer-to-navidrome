"""Settings: the folders and limits, sign-in and other apps, Reset data and the
scheduler; then the help and the notes of each version."""
from core import content, deezer_dl
from core.config import whats_new_state
from routes import auth as sign_in
from routes import system
from routes.api_v1 import COVERED, api_v1_bp, body, error, expose, ok, replaces

# Settings that are lists, and what each item is.
_LISTS = {"scan_dirs": str, "host_to_navidrome_roots": dict}


def _settings() -> dict:
    return {"settings": system.settings_values(), "downloads_folder": deezer_dl.download_dir_status(),
            # The values each number takes, as the menus of Settings offer them.
            "choices": {key: list(values) for key, values in system.SETTING_CHOICES.items()}}


@api_v1_bp.get("/settings")
@replaces(system.config_view)
def settings_get():
    return ok(_settings(), cache=True)


@api_v1_bp.put("/settings")
def settings_save():
    """Only the settings sent change; the others keep their value."""
    data = body()
    unknown = sorted(set(data) - set(system.SETTINGS_KEYS))
    if unknown:
        return error("invalid", f"Unknown settings: {', '.join(unknown)}.", 400)
    for key, kind in _LISTS.items():
        if key in data and (not isinstance(data[key], list) or not all(isinstance(i, kind) for i in data[key])):
            return error("invalid", f"{key} must be a list.", 400)
    for key, values in system.SETTING_CHOICES.items():
        if key in data and (isinstance(data[key], bool) or data[key] not in values):
            return error("invalid", f"{key} must be one of {', '.join(map(str, values))}.", 400)
    try:
        system.save_settings_values({**system.settings_values(), **data})
    except ValueError as e:
        return error("invalid", str(e), 400)
    return ok(_settings())


@api_v1_bp.post("/settings/clear/<what>")
@replaces(system.clear_library_cache_route, system.clear_preview_state_route, system.clear_playlists_route,
          system.clear_all_route, system.clear_dedup_report_route, system.clear_dedup_choices_route)
def settings_clear(what):
    """Reset data: library-cache, preview-state, playlists, all, dedup-report or dedup-choices."""
    if what not in system.CLEARS:
        return error("not_found", f"Nothing called {what} to clear.", 404)
    return ok({"cleared": what, "message": system.clear(what)})


expose("/settings/security", sign_in.status_route, name="settings_security", cache=False)
expose("/settings/password", sign_in.password_route, ("POST",), name="settings_password")
expose("/settings/api-token", sign_in.token_route, ("POST",), name="settings_api_token")
expose("/settings/webhook", sign_in.webhook_route, ("PUT", "DELETE"), name="settings_webhook")
expose("/settings/webhook/test", sign_in.webhook_test_route, ("POST",), name="settings_webhook_test")
expose("/scheduler", system.scheduler_status, name="scheduler")
expose("/version", system.latest_version_route, name="version")
# The version alone: in /version and /info.
COVERED.add(system.version_route)


@api_v1_bp.get("/content/notes")
def content_notes():
    """The notes of each version, the newest first, each with its highlights and
    what to change for it; `unseen` while the New button shows its dot, then
    `since` (the version read last) and `pending_actions`, what to change since."""
    state = whats_new_state()
    return ok({"notes": content.release_notes(), "unseen": state["show"], "since": state["since"],
               "pending_actions": state["pending"]}, cache=True)


expose("/content/notes/seen", system.whats_new_seen_route, ("POST",), name="content_notes_seen")


@api_v1_bp.get("/content/help")
def content_help():
    return ok({"sections": content.help_sections()}, cache=True)
