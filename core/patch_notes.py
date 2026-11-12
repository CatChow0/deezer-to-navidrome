"""The versions shown by the New button, newest first. Each has its own note in
templates/notes/<version>.html; a test fails if VERSION has none, so a release
cannot ship without one.

Each version also says, apart from its note:
- `highlights`: what matters most in it, three lines at most, shown first;
- `actions`: what to change for it, if anything. The New panel puts them in a
  card at the top of the note, and adds up those of every version not read
  yet, so someone jumping several versions sees all they have to do. The
  README's Upgrading section lists the same (a test checks they agree).

An action: `level` is "required" (something stops working otherwise),
"recommended" or "optional"; `when` the setups it is for; `do` what to do, in
one sentence; `lines` what to copy, if anything; `file` where they go
(".env", "compose", "Navidrome", "Authelia" or "app" for a step in the app)."""

LEVELS = ("required", "recommended", "optional")
FILES = (".env", "compose", "Navidrome", "Authelia", "app")

_AUTHELIA_BYPASS = [
    "- domain: music.example.com",
    '  resources: ["^/api/v1/"]',
    "  policy: bypass",
]

RELEASES = [
    {"version": "1.21.0", "date": "2026-11-12", "title": "Your Deezer playlists in one click",
     "highlights": [
         "From Deezer lists your account's playlists: Loved tracks, yours and your favorites, private ones too.",
         "Your playlists, Deezer's mixes and its recommendations in one panel, on the web and the phone.",
         "Daily Mix and Daily Mix+ stay close to their seed: its artist, and those Deezer says are close.",
     ],
     "actions": []},
    {"version": "1.20.0", "date": "2026-11-12", "title": "Several accounts, each with its own profiles",
     "highlights": [
         "A Super-Admin, Admins and Standard accounts, each with its own profiles and Deezer accounts.",
         "Forgot your password? A recovery code for each account.",
         "Settings in spaces: General, Accounts, Stats and sign-in, and Users.",
     ],
     "actions": [
         {"level": "recommended", "when": "Everyone",
          "do": "Make your recovery code in Settings → Stats and sign-in → Sign-in and other apps, and keep it somewhere safe.",
          "lines": [], "file": "app"},
     ]},
    {"version": "1.19.0", "date": "2026-11-11", "title": "Safer files, sign-in and downloads",
     "highlights": [
         "Saved playlists, scans and settings can no longer be wiped by two saves at once.",
         "Artists and titles in every script (Кино, 宇多田ヒカル) match your library.",
         "The yearly recap of a long history opens in seconds.",
     ],
     "actions": [
         {"level": "recommended", "when": "Behind a reverse proxy (Traefik, nginx, Caddy…)",
          "do": "Tell the app how many proxies stand in front of it, and keep the session cookie on HTTPS.",
          "lines": ["TRUSTED_PROXIES=1", "COOKIE_SECURE=true"], "file": ".env"},
         {"level": "optional", "when": "To run the app as your own user instead of root",
          "do": "Set your user and group IDs; the music folders must be writable by them first.",
          "lines": ["PUID=1000", "PGID=1000"], "file": ".env"},
     ]},
    {"version": "1.18.2", "date": "2026-11-11", "title": "Namesakes, private Deezer profiles, big playlists",
     "highlights": [
         "Private Deezer profiles and playlists of your own are read with your Deezer account.",
         "Deezer playlists over 400 tracks are no longer cut.",
         "Made for you no longer mixes up artists who share a name.",
     ],
     "actions": []},
    {"version": "1.18.1", "date": "2026-11-10", "title": "The whole web interface in the Android app",
     "highlights": [
         "Playlists, search, Made for you, Stats, Releases and Settings in the Android app.",
         "The app shows the pages it saved while the server cannot be reached.",
         "A smaller app that starts faster.",
     ],
     "actions": []},
    {"version": "1.18.0", "date": "2026-11-09", "title": "The Android app",
     "highlights": [
         "An Android app, installed from Settings, that updates itself from your server.",
         "Sign in, choose the profile, and follow Activity from your phone.",
     ],
     "actions": [
         {"level": "required", "when": "Behind Authelia or another login proxy",
          "do": "Let /api/v1/ through without the login page: the app cannot pass it, its token protects these routes.",
          "lines": _AUTHELIA_BYPASS, "file": "Authelia"},
     ]},
    {"version": "1.17.0", "date": "2026-11-09", "title": "An API for the Android app",
     "highlights": [
         "A JSON API under /api/v1/, with a token for each device.",
         "Settings lists the devices signed in, and signs one out.",
     ],
     "actions": [
         {"level": "required", "when": "Behind Authelia or another login proxy, to use the API",
          "do": "Let /api/v1/ through without the login page: the device token protects these routes.",
          "lines": _AUTHELIA_BYPASS, "file": "Authelia"},
     ]},
    {"version": "1.16.0", "date": "2026-11-09", "title": "Several Navidrome users and Deezer accounts",
     "highlights": [
         "Several Navidrome users, each with their playlists, history, recaps and Made for you.",
         "Several Deezer accounts, one of them for the downloads.",
         "Saved passwords and tokens are encrypted.",
     ],
     "actions": [
         {"level": "recommended", "when": "Every setup",
          "do": "Set your own encryption key, so a copy of the data folder does not carry the key along.",
          "lines": ["D2N_ENCRYPTION_KEY=a-long-random-string"], "file": ".env"},
     ]},
    {"version": "1.15.0", "date": "2026-11-08", "title": "A quarantine you can sort and set",
     "highlights": [
         "On trial, To review and Trash can be searched, sorted and filtered.",
         "The trial rules are yours to set.",
     ],
     "actions": []},
    {"version": "1.14.0", "date": "2026-11-06", "title": "Playlists made from your listening",
     "highlights": [
         "Daily Mix, Daily Mix+ and Discover, built from what you listen to.",
         "Fix missing metadata adds the tempo and genre your files lack.",
         "What the mixes download stays on trial until you keep it.",
     ],
     "actions": [
         {"level": "recommended", "when": "To let Fix missing metadata write tags",
          "do": "Mount your music folders writable (no :ro): otherwise the tags are only kept in the app.",
          "lines": [], "file": "compose"},
     ]},
    {"version": "1.13.0", "date": "2026-11-05", "title": "Your listening stats are built in",
     "highlights": [
         "A Stats tab with story recaps, top lists, genres and habits.",
         "The app keeps its own history, and imports the past from Navidrome and Maloja.",
     ],
     "actions": [
         {"level": "recommended", "when": "To import your past plays",
          "do": "Mount Navidrome's data folder, and Maloja's if you had it, read-only.",
          "lines": ["- /path/to/navidrome/data:/import/navidrome:ro", "- /path/to/Maloja:/import/maloja:ro"],
          "file": "compose"},
         {"level": "recommended", "when": "To record new plays",
          "do": "Point Navidrome's ListenBrainz at this app, restart it, and link ListenBrainz with the token from Settings.",
          "lines": ["ND_LISTENBRAINZ_BASEURL=http://deezer-to-navidrome:8080/apis/listenbrainz/1/"],
          "file": "Navidrome"},
     ]},
    {"version": "1.12.0", "date": "2026-11-03", "title": "Playlists from Spotify and CSV files",
     "highlights": [
         "Paste a Spotify link, or import a CSV from Exportify, TuneMyMusic or Soundiiz.",
         "Find on Deezer picks the right track by hand.",
     ],
     "actions": []},
    {"version": "1.11.2", "date": "2026-10-22", "title": "Clearer setup, exact album badges",
     "highlights": ["Album badges count their real tracks.", "A Clear button empties the search."],
     "actions": []},
    {"version": "1.11.1", "date": "2026-10-22", "title": "Damaged downloads fixed and repaired",
     "highlights": ["Downloads made by 1.10.0 to 1.11.0 could be damaged: they are correct from now on."],
     "actions": [
         {"level": "required", "when": "If you downloaded with 1.10.0 to 1.11.0",
          "do": "Run Repair downloads (Settings → Library index), then Refresh library.",
          "lines": [], "file": "app"},
     ]},
    {"version": "1.11.0", "date": "2026-10-22", "title": "Explicit versions and your account's country",
     "highlights": ["Explicit tracks stay explicit.", "Settings shows your Deezer account's country."],
     "actions": []},
    {"version": "1.10.1", "date": "2026-10-21", "title": "Follow each download, choose where it goes",
     "highlights": ["Each download shows its progress on its button.", "Settings chooses the downloads folder."],
     "actions": []},
    {"version": "1.10.0", "date": "2026-10-21", "title": "Downloads are built in",
     "highlights": ["The app downloads from Deezer by itself: no second container."],
     "actions": [
         {"level": "required", "when": "If you ran the deezer-downloader container",
          "do": "Delete its service and DEEZER_DL_BASE_URL, and mount your downloads folder here, writable.",
          "lines": ["- /path/on/host/deezer-dl:/music/deezer-dl"], "file": "compose"},
     ]},
]


def version_key(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def unread(since) -> list:
    """The releases newer than `since` (the version whose notes were read last),
    newest first. Every release when nothing was read yet."""
    if not since:
        return list(RELEASES)
    try:
        seen = version_key(str(since))
    except ValueError:
        return list(RELEASES)
    return [r for r in RELEASES if version_key(r["version"]) > seen]


def pending_actions(since) -> list:
    """The actions of every release not read yet, each with its version."""
    return [{**action, "version": release["version"]} for release in unread(since) for action in release.get("actions", [])]
