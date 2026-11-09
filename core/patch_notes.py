"""The versions shown by the New button, newest first. Each has its own note in
templates/notes/<version>.html; a test fails if VERSION has none, so a release
cannot ship without one."""

RELEASES = [
    {"version": "1.17.0", "date": "2026-11-09", "title": "An API for the Android app"},
    {"version": "1.16.0", "date": "2026-11-09", "title": "Several Navidrome users and Deezer accounts"},
    {"version": "1.15.0", "date": "2026-11-08", "title": "A quarantine you can sort and set"},
    {"version": "1.14.0", "date": "2026-11-06", "title": "Playlists made from your listening"},
    {"version": "1.13.0", "date": "2026-11-05", "title": "Your listening stats are built in"},
    {"version": "1.12.0", "date": "2026-11-03", "title": "Playlists from Spotify and CSV files"},
    {"version": "1.11.2", "date": "2026-10-22", "title": "Clearer setup, exact album badges"},
    {"version": "1.11.1", "date": "2026-10-22", "title": "Damaged downloads fixed and repaired"},
    {"version": "1.11.0", "date": "2026-10-22", "title": "Explicit versions and your account's country"},
    {"version": "1.10.1", "date": "2026-10-21", "title": "Follow each download, choose where it goes"},
    {"version": "1.10.0", "date": "2026-10-21", "title": "Downloads are built in"},
]
