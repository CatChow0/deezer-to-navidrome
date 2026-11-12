# Deezer to Navidrome

**A self-hosted web app that turns your Deezer playlists into Navidrome `.m3u8` playlists, matches them against your local library, and downloads what is missing straight from Deezer.**

[![Docker Image Version](https://img.shields.io/badge/version-1.21.0-blue)](https://hub.docker.com/r/catchow/deezer-to-navidrome)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-web%20app-brightgreen)](https://flask.palletsprojects.com/)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Downloads](#downloads)
- [Playlists from other platforms](#other-platforms)
- [Listening stats](#-listening-stats)
- [Cache System](#cache-system)
- [Deduplication System](#deduplication-system)
- [Installation](#installation)
  - [Behind a reverse proxy](#behind-a-reverse-proxy)
  - [Upgrading](#upgrading)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Android app](#android-app)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Notes](#notes)
- [License](#license)
- [Contributing](#contributing)
- [Support](#support)

---

<a id ="overview"></a>
## 🎯 Overview

Deezer-To-Navidrome bridges Deezer and self-hosted music servers like [Navidrome](https://www.navidrome.org/). It lets you:

- **Import your Deezer playlists** from your account (yours, your favorites, Loved tracks, private ones too), and follow the mixes Deezer makes for you (Flow, "made for you")
- **Import playlists from Spotify** (link or CSV export), matched to Deezer tracks
- **Index your local library** and keep that index up to date
- **Match tracks** against your files, and fix a wrong match by hand
- **Download missing tracks** directly from Deezer, with nothing else to install
- **Generate M3U8 playlists** that Navidrome imports
- **Follow new releases** of your favorite Deezer artists, with what you already own
- **Find duplicates** in your library and quarantine or delete them
- **Keep your listening stats**: recaps, tops and habits, from the plays Navidrome sends
- **Get playlists made from your listening** (Made for you): Daily Mix, Daily Mix+ and Discover
- **Serve several Navidrome users and Deezer accounts**, each with their own playlists, history and mixes
- **Use it from your phone** with the Android app shipped in the image

### Why Deezer-To-Navidrome?

If you self-host your music with Navidrome but discover it on Deezer, this app keeps the two in step:

1. ✅ Your Deezer playlists exist in Navidrome, pointing to your own files
2. ✅ Tracks are found even when tags and file names differ from Deezer's
3. ✅ What is missing is downloaded in one click, or automatically
4. ✅ Playlists stay synchronized on a schedule
5. ✅ The library stays clean of duplicates

---

<a id ="features"></a>
## ✨ Features

The interface has four views: **Dashboard**, **Stats**, **Releases** and **Settings**. Long tasks (scans, downloads, library refreshes) run in the background and show their progress in the **Activity** cell, so the rest of the page stays usable.

**Made for you** builds playlists from what you listen to: Daily Mix from music you already have, Daily Mix+ with a share of tracks to download (a third by default), and Discover with only tracks you never heard. Mixes form around a track, an album or an artist that keeps coming back, using tempo and genre. One switch chooses Off, Daily Mix or Daily Mix+, Discover has its own, and **Manage** sets how often they refresh, their length, the share of new tracks and the disk limits. **Fix missing metadata** finds what your files lack (tempo measured from the audio, genre from Deezer) and adds it to their tags without replacing anything: in the free space of a FLAC header, saved first so a brutal stop can put it back, or on a copy checked against the original. What these playlists download stays on trial: played enough, or starred or well rated in Navidrome, it waits under To review for you to keep it; otherwise it goes to the trash at the end of its trial. Every rule can be changed in **Manage**, and the lists can be searched, sorted and filtered. Everything is off until you turn it on. Each Navidrome profile has its own mixes, settings and quarantine (see [Made for you per profile](#made-for-you-per-profile)).

Two buttons in the topbar explain the app. **New** keeps the notes of each version, one tab each, and shows a dot after an upgrade until you open it. **Help** is a full guide with a search: how each part works, every setting, and what to do when something goes wrong, with live checks of your Deezer account and downloads folder.

### Playlists
- **From Deezer** - Your Deezer account's playlists, private ones too: Loved tracks, those you made and your favorites, in one click; any public Deezer playlist by link or ID
- **Spotify and CSV import** - Paste a Spotify link or import a CSV; each track is matched to Deezer, with **Find on Deezer** to pick it by hand
- **Mixes** - Follow your Flow and the "made for you" mixes from **From Deezer**, or add the playlists Deezer recommends; they sit with your playlists, marked **Mix**
- **Match breakdown** - Each track is shown as *In library*, *Missing* or *Not checked*, with filters
- **Quick scan / Full scan** - Re-check only what is missing, or everything
- **Manual matching** - **Fix** a track: search your library and pick the right file, or mark it as not in your library
- **M3U8 export** - Navidrome-compatible playlists, with a `report.json` and a `missing.txt`
- **Automation** - Per playlist: scan on an interval (minutes, hours or days) and download what is missing after each scan

### Listening stats

- **Stats tab** with story recaps of each month and year, top lists, genres and listening habits
- **Keeps its own history**: receives new plays from Navidrome and imports your past plays from Navidrome and Maloja
- See [Listening stats](#-listening-stats)

### Search, releases and player
- **Deezer search** - Tracks, albums and artists, with album and artist details in a drawer
- **Library check** - Chips show what you already own: tracks, albums (owned / total tracks) and artists (owned / total albums)
- **Release feed** - Recent albums, EPs and singles of your favorite Deezer artists, refreshed on a schedule; artists can be muted
- **Preview player** - 30-second previews with a queue, plus the official Deezer widget for full-length listening

### Downloads
- **Built-in Deezer downloader** - Tracks, albums and whole discographies, decrypted and tagged (cover included) by the app itself
- **Progress on the button** - *Queued*, then `42%` or `3/14`, then *Downloaded*; details in Activity
- **Retry** - A failed or partly failed download can be started again; files already saved are kept
- **Several Deezer accounts** - Each account of the app marks one **Use for download** for its downloads: mark a premium one for FLAC

### Library
- **Full rebuild / incremental refresh** of the library index
- **Multi-folder support** - Each music folder gets its own thread pool, so several disks are scanned in parallel
- **Path mappings** - Paths seen by the app are translated to the paths Navidrome sees

### Duplicates
- **Grouping** by artist, album, title and version (remix, live, remaster…)
- **Quality ranking** - Codec, file size and tag completeness
- **Persistent decisions** - Groups you already reviewed stay hidden until a new file appears
- **Quarantine or delete** the files you do not keep

### Security and integrations
- **Accounts** - A Super-Admin (created on the first visit or set from the environment), Admins and Standard accounts, each with its own profiles, and a recovery code for a forgotten password
- **API token** - Read-only access for other apps
- **API v1** - A JSON API for the Android app: each device signs in with its own token, listed and revocable in Settings
- **Android app** - Shipped inside the image: download it from Settings, and it updates itself from your server
- **[CatBoard](https://github.com/CatChow0/catboard)** - Shows the release feed; a webhook tells it when the feed or the library changed
- **Update badge** - The topbar shows when a newer version is on Docker Hub

---

<a id ="architecture"></a>
## 🏗️ Architecture

### System Overview

```
┌─────────────────────────┐
│  Deezer                 │
│  • Public API           │  search, artists, albums; playlists and favorites as a fallback
│  • Private gateway      │  playlists, favorites, mixes, download links (needs the ARL)
│  • Media servers        │  encrypted audio files
└───────────┬─────────────┘
            │
            ▼
┌──────────────────────────────────────────┐      ┌──────────────────────┐
│  Deezer-To-Navidrome (port 8080)         │◄────►│  Web browser         │
│  • Web UI + background tasks (SSE)       │      │  Android app         │
│  • API v1, a token per device            │      │  (API v1)            │
│  • Matching engine                       │      └──────────────────────┘
│  • Download queue (decrypt + tag)        │
│  • Library index + dedup engine          │
│  • Made for you + quarantine             │
│  • Listening stats (one history/profile) │
│  • Scheduler (scans, releases, mixes,    │
│    sync with Navidrome)                  │
└─────┬─────────────┬─────────────┬────────┘
      │             │             │
      ▼             ▼             ▼
┌───────────┐ ┌───────────┐ ┌────────────┐
│ Music     │ │ Downloads │ │ M3U8       │
│ folders   │ │ deezer-dl │ │ playlists  │
└─────┬─────┘ └─────┬─────┘ └─────┬──────┘
      └─────────────┼─────────────┘
                    ▼
          ┌───────────────────────────────┐
          │  Navidrome                    │
          │  • reads the files and M3U8   │
          │  • gets each user's playlists │
          │    through its Subsonic API   │
          │  • sends new plays back       │
          │    (ListenBrainz endpoint)    │
          └───────────────────────────────┘
```

The app keeps everything in `DATA_DIR`. Each file there is written in one step (a temporary file, then a rename), so a crash or two saves at once never leave it half-written; a file found damaged is set aside as `name.corrupt-<time>` rather than replaced by an empty one.

### Data Flow

1. **Index**: the app scans your music folders, reads the tags and builds the library index
2. **Fetch**: when a playlist is added or scanned, its tracks are read from Deezer
3. **Match**: each Deezer track is compared with the files of the matching artist
4. **Preview**: the result of each track is kept per playlist, so a Quick scan only re-checks what is missing
5. **Download** (optional): missing tracks are downloaded from Deezer into the downloads folder
6. **Refresh**: an incremental refresh adds the new files to the index
7. **Generate**: the M3U8 playlist is written with paths translated for Navidrome
8. **Import**: Navidrome picks up the M3U8 file

### Matching

```
For each Deezer track:
├─ 1. Artist (must match)
│     The Deezer main artist must match one of the file's artists
│     (similarity ≥ 0.85). Collaborations ("feat.", "&", "x", ",") are
│     split and a leading "The" is ignored. Only these files go further.
│
├─ 2. Title (must match)
│     Similarity ≥ 0.90, or ≥ 0.80 when the durations are within 3 s.
│     Compared with the tag title, the title parsed from the file name,
│     or the file name itself.
│
└─ 3. Ranking among the files left
      score = title × 0.60 + artist × 0.25 + album × 0.05
      Duration:      ≤ 2 s +0.10 | ≤ 5 s +0.06 | > 20 s −0.05
      Version flags: same flags +0.05 | conflict (live vs studio,
                     remix vs original…) −0.15 | remaster only: ignored
```

- `rapidfuzz` (C++, releases the GIL) computes the similarities, so matching threads run on separate cores
- The artist lookup is built once per scan, so only a small part of the library is compared with each track
- A track with no artist on Deezer falls back to comparing every title
- A match you fixed by hand is kept by the following scans

---

<a id ="downloads"></a>
## ⬇️ Downloads

The app downloads from Deezer itself: it fetches the file, decrypts it and writes its tags. The decryption and tagging code is adapted from [deezer-downloader](https://github.com/kmille/deezer-downloader) by kmille, under the MIT licence (see [License](#license)).

### Accounts and quality

Downloads use the session cookie (`arl`) of a Deezer account, added in **Settings → Deezer accounts**. Each account of the app marks the one that fetches its downloads (**Use for download**), one of its own or one shared with it; when none is marked, the first it may use does. Made for you and the automatic downloads of a profile use its owner's.

| Account used for the downloads | Badge | Download format |
|---|---|---|
| Premium (HiFi) | `Premium` | FLAC |
| Premium with high quality only | `Premium` | MP3 320 kbps |
| Free | `Free` | MP3 128 kbps |

A free account can stay the one your mixes and release feed come from, next to a premium one marked for the downloads. See [Deezer accounts](#deezer-accounts).

To get the ARL: sign in on deezer.com, open the browser's developer tools, and copy the value of the `arl` cookie.

### Country and explicit versions

Deezer serves the catalogue of the account's subscription country; Settings shows it next to the account badge. The app does not pick a country: to download from another catalogue, use an account from that country.

- **Explicit or censored**: the version downloaded is exactly the one you clicked. Search, albums and releases show an **E** next to explicit tracks and albums, so you can see which one you pick.
- **Another release of the same recording**: when a release is not available for your account, Deezer often names another release of the same recording (a best-of instead of a compilation, for example). The app downloads that one only if it is explicit exactly when the requested track is, and keeps the tags of the requested track; Activity says so ("from another release: …"). If only the censored version is available, the download fails with "Only the censored version is available for your Deezer account (FR)" instead of silently saving it.

### Where files go

```
<downloads folder>/
├── albums/
│   └── Artist - Album/
│       ├── 01 - Artist Title.flac
│       └── 02 - Artist Title.flac
└── songs/
    └── Artist - Title.flac
```

The downloads folder is set in **Settings → Downloads**. Left empty, it is the music folder named `deezer-dl` (for example `/music/deezer-dl`). Settings shows the folder actually used and warns if it does not exist or cannot be written to. Mount it as a volume, or the files stay inside the container.

Files are tagged with artist, title, album, track and disc number, date and the album cover. A file that already exists is not downloaded again.

### The queue

- Downloads run in a few threads at the same time (`DOWNLOAD_WORKERS`, 4 by default, also in **Settings → Performance**). Deezer throttles requests, so a low number is safer.
- Each download appears in **Activity** and on its button: *Queued* while it waits for a free slot, then the percentage (track) or `done/total` (album, discography), then *Downloaded* or *Already there*.
- When some tracks of an album fail, the button shows `saved/total saved` and lists the missing ones; clicking it again only fetches those.
- In a playlist, **Download missing** queues every missing track and marks the rows as *Downloaded* as they finish. Run **Refresh library** and a **Quick scan** afterwards so they count as *In library*. With automation, the next automatic scan picks them up.

> Deezer's private gateway is undocumented. If Deezer changes it, downloads and mixes may stop working until the app is updated. Search uses the public API and is not affected. Playlists and the release feed are read through the gateway first, with the Deezer account (private playlists and profiles, playlists of any size); if it fails they fall back to the public API, which only reads public playlists and profiles.

---

<a id ="other-platforms"></a>
## 🔀 Playlists from other platforms

A playlist from Spotify, or any app that exports CSV, can be imported. Each of its tracks is matched to a Deezer track; from then on it works like a Deezer playlist: previews, **Download missing**, scans against your library, the `.m3u8` and automation.

### Importing

| From | How | Limits |
|---|---|---|
| **Spotify link** | Paste an `open.spotify.com/playlist/…` link in **Playlists → Add** | Public playlists only, **first 100 tracks** |
| **CSV file** | **Playlists → Import CSV**, with a file from [Exportify](https://exportify.app), TuneMyMusic or Soundiiz | None: any size, private playlists too |

The Spotify link is read from Spotify's public embed page, with no account or API key. Since February 2026 Spotify's API only gives the tracks of a playlist to its owner, through a developer app and a Premium account, so the app does not use it. The embed page lists 100 tracks at most: for a longer playlist the drawer says so and suggests a CSV export. A CSV export usually carries the **ISRC** of each track, which gives an exact match.

CSV columns are found by name (`Track Name`/`Title`, `Artist Name(s)`/`Artist`, `Album`, `Duration (ms)` or `3:43`, `ISRC`, `Explicit`, `Playlist name`), with commas, semicolons or tabs.

### How tracks are matched to Deezer

1. **By ISRC** when the source gives it: exact.
2. **Else by search**, scoring each Deezer result on artist, title, duration, version (a remix, a live or a radio edit is another recording), album, and the explicit flag. An explicit track is never traded for its censored version silently.

Each track then shows its status in the drawer:

| Status | Meaning |
|---|---|
| (none) | Found on Deezer with a sure match |
| **Review** | The closest Deezer track, used, but worth a check (for example only the clean version exists on Deezer) |
| **Not on Deezer** | Nothing close enough was found |
| **Picked by hand** | Chosen with **Find on Deezer**, kept by every later sync |

The **To review** filter lists the tracks to check. **Find on Deezer** on a row searches Deezer (pre-filled with the source artist and title), with a preview of each result: **Use this track**, **Not on Deezer**, or **Back to automatic matching**. A file chosen by hand with **Fix** stays chosen when the Deezer track changes.

### Syncing

- A **Quick scan** reads the Spotify playlist again and matches the tracks added since; **Full scan** also matches again every track not picked by hand.
- With **Automation** on, new tracks of the Spotify playlist are matched and can be downloaded on schedule.
- A CSV import is a snapshot: import the file again to update it.

> Spotify's embed page is not an API: if Spotify changes it, reading a link stops working until the app is updated, and the error says so. CSV imports are not affected.

---

<a id ="cache-system"></a>
## 📊 Listening stats

The **Stats** tab shows what you listen to: a story recap of each month and year, top artists, albums and tracks for any week, month or year, genres, when you listen, and a searchable list of your plays. Open an artist, album or track for its plays over time.

It keeps its own history in `stats.db`, so it needs neither Maloja nor lb-enricher, and no Navidrome password. Each Navidrome account has its own history: the Stats tab shows the one of the profile chosen at the top of the page (see [Histories per profile](#histories-per-profile)). Track lengths come from Navidrome and your library index; missing genres come from Deezer, a few tracks at a time in the background, most played first. Listening time is plays × track length, so it is an estimate.

### Recaps

Each recap is a story of 10 to 12 slides that move on by themselves: tap the right side to skip, the left to go back, hold to pause. The slides depend on what stood out in that period, such as a song you played 40 times in a day, your longest sitting, who rose and fell, and a listener personality that compares the period with your usual habits.

Recaps play your own files, starting about a third of the way into each song, using the music folders already mounted in this container. A track with no playable file falls back on Deezer's 30-second preview.

### Covers

Covers are cached in `stats_covers/` in `DATA_DIR`, at most 600 px. Tracks and albums use art embedded in your files, then a `cover`, `folder` or `front` image in the album's own folder, then Deezer. Artists use an `artist` or `folder` image in their folder, then their Deezer photo, then their most-played album's cover. The cache fills in the background, most played first, and a cover is also fetched the first time a page needs it. Run **Rebuild (merge)** once after upgrading from an earlier build: it records each track's exact file.

### Recording new plays

Navidrome sends plays over its ListenBrainz integration:

1. Create a token in **Settings → Listening stats**, or set `SCROBBLE_TOKEN`. Each Navidrome account has its own: the page shows the one of the chosen profile.
2. Set `ND_LISTENBRAINZ_BASEURL=http://deezer-to-navidrome:8080/apis/listenbrainz/1/` in Navidrome and restart it, once for all its users.
3. Signed in to Navidrome as that profile's user, link ListenBrainz in the personal settings using its token.
4. Play a track and find it under **Stats → Recent plays**.

The route checks the tokens itself, even with `DISABLE_AUTH`: the token says whose play it is.

### Histories per profile

- **One history per Navidrome account.** The install's account keeps `stats.db` where it always was, untouched by the upgrade; the others have `stats/nd2.db`… The Stats tab, the recaps and **Your history** follow the profile chosen at the top of the page.
- **One token per account.** The first account's is `SCROBBLE_TOKEN` (or the one made in Settings, as before); the others' are made in Settings or set with `SCROBBLE_TOKEN_ND2`… Two accounts cannot share a token.
- **Imports read each user's plays.** Merge and Start clean only take the plays of the profile's Navidrome user in Navidrome's database: the user found by **Test** in Settings → Navidrome accounts, else the one with its user name. On a Navidrome where a single user ever played, the install's account keeps reading those plays as before.
- **Maloja is the install's.** It kept one person's plays, so only the install's account reads it.
- **Shared work.** Covers and what Deezer said about a track are found once and serve every history.
- **A removed account** takes its history to `backups/removed-accounts/` and its token stops working.
- Made for you reads each profile's own history: see below.

### Made for you per profile

- **Each profile its own mixes.** Daily Mix, Daily Mix+ and Discover are built from the profile's listening history, Discover from the releases of its Deezer account, and published for that Navidrome user only. The install's playlists keep their IDs (`auto-daily-1`); the other profiles' carry theirs (`auto-nd2-daily-1`).
- **Its own settings and verdicts.** **Manage** shows those of the profile chosen at the top of the page: its versions, refresh rate, length and trial rules, and its tracks on trial. Each profile decides with its own plays and its own stars in Navidrome only.
- **Shared disk limits.** The unheard tracks and the quarantine size count every profile together, since they share the disk.
- **A shared quarantine.** A track has one file and a verdict from each profile that got it. A mix can take a track another profile has on trial without downloading it again; the list then says "Also on trial for…". **Keep** puts it in the library for everyone. A refusal only counts for the profile that made it: the file goes to the trash once no other profile has it on trial, and a profile that later wants it gets it back from there. A file another profile's own playlist uses never goes to the trash: it goes to the library instead.
- **No duplicates.** A track someone kept is never downloaded again, and a track's file is never in two quarantines. A track on trial that is also downloaded by hand ends its trial kept: the library's copy replaces the trial copy in every playlist, and the trial copy goes.
- **One profile at a time.** Mixes are built for one profile after the other, as they share the Deezer quota.
- **A removed profile** takes its playlists out of Navidrome and of the app (a playlist shared with other profiles stays for them), and its tracks in quarantine go to the install's account.

### Importing your history

Mount the sources read-only, then choose **Rebuild (merge)** under **Stats → Your history**:

```yaml
volumes:
  - /path/to/navidrome/data:/import/navidrome:ro
  - /path/to/Maloja:/import/maloja:ro
```

The app reads copies of these files and never writes to them. When the same play is in both, Navidrome's details win. It counts as the same play within 5 seconds whatever the title (Maloja rewrites titles), within 2 minutes with the same track or a very similar title, and within 10 minutes for the same track with no closer partner.

### Rebuilding

| | Rebuild (merge) | Start clean |
|---|---|---|
| Plays only this app has | Kept | Lost |
| Plays gone from the sources | Kept | Lost |
| Needs Navidrome's database | No | Yes |

Both back up the profile's history first (the last 3, as `stats.db.bak-*` in `DATA_DIR`, or `stats/nd2.db.bak-*`…) and report what changed. To go back to a backup, stop the container, delete the history (`stats.db`, or `stats/nd2.db`…) and its `-wal` and `-shm` files, rename the backup to its name, and start it again. Start clean shows how many plays it would lose before you confirm, and refuses to run if Navidrome's database has no plays. Merge can be run any time without counting anything twice. The first import saves a copy of Maloja's database in `stats_sources/`, so rebuilds keep working after you remove Maloja. **Reset data** in Settings does not touch your listening history.

### Moving from Wrapped, Maloja and lb-enricher

1. Deploy this version, mount both sources, run **Rebuild (merge)** and check the numbers.
2. Point Navidrome at this app (above).
3. Check that a new play arrives.
4. Run **Rebuild (merge)** again to pick up plays from during the switch: Navidrome kept them.
5. Stop and remove lb-enricher, Maloja and Wrapped. Keep the Navidrome mount: Start clean needs it, and Merge reads new Navidrome plays through it.

---

## 📦 Cache System

### Cache Files Overview

| File | Purpose | Lifetime |
|------|---------|----------|
| `music_library_cache.json` | Library index | Until a full rebuild |
| `deezer_playlist_ids.json` | Saved playlists and mixes, with their automation settings | Until deleted |
| `playlist_preview_state.json` | Per-playlist match results, including manual matches | Until the playlist is deleted |
| `crossplatform.json` | Imported playlists: their source tracks and the Deezer track picked for each | Until the playlist is deleted |
| `releases.json` | Release feed | Until the next refresh |
| `release_prefs.json` | Muted artists of the release feed | Survives restarts |
| `dedup_report.json` | Latest duplicate analysis | Until a new scan |
| `dedup_choices.json` | **Persistent** duplicate decisions | Survives restarts |
| `stats.db` | Listening history of the install's Navidrome account | Survives **Reset data**; replaced only by Start clean |
| `stats/nd2.db`… | Listening history of the other Navidrome accounts | As above |
| `stats.db.bak-*`, `stats/*.db.bak-*` | Backups made before each rebuild (the last 3 of each history) | Replaced by newer ones |
| `backups/removed-accounts/` | The history of each removed Navidrome account | Delete it when you no longer need it |
| `mixes.db` | Made for you of every profile (quarantine, mix history, settings), tempo and genre results, and the playlists published in Navidrome | Survives **Reset data** and Start clean |
| `backups/pre-1.16.0/` | The saved playlists, `secrets.json` and `mixes.db` as they were before 1.16 | Can be deleted once 1.16 works for you |
| `metadata_journal/` | Saved FLAC headers while Fix missing metadata writes them | Emptied as each file is done, or at the next start |
| `trial_trash/` | Tracks removed from quarantine | Deleted after the days chosen in Manage, 30 by default |
| `stats_sources/` | Saved copy of Maloja's database | Until replaced by a larger one |
| `stats_covers/` | Cached artist, album and track covers | Survives **Reset data**; can be deleted, it fills again |
| `covers/` | Playlist artwork | Until cleaned up |
| `config.json` | App configuration | Survives restarts |
| `secrets.json` | Session key; before 1.20, the account's password hash, API token and webhook URL | Survives restarts |
| `users.json` | The accounts of the app: password and recovery code hashes, API token and webhook URL encrypted, the profiles CatBoard reads | Survives restarts |
| `recovery-code.txt` | The Super-Admin's one-time code, when asked for on the Forgot page | Deleted once used, or after 15 min |
| `navidrome_accounts.json` | Navidrome accounts, their passwords encrypted | Survives restarts |
| `devices.json` | The devices signed in through the API, each with its account, a digest of each token | Survives restarts |
| `deezer_accounts.json` | Deezer accounts, their ARLs encrypted | Survives restarts |
| `releases.json`, `releases-dz2.json`… | Release feed of each Deezer account, with `release_prefs*.json` for the muted artists | Rebuilt by a refresh |
| `encryption.key` | The encryption key, only when `D2N_ENCRYPTION_KEY` is not set | Keep it: without it, saved credentials must be entered again |
| `scheduler.json` | When each playlist was last scanned automatically, so a restart keeps the schedule | Survives restarts |
| `dedup_quarantine/` | Duplicates moved aside, with `manifest.jsonl`: one line per file, saying where it came from | Until you empty it |
| `*.corrupt-<time>` | A file that could not be read, set aside instead of being overwritten | Delete it once you checked it |
| `trial/` (in the downloads folder) | Tracks Made for you downloaded, on trial | Until kept (moved to `songs/`) or removed |

> Credentials are encrypted, but with `encryption.key` in the same folder a copy of `/data` still reveals them. Set `D2N_ENCRYPTION_KEY`, and keep `/data` private and out of any backup you share.

### Library Cache Structure

Each entry in the cache contains:

```json
{
  "path": "/music/library/Artist/Album/01 - Track.mp3",
  "mtime_ns": 1234567890123456,
  "size": 5242880,

  "tag_artist": "Artist Name",
  "tag_title": "Track Title",
  "tag_album": "Album Name",
  "tag_track_number": 1,

  "parsed_artist": "Artist Name",
  "parsed_title": "Track Title",

  "stem_norm": "01 track",
  "artist_dir_norm": "artist name",
  "album_dir_norm": "album name",

  "duration": 180.5,
  "quality_score": 85.5,
  "version_flags": ["remaster", "live"]
}
```

### Incremental Refresh

A file whose modification time and size did not change keeps its cached entry; only new and changed files are read again.

**Performance:** a full rebuild of 10,000 files takes a few minutes; an incremental refresh takes seconds.

During the build, the app also pre-computes normalized text (lowercase, no accents), version flags, quality scores and track numbers, which keeps matching and duplicate analysis fast.

---
<a id ="deduplication-system"></a>
## 🔍 Deduplication System

### Dedup Workflow

```
1. Analyze Phase
   ├─ Scan library using cache
   ├─ Extract enriched metadata
   ├─ Compute quality scores
   └─ Group by identity (artist+album+title+flags)

2. Group Phase
   ├─ For each group:
   │  ├─ Select KEEPER (highest quality)
   │  ├─ Identify DUPLICATES (other files)
   │  └─ Store folder organization
   └─ Generate group_id (UUID)

3. Filter Phase
   ├─ Load previous dedup decisions (dedup_choices.json)
   ├─ For each group:
   │  ├─ If ALL files are known: SKIP (already decided)
   │  ├─ If NEW files exist: SHOW + pre-select old files
   │  └─ If NEVER SEEN: SHOW normally
   └─ Return keeper_hints for UI

4. Display Phase
   ├─ Group by Album for organization
   ├─ Show quality metrics for each variant
   ├─ Pre-select keeper paths (from previous decisions)
   └─ Allow manual selection

5. Action Phase
   ├─ User chooses: QUARANTINE or DELETE
   ├─ A group keeping none of its files is left alone
   ├─ Apply to all duplicates
   ├─ Move to quarantine dir (noted in manifest.jsonl) or unlink
   └─ Save decisions to dedup_choices.json
```

### Quality Scoring Algorithm

```
score = 
  + codec_quality     // FLAC:100, WAV:95, MP3:60, OGG:65, etc.
  + min(file_size_MB, 200)  // Normalized file size (capped)
  + 6 (if tag_artist exists)
  + 6 (if tag_title exists)
  + 4 (if tag_album exists)
  + 3 (if duration exists)
```

**Example Scores:**
- FLAC with full tags + 4MB: ~90+ points (Keeper)
- MP3 with tags + 3MB: ~75+ points (Duplicate)
- Untagged MP3 + 2MB: ~60 points (Duplicate)

### Version Flag Detection

The app detects version flags from **raw** tag values (including content inside parentheses/brackets) for both library files and Deezer tracks. Flags are used both for dedup grouping and for match scoring — a version conflict applies a `-0.15` penalty so the correct variant is preferred.

| Flag | Detected keywords |
|------|------------------|
| `remix` | remix, rmx |
| `live` | live |
| `instrumental` | instrumental, instr |
| `remaster` | remaster, remastered |
| `radio_edit` | radio edit, radio mix, radio version |
| `extended` | extended, extended mix, extended version |
| `edit` | club edit, single edit, album edit, special edit |
| `demo` | demo |
| `session` | session, garage session, studio session |
| `original` | original, original version, original mix |
| `bonus` | bonus, bonus track |
| `alt` | alternate, alt version, alternative |
| `acapella` | acapella, a cappella |
| `mono` | mono |
| `stereo` | stereo |
| `explicit` | explicit |
| `clean` | clean version, clean edit |

**Examples of correctly detected flags:**
- `"Feather (Live Version)"` → `["live"]`
- `"Blue (Da Ba Dee) [Radio Edit]"` → `["radio_edit"]`
- `"Song - Garage Session"` → `["session"]`
- `"Track (Remastered 2021)"` → `["remaster"]`

> **Note:** a difference that is only `remaster` is ignored during matching, since remastered and original versions are generally interchangeable. Every other version conflict applies a `-0.15` penalty.

### Persistent Dedup Choices

**Key Feature**: Decisions survive app restarts!

Structure:
```json
{
  "artist_norm|album_norm|title_norm|version_flags": {
    "identity": {
      "artist": "Original Artist",
      "album": "Original Album",
      "base_title": "Original Title",
      "version_flags": ["live"]
    },
    "keep_paths": [
      "/music/lib1/Artist/Album/track.mp3",
      "/music/lib2/Artist/Album/track.flac"
    ]
  }
}
```

**Behavior on Next Scan:**
- If group has ALL same files: Hidden (skip)
- If group has NEW files: Shown, old files pre-selected
- If NEW source added: Shown, old sources pre-selected, new source unchecked

---

<a id ="installation"></a>
## 🚀 Installation

### Prerequisites

- Docker & Docker Compose
- At least one music folder mounted in the container
- (Optional) A Deezer account's `arl` cookie, for downloads, mixes and the release feed
- (Optional) Navidrome configured to import M3U8 playlists

### Quick Start with Docker Compose

1. **Create `docker-compose.yml`:**

```yaml
services:
  deezer-to-navidrome:
    image: catchow/deezer-to-navidrome:latest
    container_name: deezer-to-navidrome
    restart: unless-stopped
    # Let the container use your CPU cores: without this, Docker may
    # throttle the library scan and the matching threads.
    cpus: "4.0"          # set to your actual core count
    cpu_shares: 1024
    env_file: .env
    # Not needed behind a reverse proxy on the same Docker network
    # (see "Behind a reverse proxy").
    ports:
      - "8080:8080"
    volumes:
      # Config, index, secrets: must be persistent and private
      - ./data:/data
      # Music folders. deezer-dl must be writable: downloads go there. The
      # others too if you use Fix missing metadata or delete duplicates.
      - /path/on/host/deezer-dl:/music/deezer-dl
      - /path/on/host/library:/music/library
      # Playlist output, shared with Navidrome
      - /path/on/host/playlists:/music/playlists
      # Optional: Navidrome's data and Maloja, for the Stats history (read-only)
      # - /path/to/navidrome/data:/import/navidrome:ro
      # - /path/to/Maloja:/import/maloja:ro
```

2. **Create `.env` next to it:**

```env
DATA_DIR=/data
# Music folders to index (comma-separated). The one named deezer-dl receives
# the downloads unless DEEZER_DL_DIR says otherwise.
SCAN_DIRS=/music/deezer-dl,/music/library
# Where the M3U8 playlists are written
PLAYLISTS_BASE_DIR=/music/playlists
# The same folders as Navidrome sees them: /in/this/app:/in/navidrome
HOST_TO_NAVIDROME_ROOT=/music/deezer-dl:/deezer-dl,/music/library:/music

# Read on first start only, then in Settings
LIBRARY_WORKERS_PER_DIR=2    # 2 = HDD, 4 = RAID, 8 = SSD/NVMe
MATCH_WORKERS=4              # your CPU count

# The key credentials are encrypted with (else one is kept in /data):
# any long random string
D2N_ENCRYPTION_KEY=

# Optional: listening stats
# STATS_NAVIDROME_DB=/import/navidrome/navidrome.db
# STATS_MALOJA_DB=/import/maloja/malojadb.sqlite
# SCROBBLE_TOKEN=            # token Navidrome sends new plays with (first account)

# Optional: behind a reverse proxy (see below)
# TRUSTED_PROXIES=1
# COOKIE_SECURE=true

# Optional: run as your user instead of root (folders must be writable by it)
# PUID=1000
# PGID=1000

# Optional: Deezer accounts and the sign-in account (else in Settings / at the
# first visit)
# DEEZER_ARL=
# DEEZER_ARL_PREMIUM=
# APP_USERNAME=admin
# APP_PASSWORD=a-long-password
```

3. **Start the app:**

```bash
docker compose up -d
```

4. **Open the web UI** at `http://localhost:8080` and create your account.

5. **Add your Deezer account** in **Settings → Deezer accounts** (optional, but needed for downloads, mixes and the release feed).

### Without Docker

With Python 3.12 (the version the image runs and the requirements are tested with):

```bash
pip install -r requirements.txt
export DATA_DIR=./data
export SCAN_DIRS=/path/to/library
export PLAYLISTS_BASE_DIR=/path/to/playlists
export HOST_TO_NAVIDROME_ROOT=/path/to/library:/music
python app.py   # http://localhost:8080
```

<a id="behind-a-reverse-proxy"></a>
### Behind a reverse proxy

The app works behind Traefik, nginx, Caddy or any proxy that serves it over HTTPS:

- **Tell it the proxy is there**: `TRUSTED_PROXIES=1` (the number of proxies in front of it; `2` with Cloudflare's proxy in front of yours). The limit on failed sign-ins then counts each visitor's own address instead of the proxy's, and the app knows the page is served over HTTPS. Leave it at `0` without a proxy: anyone could then pretend to be another address.
- **Keep the session cookie on HTTPS**: `COOKIE_SECURE=true`.
- **No port to publish**: drop `ports:` when the proxy reaches the container on a shared Docker network.
- **Let task streams through as they come.** Activity follows each task through a Server-Sent Events stream (`/tasks/<id>/stream`, `/api/v1/tasks/<id>/stream`): the proxy must neither buffer nor compress it. Traefik does not buffer, but keep any `compress` middleware off these paths; nginx needs `proxy_buffering off`.
- **A login in front (Authelia…)** must let `/api/v1/` through, or the Android app cannot sign in: see [API v1](#api-v1).

Traefik, with the app on the proxy's network:

```yaml
    labels:
      - traefik.enable=true
      - traefik.docker.network=proxy
      - traefik.http.routers.d2n.rule=Host(`music.example.com`)
      - traefik.http.routers.d2n.entrypoints=websecure
      - traefik.http.routers.d2n.tls=true
      - traefik.http.services.d2n.loadbalancer.server.port=8080
    networks:
      - proxy
```

nginx:

```nginx
location / {
    proxy_pass http://deezer-to-navidrome:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # task streams (SSE)
    proxy_read_timeout 1h;
    client_max_body_size 16m;     # the largest request the app takes
}
```

<a id="upgrading"></a>
### Upgrading

Pull the new image and restart: `docker compose pull && docker compose up -d`. Settings, playlists and histories carry over; the app updates what it keeps at its first start. **New**, in the app, shows what changed and starts with what to change, all versions you skipped together. The same list:

#### 1.20.0

- *Recommended*: in **Settings → Stats and sign-in → Sign-in and other apps**, make your recovery code and keep it somewhere safe. Without it, a forgotten Super-Admin password needs the one-time code the app writes in its data folder.
- At its first start, the app makes your account the Super-Admin, owner of every Navidrome and Deezer account; its devices stay signed in and CatBoard keeps its token. Add the other accounts in **Settings → Users**.

#### 1.19.0

- *Recommended, behind a reverse proxy*: `TRUSTED_PROXIES=1` and `COOKIE_SECURE=true` in `.env` (see [Behind a reverse proxy](#behind-a-reverse-proxy)).
- *Optional*: `PUID=1000` and `PGID=1000` to run as your user instead of root. The music and playlist folders must be writable by that user first (the data folder is given to it at start).
- At its first start, the app makes the library index's keys again from the tags it holds, without reading your files: names in every script now match.

#### 1.18.0 and 1.17.0

- *Required behind Authelia or another login proxy*: let `/api/v1/` through without the login page, for the Android app:

  ```yaml
  - domain: music.example.com
    resources: ["^/api/v1/"]
    policy: bypass
  ```

#### 1.16.0

- *Recommended*: `D2N_ENCRYPTION_KEY=a-long-random-string` in `.env`, so a copy of the data folder does not carry the key along.

#### 1.14.0

- *Recommended*: mount your music folders writable (no `:ro`), so Fix missing metadata can write tags.

#### 1.13.0

- *Recommended, to import your past plays*: mount Navidrome's data folder, and Maloja's if you had it, read-only:

  ```yaml
  - /path/to/navidrome/data:/import/navidrome:ro
  - /path/to/Maloja:/import/maloja:ro
  ```

- *Recommended, to record new plays*: in Navidrome, `ND_LISTENBRAINZ_BASEURL=http://deezer-to-navidrome:8080/apis/listenbrainz/1/`, then link ListenBrainz with the token from **Settings → Listening stats**.

#### 1.11.1

- *Required if you downloaded with 1.10.0 to 1.11.0*: run **Repair downloads** (Settings → Library index), then **Refresh library**.

#### 1.10.0

- *Required if you ran the deezer-downloader container*: delete its service and `DEEZER_DL_BASE_URL`, and mount your downloads folder here, writable: `- /path/on/host/deezer-dl:/music/deezer-dl`.

---

<a id ="configuration"></a>
## ⚙️ Configuration

### Environment Variables

The folder and performance variables are read **on first start** to create `config.json`; after that, change them in **Settings** (no restart needed). The credentials (`DEEZER_ARL`, `APP_PASSWORD`, `API_TOKEN`…) are read on every start and take precedence over what is saved in Settings.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data` | Config, index, secrets. **Must be a persistent volume.** |
| `SCAN_DIRS` | `/music/deezer-dl,/music/library` | Music folders to index, comma-separated |
| `PLAYLISTS_BASE_DIR` | `/music/playlists` | Where the M3U8 playlists are written |
| `HOST_TO_NAVIDROME_ROOT` | `/music/deezer-dl:/deezer-dl,/music/library:/music` | Path mappings `app_path:navidrome_path`, comma-separated |
| `DEEZER_DL_DIR` | empty | Downloads folder. Empty: the music folder named `deezer-dl` |
| `LIBRARY_WORKERS_PER_DIR` | `2` | Scan threads per music folder: `2` HDD, `4` RAID, `8` SSD/NVMe |
| `MATCH_WORKERS` | `4` | Matching threads; set it to your CPU count |
| `METADATA_WORKERS` | `4` | Files Fix missing metadata handles at once; up to your CPU count, about 80 MB of memory each, 2 on a spinning disk |
| `DOWNLOAD_WORKERS` | `4` | Downloads running at the same time |
| `DEEZER_ARL` | — | `arl` cookie of a Deezer account, the default one (mixes, release feed, downloads) |
| `DEEZER_ARL_PREMIUM` | — | `arl` of a Deezer account marked for the downloads |
| `SECRET_KEY` | random, kept in `secrets.json` | Session signing key |
| `D2N_ENCRYPTION_KEY` | random, kept in `encryption.key` | Key the saved credentials are encrypted with: any long random string |
| `APP_USERNAME` / `APP_PASSWORD` | — | The Super-Admin; else the first visit asks you to create it |
| `API_TOKEN` | — | The Super-Admin's token for other apps; else create one in Settings |
| `SCROBBLE_TOKEN` | — | Token Navidrome sends the first account's plays with; else create one in Settings |
| `SCROBBLE_TOKEN_ND2`… | — | Token of the other Navidrome accounts, by their ID |
| `STATS_NAVIDROME_DB` | `/import/navidrome/navidrome.db` | Navidrome's database, for importing your history |
| `STATS_MALOJA_DB` | `/import/maloja/malojadb.sqlite` | Maloja's database, for importing your history |
| `DISABLE_AUTH` | `false` | `true` turns sign-in off (a reverse proxy already asks for a login) |
| `COOKIE_SECURE` | `false` | `true` makes the session cookie HTTPS-only |
| `TRUSTED_PROXIES` | `0` | How many reverse proxies stand in front of the app. Set it (usually `1`) behind a proxy, so the limit on failed sign-ins counts each visitor's own address rather than the proxy's. Leave it at `0` otherwise: anyone could then pretend to be another address |
| `PUID` / `PGID` | — | Run the app as this user and group instead of root. The data folder is given to them at start; the music and playlist folders must already be writable by them |

Only `DEEZER_ARL`, `DEEZER_ARL_PREMIUM`, `API_TOKEN`, `SCROBBLE_TOKEN` and `SCROBBLE_TOKEN_ND2`… replace a saved credential. The files named in Settings (library cache, scan state, playlists list) stay inside `DATA_DIR`: a path elsewhere is replaced by the default one.

#### Folders

**Supported audio formats:** `.mp3`, `.flac`, `.m4a`, `.aac`, `.ogg`, `.opus`, `.wav`, `.wv`, `.mp4`

Each playlist gets its own folder under `PLAYLISTS_BASE_DIR`:
```
/music/playlists/
├── My Playlist/
│   ├── My Playlist.m3u8
│   ├── report.json
│   └── missing.txt
└── My Playlist [xp-csv-…]/   # a second playlist with the same name
```

The folder is chosen once and kept: Navidrome knows a playlist by its file, so a title changed on Deezer keeps the same file. A second playlist with a name already taken gets its ID in its folder's name.

#### Path mappings (`HOST_TO_NAVIDROME_ROOT`)

The app and Navidrome usually see the same files under different paths. The mappings translate them so the M3U8 files point where Navidrome looks.

```env
HOST_TO_NAVIDROME_ROOT=/music/deezer-dl:/deezer-dl,/music/library:/music
```

- The app sees: `/music/deezer-dl/songs/Artist - Song.mp3`
- Navidrome sees: `/deezer-dl/songs/Artist - Song.mp3`
- The M3U8 contains the Navidrome path

Both containers must see the same files under their mapped paths. The downloads folder needs a mapping too, or downloaded tracks are left out of the playlists Navidrome reads.

#### Performance

- Each music folder gets its own pool of `LIBRARY_WORKERS_PER_DIR` threads, so several disks are scanned in parallel. More than 2 threads on a spinning disk causes seeks and slows the scan down.
- `MATCH_WORKERS` threads run on separate cores (rapidfuzz releases the GIL). Set it to the `cpus` value of your compose file.
- `DOWNLOAD_WORKERS`: Deezer throttles requests, so a low number is safer.

#### Sign-in and accounts

The web interface asks for a sign-in. On the first visit, the app asks you to create the first account, the **Super-Admin** (password of 8 characters or more, stored hashed in `data/users.json`), unless `APP_USERNAME` and `APP_PASSWORD` are set.

- **Three privileges.** The Super-Admin, never removed, manages everyone. An **Admin** manages the Standard accounts and the server's settings; only the Super-Admin makes an Admin Standard again, and Admins do not change each other. A **Standard** account has its own profiles and settings, and never the server's.
- **Settings → Users** (Admins) adds an account with a temporary password: its user chooses their own at the first sign-in. It edits an account's username, privilege and password, and removes one: its Navidrome and Deezer accounts go to another account, or with it.
- **Each account its own profiles.** Its Navidrome accounts, its Deezer accounts, its downloads account, its API token, CatBoard webhook and devices. A Navidrome user belongs to one account of the app only; a Deezer account can be shared (**Share**), and is then used, never changed, by the others. The picker at the top shows your own profiles only, Admins too: an Admin manages another account's in **Settings → Accounts → Accounts of**.
- **Admins only:** the General settings, Rebuild from scratch, applying duplicates, Made for you's disk limits and Reset data. Everyone: Refresh library, Fix missing metadata, Repair downloads, and **Clear your profiles**.
- **Forgot your password?** Each account has a **recovery code**, shown once, at the first sign-in, then when made again in **Settings → Sign-in and other apps** (or by an Admin for a Standard, by the Super-Admin for an Admin). On the sign-in page, **Forgot your password?** takes the username, the code and a new password. The Super-Admin without its code can have a one-time code written in `data/recovery-code.txt`, valid 15 minutes.
- **From an older version.** Your account becomes the Super-Admin and keeps everything: its profiles, Deezer accounts, token, webhook and signed-in devices.

- After 5 failed sign-ins in 15 minutes, the address waits 30 s, then twice as long after each new failure (up to 15 min). Failures on one username from everywhere at once wait after 50, so someone guessing from the internet cannot lock you out. Behind a reverse proxy, set `TRUSTED_PROXIES` so each visitor's own address is counted.
- Forms and scripts from another site cannot post to the app (browsers say where a request comes from), even with `DISABLE_AUTH`. Requests over 16 MB are refused.
- Changing the password (**Settings → Sign-in and other apps**) signs out your other browsers and your devices.
- The API token is sent as `Authorization: Bearer <token>` and only opens `GET /api/releases`, `POST /search/library-check` and `GET /api/version`. `GET /api/releases` answers the feed of the profiles the account chose for CatBoard, as one.
- **Devices** (the Android app) sign in through the API and each get their own token. **Settings → Sign-in and other apps** lists them, with when they were last used, and signs one out. See [API v1](#api-v1).

#### Navidrome accounts

**Settings → Navidrome accounts** lists the Navidrome users this app works for: the address of your Navidrome, a user name and its password (Navidrome does not accept API keys yet). **Test** signs in through the Subsonic API and says whether the user is an admin and which libraries it sees; with Navidrome's database mounted, it also finds the user there, so its plays and stars can be told apart.

- Your install becomes the first account and keeps working as before. A Navidrome user can belong to one account of this app only.
- **Profile**, at the top of the page, chooses the Navidrome user of this browser. Each browser, and the phone, keeps its own.
- Passwords are encrypted with `D2N_ENCRYPTION_KEY`, else with a key generated in `data/encryption.key`. They are never shown again, never sent back by the API, and never written in a log. Requests to Navidrome carry them in a POST body, never in a URL.
- **Playlists per user.** A playlist goes to the accounts ticked under **In Navidrome** in its drawer. For each, the app creates a private playlist as that user through the Subsonic API and replaces its content at each update, in place (the playlist keeps its ID in every app). Tracks are found by their path in Navidrome's database (mounted at `/import/navidrome`); without it, by their tags. Tracks Navidrome has not scanned yet are added later, and failures are tried again every 10 minutes. Only playlists the app made itself are ever touched.
- **The install's account keeps its `.m3u8` files** (owned by Navidrome's first admin) until **Publish as this user…** in Settings: the app publishes its playlists through the API, then removes its own `.m3u8` files and the copies Navidrome imported from them. If Navidrome refuses one, what was made is undone and nothing changes.
- Playlists added go to the account of the browser, the dashboard shows that account's playlists, and **Delete** takes a shared playlist away from this account only. A deleted playlist also leaves Navidrome: Navidrome keeps a playlist it imported from a `.m3u8` even once the file is gone, so the app removes that copy through the API when the account has its password.
- **In step with Navidrome.** Every 10 minutes, and when the dashboard opens, the app reads each user's playlists: a playlist of the app deleted there leaves that profile (and the app when no other profile has it), and one renamed there keeps its new name. If every playlist of the app vanishes at once, the app takes it as a reset of Navidrome and publishes them again. **Also in Navidrome** shows, read-only, the playlists the user made by hand there.
- Each account chooses its Deezer account under **Deezer account** in its form: see below.
- Each profile has its own listening history and its own Made for you: see [Histories per profile](#histories-per-profile) and [Made for you per profile](#made-for-you-per-profile).

#### Deezer accounts

**Settings → Deezer accounts** lists the Deezer accounts the app reads. **Add an account** takes a name and an ARL, checked by signing in to Deezer, then kept encrypted and never shown again. Each account can be edited, checked again or removed (not the last one).

- **Releases and mixes per profile.** Each Navidrome account follows the releases and the Deezer mixes (Flow, made for you) of the Deezer account chosen in its form, else of the default one (**Make default**). Two profiles on the same Deezer account share its feed and its muted artists.
- **Use for download.** Each account of the app marks the one that fetches its downloads. Mark a premium account for FLAC.
- **Share.** A Deezer account belongs to the account of the app that added it. **Share** lets other accounts use it for their profiles and downloads; they never see its ARL, and only its owner (or an Admin) changes it.
- **From an older version.** Your account becomes the first one, the default; the premium account used for downloads becomes a second one, marked for the downloads. `DEEZER_ARL` and `DEEZER_ARL_PREMIUM` keep working: such an account shows the variable, and its ARL is changed there.
- The mixes followed before keep their ID. A mix of another account carries it in its ID (`mix-dz2-flow-chill`), so two Flows never mix up, and a scan reads it with that account.
- A removed account takes its feed along, and the profiles that had chosen it go back to the default one.
- The API token (CatBoard) reads the feeds of the profiles chosen under **Profiles CatBoard reads**, as one; all your profiles when none is chosen.

Generate a `SECRET_KEY`, a `D2N_ENCRYPTION_KEY` or a token with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### CatBoard

[CatBoard](https://github.com/CatChow0/catboard) shows the release feed in its Calendar and New releases widgets:

1. In this app, **Settings → Sign-in and other apps**: create an API token.
2. In CatBoard, **Settings → Integrations → Deezer to Navidrome**: enter this app's URL and the token, then save.
3. Copy the **webhook URL** CatBoard shows, and paste it under **CatBoard webhook** here; **Send a test** checks it.

The app then calls the webhook when the release feed is refreshed (or an artist is muted) and when the library index is refreshed, so CatBoard reloads right away instead of polling.

### Settings page

Settings has four spaces, chosen at the top (and kept in the address, `#settings/accounts`), with **Maintenance** under each:

- **General** (Admins): **Music folders**, **Navidrome paths** (mappings), **Downloads** folder (with the folder actually used and a warning if it is missing)
- **Performance**: scan, download and matching threads
- **Release feed**: refresh interval (6 h to weekly, or manual only)
- **Data files**: where the app keeps its state
- **Accounts**: **Navidrome accounts**, the users the app works for, and the Deezer account of each; **Deezer accounts**, their badges, the default one, the one used for your downloads, and sharing
- **Stats and sign-in**: **Listening stats**; **Sign-in and other apps**, password, recovery code, devices, API token, the profiles CatBoard reads, and its webhook
- **Users** (Admins): the accounts of the app
- **Library index**: refresh, or rebuild (Admins)
- **Clear your profiles**: match results, covers or playlists of your own profiles (two clicks each)
- **Reset data** (Admins): clear the index, match results, playlists, duplicate report or decisions (two clicks each)

Changes are saved to `config.json` and apply at once.

---
<a id ="usage"></a>
## 📖 Usage

### Typical Workflow

#### 1. Configure

Open **Settings**, check the music folders and the Navidrome paths, make sure the downloads line under **Downloads** is green, and add your Deezer account.

#### 2. Build the library index

**Settings → Library index → Rebuild from scratch** the first time (progress in Activity). Afterwards, **Refresh library** (Dashboard or Settings) only reads new and changed files.

#### 3. Add playlists

On the Dashboard, **Playlists → From Deezer** lists the playlists of the profile's Deezer account (**Your playlists**: Loved tracks, those you made and your favorites, private ones too), the mixes Deezer makes for it (**Mixes**) and the playlists it recommends (**Recommended**): **Add** or **Follow** one. You can also paste a Spotify link or a public Deezer playlist's link or ID, or import a CSV (see [Playlists from other platforms](#other-platforms)). The mixes you follow sit with your playlists, marked **Mix**.

#### 4. Scan

Open a playlist and run a scan:

| Button | Behaviour |
|--------|-----------|
| **Quick scan** | Keeps the tracks already in your library and only re-checks the missing and unchecked ones |
| **Full scan** | Matches every track again. Use it after reorganizing your library |

Both write the M3U8, `report.json` and `missing.txt`. Tracks are shown as **In library**, **Missing** or **Not checked**; filter the list with the buttons above it.

A wrong or missing match can be corrected with **Fix**: search your library and **Use this file**, or choose **Not in my library**. **Back to automatic matching** undoes it.

#### 5. Download what is missing

- **Download missing** in the playlist queues every missing track.
- Each missing row also has its own **Download** button.
- Then **Refresh library** and run a **Quick scan** so the new files count as *In library*.

#### 6. Automate (optional)

In the playlist drawer, **Automation**:
1. Enable the automatic scan and set its interval (minutes, hours or days)
2. Optionally download the missing tracks after each scan
3. Save

The scheduler then scans the playlist, queues the missing tracks, and refreshes the library index after its scans; tracks downloaded during one run are picked up by the next. The playlist tile shows the automation chips and the time until the next scan.

### Search

**Find music on Deezer** searches tracks, albums and artists. Chips show what you own:

- **Tracks:** *Owned* when the file is in your library
- **Albums:** `owned / total tracks`, amber when partial, green when complete
- **Artists:** `owned / total albums`

Every result can be previewed (30 s) and downloaded: a track, a whole album, or an artist's discography.

### Releases

The **Releases** view lists recent albums, EPs and singles of your favorite Deezer artists (needs a connected account), with what you already own. It refreshes on the interval set in Settings, or with **Refresh now**. Mute an artist in **Artists you follow** to hide their releases.

### Duplicates

1. **Your library → Find duplicates**
2. Groups are shown per album, with one column per music folder and the quality of each file
3. Check the files to **keep** (your previous choices are pre-selected)
4. **Quarantine** (moved to `/data/dedup_quarantine/`) or **Delete** the others
5. Decisions are saved and survive restarts

---
<a id ="api-reference"></a>
## 🔌 API Reference

All routes need a signed-in session or a device's token, except `/health`, the three routes the API token opens, and the sign-in routes of API v1.

### API v1

The API the Android app uses, described in [`docs/api/openapi.yaml`](docs/api/openapi.yaml). Everything a phone needs lives under `/api/v1/`, media and task streams included.

- **Sign-in.** `POST /api/v1/auth/login` with the account's username and password and a name for the device returns a token (`d2n_…`), shown once; send it as `Authorization: Bearer <token>`. Only a SHA-256 digest is kept, in `data/devices.json`. The token opens every route; it stops working when the device signs out (`POST /api/v1/auth/logout`), is signed out in Settings, or when the password changes. Failed attempts count as on the web sign-in page. `GET /api/v1/auth/status` (public) says whether the server needs a sign-in, has no account yet (`POST /api/v1/auth/setup` creates it), or has sign-in turned off.
- **Answers.** A JSON object; a failure is `{"error": {"code", "message"}}` with the matching HTTP status. Reads carry an ETag: send it back in `If-None-Match` to get a 304 when nothing changed. The profile comes from the `X-Navidrome-Account` header, else the default account.
- **The whole web interface.** Each of its functions has its counterpart here, and a test checks that none is missing. Most are the web's own functions answering in this format, so the two cannot drift apart. The covers and the audio the answers link to are under `/api/v1/` too.
- **Tasks.** `GET /api/v1/tasks/<id>/stream` is the event stream the web page follows (resume with `Last-Event-ID` or `?from=`). Without a stream, `GET /api/v1/tasks/<id>/events?after=N&wait=25` returns the events after index `N`, waiting up to 25 s for the next one, and `GET /api/v1/tasks?changed_since=<time>` lists the tasks that changed.
- **Behind Authelia, or another login proxy.** The app cannot get through a login page. Let `/api/v1/` through without it: the device token protects it. For Authelia:

  ```yaml
  access_control:
    rules:
      - domain: music.example.com
        resources: ["^/api/v1/"]
        policy: bypass
  ```

  Keep the rest of the site behind the proxy's login. With `DISABLE_AUTH=true` the app needs no token, so only do this when the API is not reachable from the internet (Tailscale, local network).

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/auth/status` | GET | Public: whether a sign-in is needed |
| `/api/v1/auth/login`, `/api/v1/auth/setup` | POST | Sign a device in; create the account on a new server |
| `/api/v1/auth/logout` | POST | Sign this device out |
| `/api/v1/devices`, `/api/v1/devices/<id>` | GET/DELETE | The devices signed in; sign one out |
| `/api/v1/info` | GET | Version, profiles, Deezer accounts, what this install can do |
| `/api/v1/tasks`, `/api/v1/tasks/<id>` | GET | Tasks and one task's state |
| `/api/v1/tasks/<id>/events`, `/stream` | GET | A task's events: waiting for the next, or as a stream |
| `/api/v1/tasks/<id>/cancel` | POST | Ask a task to stop |
| `/api/v1/playlists` | GET/POST | The profile's playlists, and those its user made in Navidrome; add one by its link (`{"link"}`) |
| `/api/v1/playlists/import` | POST | Import a CSV export (multipart `csv_file`) |
| `/api/v1/playlists/<id>` | DELETE | Take a playlist off the profile; deleted when no other profile has it |
| `/api/v1/playlists/<id>/tracks`, `/navidrome` | GET | Its tracks and their matches; where it is in Navidrome |
| `/api/v1/playlists/<id>/scan`, `/download-missing`, `/publish` | POST | Scan it, download what it misses (tasks); publish it again |
| `/api/v1/playlists/<id>/match`, `/source-match` | POST | Fix a match by hand; pick the Deezer track of an imported one |
| `/api/v1/playlists/<id>/accounts`, `/automation` | PUT | The accounts it goes to; its schedule |
| `/api/v1/navidrome/playlists/<account>/<id>` | GET | A playlist made in Navidrome, read-only |
| `/api/v1/releases`, `/releases/refresh`, `/releases/mute` | GET/POST | The profile's release feed |
| `/api/v1/deezer/mixes`, `/deezer/mixes/follow` | GET/POST | Deezer's mixes for the profile; follow one |
| `/api/v1/search`, `/search/album/<id>`, `/search/artist/<id>`, `/preview/<id>` | GET | Deezer search, details and 30-second previews |
| `/api/v1/library/stats`, `/search`, `/check`, `/refresh`, `/rebuild`, `/metadata/fix`, `/metadata/undo` | GET/POST | The library: figures, search, what it has, its index, its metadata |
| `/api/v1/downloads`, `/downloads/track/<id>`, `/downloads/repair` | GET/POST | The queue; download a track, an album or an artist; repair |
| `/api/v1/dedup/start`, `/dedup/report`, `/dedup/apply` | POST/GET | Duplicates |
| `/api/v1/stats/…` | GET/POST/DELETE | Overview, recaps, an artist, album or track, plays, status, rebuild, ListenBrainz token, covers and audio |
| `/api/v1/mixes`, `/mixes/settings`, `/mixes/generate`, `/mixes/trial/…` | GET/POST | The profile's Made for you and its quarantine |
| `/api/v1/navidrome/accounts…`, `/api/v1/deezer/accounts…` | GET/POST/PATCH/DELETE | The accounts, as in Settings |
| `/api/v1/settings` | GET/PUT | Folders, mappings and limits; a PUT changes only what it sends |
| `/api/v1/settings/clear/<what>` | POST | Reset data: `library-cache`, `preview-state`, `playlists`, `all`, `dedup-report`, `dedup-choices` |
| `/api/v1/settings/security`, `/password`, `/api-token`, `/webhook`, `/webhook/test` | GET/POST/PUT/DELETE | Sign-in and other apps |
| `/api/v1/scheduler`, `/api/v1/version` | GET | The scheduled scans; this version and the newest one |
| `/api/v1/content/help`, `/content/notes`, `/content/notes/seen` | GET/POST | The help and the notes of each version, in HTML |
| `/api/v1/app`, `/api/v1/app/apk` | GET | The Android app in this image (version, size, SHA-256), and its APK |

### Web routes

#### Playlists

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Dashboard |
| `/releases` | GET | Releases view |
| `/playlist/add` | POST | Add a Deezer playlist, or a Spotify playlist by its link |
| `/playlist/import-csv` | POST | Import a CSV export (multipart `csv_file`) |
| `/playlist/<id>/source-match` | POST | Imported playlists: `{"key", "deezer_id"}` picks a Deezer track, `null` marks it not on Deezer, `"auto"` goes back |
| `/playlist/<id>/delete` | POST | Remove a playlist |
| `/playlist/<id>/preview` | GET | Match results |
| `/playlist/<id>/convert` | POST | Scan and write the M3U8 (blocking) |
| `/playlist/<id>/convert/start` | POST | Same, as a task — body `{"mode":"quick"\|"full"}` |
| `/playlist/<id>/match` | POST | Fix a match by hand, or go back to automatic matching |
| `/playlist/<id>/automation` | POST | Save the automation settings |
| `/playlist/<id>/download-missing/start` | POST | Download the missing tracks (task) |
| `/api/scheduler/status` | GET | Next automatic scan of each playlist |

#### Downloads

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/deezer-dl/download/start` | POST | `{"type":"track"\|"album"\|"artist", "music_id":…, "label":…}` → `{"task_id"}` |
| `/deezer-dl/track/<id>` | POST | Download one track; optional `{"playlist_id"}` marks the playlist row |
| `/deezer-dl/queue` | GET | State of the download queue |

#### Library and cache

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/library/stats` | GET | Size of the library index |
| `/api/library/search` | GET | Search the index (used by **Fix**) |
| `/cache/full/start` | POST | Full rebuild (task) |
| `/cache/incremental/start` | POST | Incremental refresh (task) |
| `/cache/rebuild`, `/cache/refresh` | POST | The same, blocking |

#### Duplicates

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/dedup/start` | POST | Start the analysis (task) |
| `/dedup/report` | GET | Latest report |
| `/dedup/apply` | POST | Quarantine or delete |

#### Deezer search, account and releases

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search` | GET | Search Deezer |
| `/search/album/<id>`, `/search/artist/<id>` | GET | Album or artist details |
| `/search/library-check` | POST | Which tracks, albums and artists you own (API token accepted) |
| `/api/preview/<track_id>` | GET | 30-second preview URL |
| `/api/deezer/accounts` | GET/POST | The Deezer accounts and the downloads status; add one |
| `/api/deezer/accounts/<id>` | PATCH/DELETE | Edit (name, ARL), remove |
| `/api/deezer/accounts/<id>/default`, `…/download`, `…/check` | POST | Make default, use for download, check again |
| `/api/deezer/account` | GET | The Deezer account of this browser's profile |
| `/api/deezer/mixes`, `/api/deezer/mixes/follow` | GET/POST | List and follow the mixes of the profile's Deezer account |
| `/api/releases` | GET | Release feed of the profile's Deezer account (API token accepted: the default profile's) |
| `/api/releases/refresh`, `/api/releases/mute` | POST | Refresh that feed, mute an artist in it |

#### Made for you

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/mixes` | GET | Settings, metadata status and quarantine of this browser's profile |
| `/api/mixes/settings` | POST | Mode (`mix_mode`: `off`, `daily`, `blend`), `discover`, limits and trial rules (`trial_*`, `trash_days`) |
| `/api/mixes/generate` | POST | Build what is turned on now |
| `/api/mixes/trial/<id>/keep`, `/remove`, `/restore` | POST | Decide about one track |
| `/api/mixes/trial/<id>/cover` | GET | The picture inside a track's file |
| `/api/mixes/trial/keep-pending` | POST | Keep the given tracks waiting under To review (`ids`) |
| `/api/mixes/trial/empty-trash` | POST | Delete everything in the trash now |
| `/api/mixes/trial/remove-pending` | POST | Remove everything waiting under To review |
| `/api/metadata/fix`, `/api/metadata/undo` | POST | Start Fix missing metadata, or undo it |

#### Listening stats

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/stats` | GET | The Stats tab |
| `/api/stats/overview`, `/api/stats/recaps`, `/api/stats/recap` | GET | Tops of a period, the recaps there are, one recap |
| `/api/stats/<artist\|album\|track>/<id>`, `/api/stats/plays` | GET | One artist, album or track; the plays, searchable |
| `/stats/cover/<kind>/<id>`, `/stats/audio/<id>` | GET | A cover, the audio a recap plays |
| `/api/stats/status`, `/api/stats/token` | GET, POST/DELETE | The profile's history and sources; its scrobble token |
| `/api/stats/import`, `/api/stats/import/preview` | POST | Rebuild the history (`merge` or `clean`), and what Start clean would do |
| `/apis/listenbrainz/1/submit-listens`, `/validate-token` | POST, GET | Where Navidrome sends new plays (its own token, no session) |

#### Navidrome accounts

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/navidrome/accounts` | GET/POST | List the accounts, add one |
| `/api/navidrome/accounts/<id>` | PATCH/DELETE | Edit or remove one (another server needs its password again) |
| `/api/navidrome/accounts/<id>/test`, `/api/navidrome/accounts/test` | POST | Test a saved account, or what the form holds |
| `/api/navidrome/accounts/<id>/default` | POST | Make it the default |
| `/api/navidrome/accounts/<id>/switch` | GET/POST | What Publish as this user would do, then do it |
| `/api/navidrome/active` | POST | The profile of this browser |
| `/api/navidrome/playlists/<id>/<playlist>`, `/navidrome/cover/<id>/<cover>` | GET | A playlist made by hand in Navidrome, its cover |

#### System

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/config` | GET/POST | Settings |
| `/admin/clear/<what>` | POST | `library-cache`, `preview-state`, `playlists`, `dedup-report`, `dedup-choices`, `all` |
| `/tasks/<id>/stream` | GET | Task progress (Server-Sent Events) |
| `/api/tasks` | GET | Running and recent tasks |
| `/api/tasks/<id>/cancel` | POST | Stop a task that can be cancelled |
| `/health` | GET | Health check |
| `/api/version`, `/api/latest-version` | GET | Current and latest version |
| `/login`, `/logout`, `/setup` | GET/POST | Sign-in |
| `/api/auth/password`, `/api/auth/token` | POST | Change the password, create the API token |
| `/api/webhook`, `/api/webhook/test` | PUT/DELETE/POST | CatBoard webhook |
| `/app/android.apk` | GET | The Android app's APK, for a signed-in browser |

---
<a id ="android-app"></a>
## 📱 Android app

The app for your phone, in Kotlin and Jetpack Compose (Android 8 or later). It does what the web interface does, for the Navidrome profile picked at the top:

- **Dashboard** and **Search**: the profile's playlists, adding one by link, ID or CSV (or by sharing a Deezer or Spotify link to the app), and Deezer search with previews and downloads.
- **Playlists**: scans, downloading what is missing, choosing a file or a Deezer match per track, automation.
- **Made for you**: the mixes, their limits and trial rules, and the quarantine (swipe to keep or remove).
- **Stats**: tops, charts, artist, album and track pages, and the recaps as stories.
- **Releases**, and every section of **Settings**, **Activity**, **What's new** and **Help** under More.

When the server cannot be reached, the app says so and shows the pages it saved, for the same profile only; nothing is changed until the server answers again.

### Installing

Each image built by Jenkins carries the app built with the same version.

1. On your phone, open the web interface signed in, then **Settings → Android app → Download the app**. Android asks once to allow installs from your browser.
2. Open the app, enter the server's address as you open it in a browser, and sign in with your account. The phone appears in **Settings → Sign-in and other apps**, where you can sign it out.
3. Pick the profile at the top: the Navidrome account the app shows.

An `http://` address works, with a warning: only on your local network or Tailscale. Behind Authelia, or another login proxy, let `^/api/v1/` through as shown under [API v1](#api-reference): the app cannot pass a login page, and says so.

### Updates

The app shares the server's version. When the server is newer, the app shows a banner: **Update** downloads the APK from your server, checks its SHA-256 and opens Android's installer; Android asks once to allow installs from D2N. **More → Check for updates** asks at once.

- `versionCode` is `MAJOR×10000 + MINOR×100 + PATCH` (1.18.0 gives 11800).
- A newer build of the same version (a DEV image) is offered too; a lower version, or an older build, never is.
- Before Android gets it, the app checks the file is this app, signed with the same key, and not older: the SHA-256 comes from the same server, so it only proves the file arrived whole.
- Signing out (on the phone, from the web, or by a new password) clears what the phone saved from the server and its downloaded updates.
- An image built without the signing key (a fork, say) carries no app, and Settings says so.

### The signing key

Every build is signed with one key, so each version installs over the previous one. **Back it up with its password: without them, phones must uninstall the app to update it.**

- **Create it once,** in a PowerShell window of your own: `powershell -File android\scripts\new-keystore.ps1`. It writes `%USERPROFILE%\.d2n-android\release.jks`, and saves the password encrypted for your Windows account (`keystore-password.dpapi`). On Linux or macOS: `android/scripts/new-keystore.sh`.
- **Restore it** on a new PC: put `release.jks` back in `%USERPROFILE%\.d2n-android\`, then save its password again:

  ```powershell
  Read-Host "Password" -AsSecureString | ConvertFrom-SecureString | Set-Content -Encoding ascii "$env:USERPROFILE\.d2n-android\keystore-password.dpapi"
  ```

### Building

The build runs in Docker (`android/Dockerfile`), the same in Jenkins and on a PC, and writes `dist/android/deezer-to-navidrome.apk` with `app.json`. `docker build .` then puts them in the image.

- **On Windows:** `powershell -File android\scripts\build-apk.ps1`, with the saved key.
- **Elsewhere:** `D2N_KEYSTORE_FILE=… D2N_KEYSTORE_PASSWORD=… android/scripts/build-apk.sh`.

`android/README.md` covers working on the app itself: the local SDK, the tests and the emulator.

### Jenkins

The `Android` stage builds the app before the image, keeps the APK as a build artifact, and the smoke test checks the image carries it.

- **Credentials:** `android-keystore`, a secret file holding `release.jks`, and `android-keystore-password`, a secret text.
- **Without them,** `main` fails, since an image on Docker Hub without its app would break updates; other branches build without the app, with a warning.
- **The agent** needs Docker with buildx (build secrets and `--output`), access to `dl.google.com`, `maven.google.com`, Maven Central and `services.gradle.org`, and about 6 GB free. The first build downloads the SDK and takes several minutes; the pipeline's timeout is 45 minutes.

---
<a id ="troubleshooting"></a>
## 🛠️ Troubleshooting

### Downloaded files play with noise, skip, or do not play in Navidrome

Versions 1.10.0 to 1.11.0 decrypted the downloads wrongly (8 wrong bytes every 6 KB). Update, then run **Settings → Library index → Repair downloads**: it checks every file of the downloads folder saved since 1.10.0, downloads it again, and replaces it only if it is byte for byte what the faulty versions produced, keeping its tags. Files it cannot identify on Deezer, and files that are fine (from another downloader, for instance), are left as they are. Then run **Refresh library**.

New downloads also carry the Deezer id of the track in a `DEEZER_TRACK_ID` tag.

### Downloads fail

**Check, in this order:**
1. **Settings → Deezer accounts** has an account, and the line under the list names the one used for downloads and its format. Without an account, nothing can be downloaded.
2. **Settings → Downloads** shows a green line. A red one means the folder does not exist or cannot be written to: mount it as a writable volume.
3. The reason of each failure is shown in **Activity** and in the tooltip of the **Retry** button. "Deezer returned no download link for this track" usually means the track is not available for your account or your country.

**Only MP3 128 kbps?** The account used for downloads is free. Add a premium account in **Settings → Deezer accounts** and mark it **Use for download** to get FLAC.

**The ARL stopped working?** Deezer session cookies expire or get revoked when you sign out of deezer.com. Copy a fresh one.

### Downloaded tracks still shown as Missing

The library index does not know the new files yet. Run **Refresh library**, then a **Quick scan** of the playlist. With automation, the next automatic scan picks them up.

### Downloaded tracks missing from Navidrome playlists

The downloads folder needs a path mapping in **Settings → Navidrome paths**, and Navidrome must see that folder too.

### Playlists not converting

1. **Library index empty** — build it first
2. **Path mapping wrong** — check **Navidrome paths**
3. **Permissions** — `PLAYLISTS_BASE_DIR` not writable

```bash
docker logs deezer-to-navidrome
docker exec deezer-to-navidrome ls -la /music
```

### No matches found

**Likely causes:**
1. **Tags** — files lack artist/title tags, and the file names do not carry them either
2. **Artist names** — the artist must match closely; fix the odd ones with **Fix**
3. **Wrong folders** — `SCAN_DIRS` points to empty folders

```bash
docker exec deezer-to-navidrome python -c "from mutagen import File; print(File('/music/path/to/file.mp3'))"
```

### Library scan or matching is slow

- Set `cpus` in `docker-compose.yml` to your actual core count
- Match `LIBRARY_WORKERS_PER_DIR` to your storage: `2` HDD, `4` RAID, `8` SSD
- Set `MATCH_WORKERS` to your CPU count
- Prefer **Refresh library** over a full rebuild, and **Quick scan** over **Full scan**

### Duplicates keep reappearing

`DATA_DIR` is not persistent. Mount it as a volume:
```yaml
volumes:
  - ./data:/data
```

### Version shows "unknown"

The `VERSION` file is missing from the image. Pull it again:
```bash
docker compose pull && docker compose up -d
```

### Disk space growing

Empty the quarantine once you are sure:
```bash
docker exec deezer-to-navidrome sh -c 'rm -rf /data/dedup_quarantine/*'
```

---
<a id ="development"></a>
## 💻 Development

### Building Locally

```bash
git clone https://github.com/CatChow0/deezer-to-navidrome
cd deezer-to-navidrome

docker build -t deezer-to-navidrome:dev .
docker run -p 8080:8080 \
  -e SCAN_DIRS=/music/lib \
  -e PLAYLISTS_BASE_DIR=/music/playlists \
  -v ./data:/data \
  -v /path/to/music:/music/lib \
  deezer-to-navidrome:dev
```

### Running Without Docker

With Python 3.12:

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

export DATA_DIR=./data
export SCAN_DIRS=/path/to/music
export PLAYLISTS_BASE_DIR=/path/to/playlists
export HOST_TO_NAVIDROME_ROOT=/path/to/music:/music

python app.py  # http://localhost:8080
```

The image runs the app with gunicorn (`gthread`, 16 threads) so task streams stay open without blocking other requests.

### Tests

```bash
python -m unittest discover -s tests -t .      # the server
cd android && ./gradlew :app:testDebugUnitTest  # the Android app
```

The tests use a throwaway data folder and never start the scheduler. Some check the documentation too: every environment variable the app reads is in the tables of both READMEs, and the Upgrading section lists what each version's notes ask to change.

### Code Structure

```
app.py                  # Flask init, blueprints, sign-in check

core/
├── config.py           # Paths, config and secrets, background tasks
├── files.py            # Files written in one step, damaged ones set aside
├── crypto.py           # Encryption of the saved credentials
├── auth.py             # Sign-in, limits on failures, API token
├── devices.py          # Devices signed in through the API
├── nd_accounts.py      # Navidrome accounts
├── subsonic.py         # Subsonic API client (Navidrome)
├── navidrome_db.py     # Reading a copy of Navidrome's database
├── publish.py          # Playlists published per user, sync with Navidrome
├── content.py          # Help and notes, for the web and the app
├── patch_notes.py      # Each version: highlights and what to change
├── library.py          # Library scanning and index (threaded, per folder)
├── matching.py         # Matching a Deezer track against the library
├── normalization.py    # Text normalization, version flags, quality score
├── deezer.py           # Deezer public API, playlists, M3U8 generation
├── crossplatform.py    # Imported playlists: matching to Deezer, picks by hand
├── xp_sources.py       # Reading a Spotify link or a CSV export
├── deezer_accounts.py  # Deezer accounts: encrypted ARLs, default and download roles
├── deezer_account.py   # Deezer sessions, one per account: mixes, favorites, status
├── deezer_dl.py        # Downloading: links, decryption, tags, file layout
├── download_queue.py   # Download queue and its worker threads
├── releases.py         # Release feed
├── scheduler.py        # Automatic playlist scans and release refreshes
├── dedup.py            # Duplicate analysis and apply
├── stats_*.py          # Listening history, imports, recaps
├── metadata_fix.py     # Fix missing metadata: tempo, genre, safe tag writing
├── audio_tempo.py      # Tempo measured from the audio
├── mix_taste.py        # Listening habits, seeds, choosing your own tracks
├── mix_candidates.py   # Tracks to download around a seed or your habits
├── mix_builder.py      # Daily Mix, Daily Mix+ and Discover
├── mixes_db.py         # mixes.db
├── trial.py            # Quarantine and its trash
├── webhook.py          # CatBoard webhook
├── utils.py            # Audio extensions, tag reading
└── version.py          # Current and latest version

routes/
├── playlists.py        # Views, /playlist/*
├── search.py           # /search/*, previews
├── account.py          # /api/deezer/*, /api/releases*
├── cache.py            # /cache/*, /api/library/*
├── dedup.py            # /dedup/*
├── stats.py            # /stats*, listening stats and recaps
├── listenbrainz.py     # /apis/listenbrainz/1/*, plays sent by Navidrome
├── mixes.py            # /api/mixes*, /api/metadata/*
├── auth.py             # /login, /setup, /api/auth/*, /api/webhook
├── navidrome_accounts.py  # /api/navidrome/accounts*
├── navidrome_playlists.py # Playlists made by hand in Navidrome
├── android.py          # The APK in the image
├── api_v1/             # /api/v1/*, for the Android app
└── system.py           # /config, /deezer-dl/*, /tasks/*, /admin/*, /health

templates/
├── base.html           # Layout, topbar, player
├── home.html           # Dashboard (+ _releases.html, _settings.html)
└── login.html          # Sign-in and first-run setup

static/
├── css/                # tokens, layers, cells, components, views…
└── js/                 # one ES module per feature (playlists, search,
                        # downloads, activity, player, releases…)
```

### Key Functions

| Function | Module | Purpose |
|----------|--------|---------|
| `scan_audio_files()` | `core/library.py` | Find all audio files (parallel, per folder) |
| `find_best_match()` | `core/matching.py` | Best library file for a Deezer track |
| `convert_playlist()` | `core/deezer.py` | Scan a playlist and write the M3U8 |
| `download_track()` / `download_album()` | `core/deezer_dl.py` | Download, decrypt and tag |
| `enqueue_download()` | `core/download_queue.py` | Queue a download with progress callbacks |
| `build_dedup_groups()` | `core/dedup.py` | Identify duplicates |

---
<a id ="notes"></a>
## 📝 Notes

- **Matching depends on tags and file names** - well-tagged files match much better
- **A Deezer account is optional** - without one, playlists, search and matching work; downloads, mixes and the release feed do not
- **Deezer's private gateway is undocumented** - downloads and mixes may break if Deezer changes it
- **Folder settings come from the environment only on first start** - then from Settings
- **Path mappings are critical** - they must match exactly how Navidrome sees the files
- **Keep `/data` private** - credentials are encrypted, but the key is in it unless you set `D2N_ENCRYPTION_KEY`
- **Download only what you are allowed to** - respect Deezer's terms and the copyright of the music

---
<a id ="license"></a>
## 📄 License

See the LICENSE file. The download code (decryption and tagging) is adapted from [deezer-downloader](https://github.com/kmille/deezer-downloader) by kmille, under the MIT licence reproduced in LICENSE.

<a id ="contributing"></a>
## 🤝 Contributing

Contributions welcome! Please submit issues or pull requests.

<a id ="support"></a>
## 🆘 Support

For bugs or questions:
1. Check this README
2. Check [GitHub Issues](https://github.com/CatChow0/deezer-to-navidrome/issues)
3. Review the app logs: `docker logs deezer-to-navidrome`
