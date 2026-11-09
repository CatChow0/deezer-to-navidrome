"""The help and the notes of each version: the web interface shows them in its
Help and New windows, and the API serves them to the Android app."""
from flask import render_template

# The help's sections, in their order: (id, title), each in templates/help/<id>.html.
HELP_SECTIONS = (
    ("getting-started", "Getting started"),
    ("playlists", "Playlists and mixes"),
    ("other-platforms", "Spotify and CSV"),
    ("search-player", "Search and player"),
    ("downloads", "Downloads"),
    ("library", "Library and duplicates"),
    ("releases", "Releases"),
    ("stats", "Stats and recaps"),
    ("made-for-you", "Made for you"),
    ("settings", "Settings"),
    ("sign-in", "Sign-in and other apps"),
    ("android-app", "Android app"),
    ("troubleshooting", "Troubleshooting"),
)


def help_sections() -> list:
    """[{id, title, html}], rendered with what the live checks need."""
    from core import deezer_dl

    context = {"download_dir": deezer_dl.download_dir_status()}
    return [{"id": key, "title": title, "html": render_template(f"help/{key}.html", **context)}
            for key, title in HELP_SECTIONS]


def release_notes() -> list:
    """[{version, date, title, html}], the newest first."""
    from core.patch_notes import RELEASES

    return [{**release, "html": render_template(f"notes/{release['version']}.html")} for release in RELEASES]
