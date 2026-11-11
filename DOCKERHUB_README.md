# Deezer to Navidrome

**Turn your Deezer playlists into Navidrome `.m3u8` playlists, match them against your local library, and download what is missing straight from Deezer.**

[![Version](https://img.shields.io/badge/version-1.18.2-blue)](https://hub.docker.com/r/catchow/deezer-to-navidrome)
[![Python 3](https://img.shields.io/badge/python-3-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-web%20app-brightgreen)](https://flask.palletsprojects.com/)
[![GitHub](https://img.shields.io/badge/GitHub-source%20%26%20full%20docs-black)](https://github.com/CatChow0/deezer-to-navidrome)

> 📖 **Full documentation:** [github.com/CatChow0/deezer-to-navidrome](https://github.com/CatChow0/deezer-to-navidrome)

---

**Made for you** builds Daily Mix or Daily Mix+, and Discover, from what you listen to, with tempo and genre filled in by **Fix missing metadata**, your own limits, and a quarantine with your own rules for what they download.

The **New** button keeps the notes of each version, and **Help** is a full guide with a search.

## What it does

- Matches each track of your Deezer playlists and mixes (Flow, "made for you") against your local files
- **Imports Spotify playlists** (public link, or a CSV export from Exportify) and matches each track to Deezer, with **Find on Deezer** to pick one by hand
- Generates `.m3u8` playlists that Navidrome imports
- **Downloads missing tracks directly from Deezer** — tracks, albums or whole discographies, decrypted and tagged by the app itself
- **Automation** — scan playlists on a schedule and download what is missing
- **Listening stats** — story recaps, top lists, genres and habits, from your own play history; replaces Maloja and lb-enricher
- **Release feed** — new albums, EPs and singles of your favorite Deezer artists, with what you already own
- **Library check** — see which tracks, albums and artists you own while browsing Deezer
- **Manual matching** — fix a wrong match by picking the file yourself
- Finds library duplicates (remix, live, remaster…) and quarantines or deletes them
- Sign-in, API token, and a webhook for [CatBoard](https://github.com/CatChow0/catboard)

---

## Quick Start

```yaml
services:
  deezer-to-navidrome:
    image: catchow/deezer-to-navidrome:latest
    container_name: deezer-to-navidrome
    restart: unless-stopped
    cpus: "4.0"       # set to your actual core count
    cpu_shares: 1024
    ports:
      - "8080:8080"
    environment:
      DATA_DIR: "/data"
      SCAN_DIRS: "/music/deezer-dl,/music/library"
      PLAYLISTS_BASE_DIR: "/music/playlists"
      HOST_TO_NAVIDROME_ROOT: "/music/deezer-dl:/deezer-dl,/music/library:/music"
      LIBRARY_WORKERS_PER_DIR: "2"   # 2=HDD  4=RAID  8=SSD
      MATCH_WORKERS: "4"             # set to your Docker CPU count
      # DEEZER_ARL: ""               # or add it in Settings
    volumes:
      - ./data:/data
      - /path/on/host/deezer-dl:/music/deezer-dl   # downloads land here (writable)
      - /path/on/host/library:/music/library
      - /path/on/host/playlists:/music/playlists
```

```bash
docker compose up -d
# Open http://localhost:8080, create your account, then connect Deezer in Settings
```

---

## Downloads

Downloads use the `arl` cookie of a Deezer account (**Settings → Deezer accounts**, or `DEEZER_ARL`). Several accounts can be added: the one marked **Use for download** fetches the files for everyone, and each Navidrome profile follows the releases and mixes of its own Deezer account, the default one otherwise.

| Account used for downloads | Badge | Format |
|---|---|---|
| Premium (HiFi) | `Premium` | FLAC |
| Premium, high quality only | `Premium` | MP3 320 kbps |
| Free | `Free` | MP3 128 kbps |

Files go to the downloads folder: the music folder named `deezer-dl` by default, or `DEEZER_DL_DIR`. Albums go in `albums/Artist - Album/`, single tracks in `songs/`. **Settings → Downloads** shows the folder actually used and warns if it is missing or read-only.

Deezer serves the catalogue of the account's country (shown in Settings). The version downloaded is exactly the one you clicked: explicit tracks and albums are marked **E**, and the app never replaces an explicit track with its censored version.

Each download shows its progress on its button (*Queued* → `42%` or `3/14` → *Downloaded*) and in the **Activity** cell. A partly failed album can be retried; files already saved are kept.

**Downloaded with 1.10.0 to 1.11.0?** Those versions saved damaged files (noise, skips, refused by Navidrome's web player). Run **Settings → Library index → Repair downloads**: it replaces only the damaged files, keeping their tags.

**Upgrading from a version before 1.10?** The separate `kmille2/deezer-downloader` container is no longer needed: remove it and `DEEZER_DL_BASE_URL`, and mount the `deezer-dl` folder (writable) in this container. The app opens a *What's new* window on the first visit that checks this for you; the **Help** button reopens it.

> The decryption and tagging code is adapted from [deezer-downloader](https://github.com/kmille/deezer-downloader) by kmille, under the MIT licence (see LICENSE in the source repository).

---

## Playlists from other platforms

- **Spotify link**: paste it in **Playlists → Add**. Read from Spotify's public embed page: public playlists, first 100 tracks.
- **CSV**: **Playlists → Import CSV** with an Exportify, TuneMyMusic or Soundiiz export: any size, private playlists too, and the ISRC gives exact matches.
- Tracks are matched by ISRC, else by search (artist, title, duration, version, explicit flag). Unsure ones are flagged **Review**; **Find on Deezer** picks the right one by hand.
- Then it is a playlist like the others: previews, **Download missing**, scans, `.m3u8`, and automation (a Spotify playlist is synced again at each scan).

---

## Listening stats

The **Stats** tab keeps its own play history in `stats.db`, one per Navidrome account (`stats/nd2.db`… for the others). No Maloja, lb-enricher or Navidrome password needed. Recaps are stories built from what stood out in each period, playing your own files, with covers taken from your files and Deezer and cached locally.

- **New plays:** create a token in Settings → Listening stats, set `ND_LISTENBRAINZ_BASEURL=http://deezer-to-navidrome:8080/apis/listenbrainz/1/` in Navidrome, restart it, and link ListenBrainz in its personal settings with that token. Each Navidrome user has their own token: the token says whose play it is.
- **Past plays:** mount Navidrome's and Maloja's data folders read-only at `/import/navidrome` and `/import/maloja`, then choose **Rebuild (merge)** under Stats → Your history. Merge never removes a play and can be run again at any time. **Start clean** wipes and rebuilds from the sources, and needs Navidrome's database.

---

## Environment Variables

> Folder and performance variables are read **on first start** to create `config.json`; then use **Settings** (no restart needed). Credentials are read on every start.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data` | Config, index, secrets. **Must be a volume.** |
| `SCAN_DIRS` | `/music/deezer-dl,/music/library` | Music folders to index, comma-separated |
| `PLAYLISTS_BASE_DIR` | `/music/playlists` | Where `.m3u8` files are written |
| `HOST_TO_NAVIDROME_ROOT` | `/music/deezer-dl:/deezer-dl,/music/library:/music` | Path mappings `app_path:navidrome_path` |
| `DEEZER_DL_DIR` | empty | Downloads folder; empty = the `deezer-dl` music folder |
| `LIBRARY_WORKERS_PER_DIR` | `2` | Scan threads per folder. `2`=HDD · `4`=RAID · `8`=SSD/NVMe |
| `MATCH_WORKERS` | `4` | Matching threads. Set to your CPU count |
| `METADATA_WORKERS` | `4` | Files Fix missing metadata handles at once. Up to your CPU count, 2 on a spinning disk |
| `DOWNLOAD_WORKERS` | `4` | Downloads at the same time |
| `DEEZER_ARL` | — | Cookie of a Deezer account, the default one (downloads, mixes, release feed) |
| `DEEZER_ARL_PREMIUM` | — | Cookie of a Deezer account marked for the downloads |
| `SECRET_KEY` | random, kept in `secrets.json` | Session key |
| `D2N_ENCRYPTION_KEY` | random, kept in `encryption.key` | Key the saved credentials are encrypted with |
| `APP_USERNAME` / `APP_PASSWORD` | — | The sign-in account; else the first visit asks you to create it |
| `API_TOKEN` | — | Token for other apps (CatBoard); else create one in Settings |
| `SCROBBLE_TOKEN` | — | Token Navidrome sends the first account's plays with; else create one in Settings |
| `SCROBBLE_TOKEN_ND2`… | — | Token of the other Navidrome accounts |
| `STATS_NAVIDROME_DB` | `/import/navidrome/navidrome.db` | Navidrome's database, for importing your history |
| `STATS_MALOJA_DB` | `/import/maloja/malojadb.sqlite` | Maloja's database, for importing your history |
| `DISABLE_AUTH` | `false` | `true` turns sign-in off (a reverse proxy already asks for a login) |
| `COOKIE_SECURE` | `false` | `true` makes the session cookie HTTPS-only |

### Path Mapping (`HOST_TO_NAVIDROME_ROOT`)

The app and Navidrome see the same files under different paths. Map them so generated M3U8s use paths Navidrome understands — including the downloads folder.

```
HOST_TO_NAVIDROME_ROOT=/music/deezer-dl:/deezer-dl,/music/library:/music

App sees:       /music/deezer-dl/songs/Artist - Song.mp3
M3U8 contains:  /deezer-dl/songs/Artist - Song.mp3   ← what Navidrome sees
```

---

## Volumes

| Container path | Purpose | Notes |
|----------------|---------|-------|
| `/data` | Config, index, secrets, dedup choices | ✅ Persistent and private (holds your Deezer cookies) |
| `/music/deezer-dl` | Downloads | ✅ Writable, shared with Navidrome |
| `/music/*` | Your music library | Read-only is fine unless you delete duplicates |
| `/music/playlists` | Generated M3U8 output | ✅ Writable, shared with Navidrome |
| `/import/navidrome`, `/import/maloja` | Optional: history to import into Stats | Read-only is enough |

---

## Typical Workflow

1. **Settings** → check music folders, Navidrome paths and the downloads folder; add your Deezer account
2. **Rebuild from scratch** → build the library index
3. **Add a playlist** (URL or ID) or **Choose mixes**
4. **Full scan** → match tracks; writes `.m3u8` + `report.json` + `missing.txt`
5. **Download missing** → then **Refresh library** and **Quick scan**
6. *(Optional)* **Automation** → scan on a schedule and download what is missing
7. Navidrome imports the `.m3u8` file

### Scan modes

| Button | Behaviour |
|--------|-----------|
| **Quick scan** | Keeps tracks already in your library; only re-checks missing and unchecked ones |
| **Full scan** | Matches every track again. Use after reorganizing your library |

---

## Matching Engine

1. **Artist first** — the Deezer main artist must match one of the file's artists (≥ 0.85; collaborations split, leading "The" ignored)
2. **Title** — similarity ≥ 0.90, or ≥ 0.80 when durations are within 3 s
3. **Ranking** — title 60 %, artist 25 %, album 5 %, plus duration (up to +0.10) and version flags (+0.05 same, −0.15 conflict such as live vs studio; remaster-only differences ignored)

Similarities use `rapidfuzz` (C++, GIL-releasing), so matching threads run in parallel. A match fixed by hand is kept by later scans.

---

## Deduplication

- Groups files by artist + album + title + version flags
- Ranks each group by quality (codec > file size > tag completeness)
- You check the files to **keep**, then quarantine or delete the rest
- Decisions are **persistent** in `dedup_choices.json`

---

## Data Files (in `DATA_DIR`)

| File | Purpose |
|------|---------|
| `config.json` | App configuration |
| `secrets.json` | Password hash, API token, Deezer cookies, webhook URL |
| `music_library_cache.json` | Library index |
| `deezer_playlist_ids.json` | Playlists, mixes and their automation settings |
| `playlist_preview_state.json` | Per-playlist match results (enables Quick scan) |
| `releases.json` / `release_prefs.json` | Release feed / muted artists |
| `dedup_report.json` / `dedup_choices.json` | Latest duplicate analysis / persistent decisions |
| `stats.db`, `stats/*.db`, their `.bak-*` | Listening history of each Navidrome account and the last 3 backups |
| `stats_sources/` | Saved copy of Maloja's database |
| `stats_covers/` | Cached artist, album and track covers |
| `covers/` | Playlist artwork |
| `dedup_quarantine/` | Quarantined duplicate files |

## Key API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /deezer-dl/download/start` | Queue a track, album or discography download |
| `GET /deezer-dl/queue` | Download queue state |
| `POST /playlist/<id>/automation` | Save a playlist's automation settings |
| `GET /api/scheduler/status` | Next automatic scan of each playlist |
| `POST /search/library-check` | Which items exist in the local library (API token accepted) |
| `GET /api/releases` | Release feed of the favorite Deezer artists (API token accepted) |

## CatBoard

Create an API token in **Settings → Sign-in and other apps**, add the app in CatBoard (**Settings → Integrations → Deezer to Navidrome**) with that token, then paste the webhook URL CatBoard shows under **CatBoard webhook**. The app calls it when the release feed or the library index is refreshed, so CatBoard updates at once.

---

## Supported Audio Formats

`.mp3` · `.flac` · `.m4a` · `.aac` · `.ogg` · `.opus` · `.wav` · `.wv` · `.mp4`

---

## Links

- 📖 [Full documentation & source code](https://github.com/CatChow0/deezer-to-navidrome)
- 🐛 [Report issues](https://github.com/CatChow0/deezer-to-navidrome/issues)
- 🐳 [Docker Hub](https://hub.docker.com/r/catchow/deezer-to-navidrome)
