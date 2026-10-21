# Deezer to Navidrome

**A self-hosted web app that turns your Deezer playlists into Navidrome `.m3u8` playlists, matches them against your local library, and downloads what is missing straight from Deezer.**

[![Docker Image Version](https://img.shields.io/badge/version-1.11.0-blue)](https://hub.docker.com/r/catchow/deezer-to-navidrome)
[![Python 3](https://img.shields.io/badge/python-3-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-web%20app-brightgreen)](https://flask.palletsprojects.com/)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Downloads](#downloads)
- [Cache System](#cache-system)
- [Deduplication System](#deduplication-system)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
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

- **Import Deezer playlists** by ID or URL, and follow the mixes Deezer makes for you (Flow, "made for you")
- **Index your local library** and keep that index up to date
- **Match tracks** against your files, and fix a wrong match by hand
- **Download missing tracks** directly from Deezer, with nothing else to install
- **Generate M3U8 playlists** that Navidrome imports
- **Follow new releases** of your favorite Deezer artists, with what you already own
- **Find duplicates** in your library and quarantine or delete them

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

The interface has three views: **Dashboard**, **Releases** and **Settings**. Long tasks (scans, downloads, library refreshes) run in the background and show their progress in the **Activity** cell, so the rest of the page stays usable.

The **Help** button in the topbar opens a short guide and the notes of the current version. After an upgrade from a version before 1.10, that window opens on its own once: it explains that the separate `kmille2/deezer-downloader` container is no longer needed, and checks that your Deezer account and downloads folder are ready.

### Playlists
- **Deezer playlist import** - Add playlists by ID or URL
- **Mixes** - Follow your Flow and the "made for you" mixes, or add the playlists Deezer recommends
- **Match breakdown** - Each track is shown as *In library*, *Missing* or *Not checked*, with filters
- **Quick scan / Full scan** - Re-check only what is missing, or everything
- **Manual matching** - **Fix** a track: search your library and pick the right file, or mark it as not in your library
- **M3U8 export** - Navidrome-compatible playlists, with a `report.json` and a `missing.txt`
- **Automation** - Per playlist: scan on an interval (minutes, hours or days) and download what is missing after each scan

### Search, releases and player
- **Deezer search** - Tracks, albums and artists, with album and artist details in a drawer
- **Library check** - Chips show what you already own: tracks, albums (owned / total tracks) and artists (owned / total albums)
- **Release feed** - Recent albums, EPs and singles of your favorite Deezer artists, refreshed on a schedule; artists can be muted
- **Preview player** - 30-second previews with a queue, plus the official Deezer widget for full-length listening

### Downloads
- **Built-in Deezer downloader** - Tracks, albums and whole discographies, decrypted and tagged (cover included) by the app itself
- **Progress on the button** - *Queued*, then `42%` or `3/14`, then *Downloaded*; details in Activity
- **Retry** - A failed or partly failed download can be started again; files already saved are kept
- **Two accounts** - A free account downloads MP3 128 kbps; add a premium account's ARL for FLAC, while your mixes keep using the first account

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
- **Sign-in** - One account, created on the first visit or set from the environment
- **API token** - Read-only access for other apps
- **[CatBoard](https://github.com/CatChow0/catboard)** - Shows the release feed; a webhook tells it when the feed or the library changed
- **Update badge** - The topbar shows when a newer version is on Docker Hub

---

<a id ="architecture"></a>
## 🏗️ Architecture

### System Overview

```
┌─────────────────────────┐
│  Deezer                 │
│  • Public API           │  playlists, search, artists, releases
│  • Private gateway      │  mixes, favorites, download links (needs the ARL)
│  • Media servers        │  encrypted audio files
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│  Deezer-To-Navidrome (port 8080)    │
│  • Web UI + background tasks (SSE)  │
│  • Matching engine                  │
│  • Download queue (decrypt + tag)   │
│  • Library index + dedup engine     │
│  • Scheduler (playlists, releases)  │
└─────┬─────────────┬─────────────┬───┘
      │             │             │
      ▼             ▼             ▼
┌───────────┐ ┌───────────┐ ┌────────────┐
│ Music     │ │ Downloads │ │ M3U8       │
│ folders   │ │ deezer-dl │ │ playlists  │
└─────┬─────┘ └─────┬─────┘ └─────┬──────┘
      └─────────────┼─────────────┘
                    ▼
          ┌───────────────────┐
          │  Navidrome        │
          └───────────────────┘
```

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

Downloads use the session cookie (`arl`) of a Deezer account, pasted in **Settings → Deezer account**.

| Account in Settings | Badge | Download format |
|---|---|---|
| Premium (HiFi) | `Premium` | FLAC |
| Premium with high quality only | `Premium` | MP3 320 kbps |
| Free | `Free` | MP3 128 kbps |
| Free + a premium ARL for the downloads | `Free · downloads in Premium` | FLAC from the second account |

When the first account is free, Settings shows a second field for the ARL of a **premium** account. That account is only used for downloads: your mixes and the release feed keep using the first one. A free ARL is refused in that field.

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

> Deezer's private gateway is undocumented. If Deezer changes it, downloads and mixes may stop working until the app is updated; search, playlists and the release feed use the public API and are not affected.

---

<a id ="cache-system"></a>
## 📦 Cache System

### Cache Files Overview

| File | Purpose | Lifetime |
|------|---------|----------|
| `music_library_cache.json` | Library index | Until a full rebuild |
| `deezer_playlist_ids.json` | Saved playlists and mixes, with their automation settings | Until deleted |
| `playlist_preview_state.json` | Per-playlist match results, including manual matches | Until the playlist is deleted |
| `releases.json` | Release feed | Until the next refresh |
| `release_prefs.json` | Muted artists of the release feed | Survives restarts |
| `dedup_report.json` | Latest duplicate analysis | Until a new scan |
| `dedup_choices.json` | **Persistent** duplicate decisions | Survives restarts |
| `covers/` | Playlist artwork | Until cleaned up |
| `config.json` | App configuration | Survives restarts |
| `secrets.json` | Password hash, API token, Deezer ARLs, webhook URL, session key | Survives restarts |

> `secrets.json` holds your Deezer session cookies and other credentials. Keep `/data` private and out of any backup you share.

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
   ├─ Apply to all duplicates
   ├─ Move to quarantine dir or unlink
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

    ports:
      - "8080:8080"

    environment:
      DATA_DIR: "/data"

      # Music folders to index (comma-separated). The one named deezer-dl
      # receives the downloads unless DEEZER_DL_DIR says otherwise.
      SCAN_DIRS: "/music/deezer-dl,/music/library"

      # Where the M3U8 playlists are written
      PLAYLISTS_BASE_DIR: "/music/playlists"

      # The same folders as Navidrome sees them: /in/this/app:/in/navidrome
      HOST_TO_NAVIDROME_ROOT: "/music/deezer-dl:/deezer-dl,/music/library:/music"

      # Optional: another folder for the downloads
      # DEEZER_DL_DIR: "/music/deezer-dl"

      LIBRARY_WORKERS_PER_DIR: "2"   # 2 = HDD, 4 = RAID, 8 = SSD/NVMe
      MATCH_WORKERS: "4"             # your CPU count
      # DOWNLOAD_WORKERS: "4"        # parallel downloads from Deezer

      # Optional: the Deezer account (you can paste it in Settings instead)
      # DEEZER_ARL: ""
      # DEEZER_ARL_PREMIUM: ""       # premium account used only for downloads

      # Optional: the sign-in account (else the first visit asks for it)
      # APP_USERNAME: "admin"
      # APP_PASSWORD: "a-long-password"

    volumes:
      # Config, index, secrets: must be persistent
      - ./data:/data

      # Music folders. deezer-dl must be writable: downloads go there.
      - /path/on/host/deezer-dl:/music/deezer-dl
      - /path/on/host/library:/music/library

      # Playlist output, shared with Navidrome
      - /path/on/host/playlists:/music/playlists
```

2. **Start the app:**

```bash
docker compose up -d
```

3. **Open the web UI** at `http://localhost:8080` and create your account.

4. **Connect Deezer** in **Settings → Deezer account** (optional, but needed for downloads, mixes and the release feed).

### Without Docker

```bash
pip install -r requirements.txt
export DATA_DIR=./data
export SCAN_DIRS=/path/to/library
export PLAYLISTS_BASE_DIR=/path/to/playlists
export HOST_TO_NAVIDROME_ROOT=/path/to/library:/music
python app.py   # http://localhost:8080
```

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
| `DOWNLOAD_WORKERS` | `4` | Downloads running at the same time |
| `DEEZER_ARL` | — | `arl` cookie of the Deezer account (mixes, release feed, downloads) |
| `DEEZER_ARL_PREMIUM` | — | `arl` of a premium account, used only for downloads |
| `SECRET_KEY` | random, kept in `secrets.json` | Session signing key |
| `APP_USERNAME` / `APP_PASSWORD` | — | The sign-in account; else the first visit asks you to create it |
| `API_TOKEN` | — | Token for other apps; else create one in Settings |
| `DISABLE_AUTH` | `false` | `true` turns sign-in off (a reverse proxy already asks for a login) |
| `COOKIE_SECURE` | `false` | `true` makes the session cookie HTTPS-only |

#### Folders

**Supported audio formats:** `.mp3`, `.flac`, `.m4a`, `.aac`, `.ogg`, `.opus`, `.wav`, `.wv`, `.mp4`

Each playlist gets its own folder under `PLAYLISTS_BASE_DIR`:
```
/music/playlists/
└── My Playlist/
    ├── My Playlist.m3u8
    ├── report.json
    └── missing.txt
```

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

#### Sign-in

The web interface asks for a sign-in. On the first visit, the app asks you to create the account (password of 8 characters or more, stored hashed in `data/secrets.json`), unless `APP_USERNAME` and `APP_PASSWORD` are set.

- After 5 failed sign-ins in 15 minutes, the username and the address wait 30 s, then twice as long after each new failure (up to 15 min). Behind a reverse proxy every request has the proxy's address, so a burst of failures briefly blocks everyone.
- Changing the password (**Settings → Sign-in and other apps**) signs out your other browsers.
- The API token is sent as `Authorization: Bearer <token>` and only opens `GET /api/releases`, `POST /search/library-check` and `GET /api/version`.

Generate a `SECRET_KEY` or a token with:
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

- **Music folders**, **Navidrome paths** (mappings), **Downloads** folder (with the folder actually used and a warning if it is missing)
- **Performance**: scan, download and matching threads
- **Release feed**: refresh interval (6 h to weekly, or manual only)
- **Data files**: where the app keeps its state
- **Deezer account**: the ARL, its badge, and the premium ARL for downloads
- **Sign-in and other apps**: password, API token, CatBoard webhook
- **Library index**: refresh or rebuild
- **Reset data**: clear the index, match results, playlists, duplicate report or decisions (two clicks each)

Changes are saved to `config.json` and apply at once.

---
<a id ="usage"></a>
## 📖 Usage

### Typical Workflow

#### 1. Configure

Open **Settings**, check the music folders and the Navidrome paths, make sure the downloads line under **Downloads** is green, and connect your Deezer account.

#### 2. Build the library index

**Settings → Library index → Rebuild from scratch** the first time (progress in Activity). Afterwards, **Refresh library** (Dashboard or Settings) only reads new and changed files.

#### 3. Add playlists

On the Dashboard, paste a Deezer playlist URL or ID in **Playlists**. With a connected account, **Mixes → Choose mixes** lets you follow your Flow and "made for you" mixes.

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

All routes need a signed-in session, except `/health` and the three routes the API token opens.

#### Playlists

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Dashboard |
| `/releases` | GET | Releases view |
| `/playlist/add` | POST | Add a Deezer playlist |
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
| `/api/deezer/account` | GET/POST/DELETE | Account status, connect, disconnect |
| `/api/deezer/premium-account` | POST/DELETE | Set or remove the premium ARL for downloads |
| `/api/deezer/mixes`, `/api/deezer/mixes/follow` | GET/POST | List and follow mixes |
| `/api/releases` | GET | Release feed (API token accepted) |
| `/api/releases/refresh`, `/api/releases/mute` | POST | Refresh the feed, mute an artist |

#### System

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/config` | GET/POST | Settings |
| `/admin/clear/<what>` | POST | `library-cache`, `preview-state`, `playlists`, `dedup-report`, `dedup-choices`, `all` |
| `/tasks/<id>/stream` | GET | Task progress (Server-Sent Events) |
| `/api/tasks` | GET | Running and recent tasks |
| `/health` | GET | Health check |
| `/api/version`, `/api/latest-version` | GET | Current and latest version |
| `/login`, `/logout`, `/setup` | GET/POST | Sign-in |
| `/api/auth/password`, `/api/auth/token` | POST | Change the password, create the API token |
| `/api/webhook`, `/api/webhook/test` | PUT/DELETE/POST | CatBoard webhook |

---
<a id ="troubleshooting"></a>
## 🛠️ Troubleshooting

### Downloads fail

**Check, in this order:**
1. **Settings → Deezer account** shows a badge (`Premium`, `Free` or `Free · downloads in Premium`). Without an account, nothing can be downloaded.
2. **Settings → Downloads** shows a green line. A red one means the folder does not exist or cannot be written to: mount it as a writable volume.
3. The reason of each failure is shown in **Activity** and in the tooltip of the **Retry** button. "Deezer returned no download link for this track" usually means the track is not available for your account or your country.

**Only MP3 128 kbps?** The account is free. Add the ARL of a premium account in the same panel to get FLAC.

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

### Code Structure

```
app.py                  # Flask init, blueprints, sign-in check

core/
├── config.py           # Paths, config and secrets, background tasks
├── auth.py             # Sign-in, password, API token
├── library.py          # Library scanning and index (threaded, per folder)
├── matching.py         # Matching a Deezer track against the library
├── normalization.py    # Text normalization, version flags, quality score
├── deezer.py           # Deezer public API, playlists, M3U8 generation
├── deezer_account.py   # Deezer session (ARL): mixes, favorites, account status
├── deezer_dl.py        # Downloading: links, decryption, tags, file layout
├── download_queue.py   # Download queue and its worker threads
├── releases.py         # Release feed
├── scheduler.py        # Automatic playlist scans and release refreshes
├── dedup.py            # Duplicate analysis and apply
├── webhook.py          # CatBoard webhook
├── utils.py            # Audio extensions, tag reading
└── version.py          # Current and latest version

routes/
├── playlists.py        # Views, /playlist/*
├── search.py           # /search/*, previews
├── account.py          # /api/deezer/*, /api/releases*
├── cache.py            # /cache/*, /api/library/*
├── dedup.py            # /dedup/*
├── auth.py             # /login, /setup, /api/auth/*, /api/webhook
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
- **Keep `/data` private** - `secrets.json` holds your Deezer cookies
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
