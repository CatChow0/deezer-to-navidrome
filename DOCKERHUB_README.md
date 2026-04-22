# Deezer to Navidrome

**Convert Deezer playlists to Navidrome-compatible `.m3u8` playlists by matching them against your local music library.**

[![Version](https://img.shields.io/badge/version-1.4.0-blue)](https://hub.docker.com/r/catchow/deezer-to-navidrome)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-web%20app-brightgreen)](https://flask.palletsprojects.com/)
[![GitHub](https://img.shields.io/badge/GitHub-source%20%26%20full%20docs-black)](https://github.com/CatChow0/deezer-to-navidrome)

> 📖 **Full documentation:** [github.com/CatChow0/deezer-to-navidrome](https://github.com/CatChow0/deezer-to-navidrome)

---

## What it does

- Fetches your Deezer playlists and matches each track against your local music files
- Generates `.m3u8` playlists that Navidrome auto-imports
- Downloads missing tracks via an optional [Deezer Downloader](https://github.com/maxim8898/deezerdownloader) integration
- **Auto-scan playlists** on configurable intervals with optional auto-download
- **Library Check** — see which tracks/albums/artists you already own while browsing Deezer
- Detects and manages library duplicates (remix, live, remaster, etc.)
- Fast matching engine: inverted title index + `rapidfuzz` (C++ GIL-releasing) + multi-threaded

---

## Quick Start

```yaml
version: "3.8"

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
      SECRET_KEY: "change-this-to-a-random-string"
      DATA_DIR: "/data"
      SCAN_DIRS: "/music/deezer-dl,/music/library"
      PLAYLISTS_BASE_DIR: "/music/playlists"
      HOST_TO_NAVIDROME_ROOT: "/music/deezer-dl:/deezer-dl,/music/library:/music"
      DEEZER_DL_BASE_URL: "https://deezer-downloader.example.com"   # optional
      LIBRARY_WORKERS_PER_DIR: "2"   # 2=HDD  4=RAID  8=SSD
      MATCH_WORKERS: "4"             # set to your Docker CPU count
    volumes:
      - ./data:/data
      - /path/on/host/deezer-dl:/music/deezer-dl
      - /path/on/host/library:/music/library
      - /path/on/host/playlists:/music/playlists
```

```bash
docker compose up -d
# Open http://localhost:8080
```

---

## Environment Variables

> These are read **once on first start** to generate `config.json`. After that, use the **Config** page in the UI — no container restart needed.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | Flask session key. Change to a random string. |
| `DATA_DIR` | `/data` | Persistent directory for config, cache, covers. **Must be a volume.** |
| `SCAN_DIRS` | — | Comma-separated music directories to scan. |
| `PLAYLISTS_BASE_DIR` | — | Where `.m3u8` files are written. |
| `HOST_TO_NAVIDROME_ROOT` | — | Path mappings `container_path:navidrome_path` (comma-separated). |
| `DEEZER_DL_BASE_URL` | — | Optional: base URL of Deezer Downloader service. |
| `LIBRARY_WORKERS_PER_DIR` | `2` | Threads per scan directory. `2`=HDD · `4`=RAID · `8`=SSD/NVMe |
| `MATCH_WORKERS` | `4` | Parallel matching threads. Set to your CPU count. |

### Path Mapping (`HOST_TO_NAVIDROME_ROOT`)

The app and Navidrome see the same files under different paths. Map them so generated M3U8s use paths Navidrome understands.

```
HOST_TO_NAVIDROME_ROOT=/music/deezer-dl:/deezer-dl,/music/library:/music

App sees:       /music/deezer-dl/Artist/Song.mp3
M3U8 contains:  /deezer-dl/Artist/Song.mp3   ← what Navidrome sees
```

---

## Volumes

| Container path | Purpose | Must be persistent? |
|----------------|---------|---------------------|
| `/data` | Config, cache, covers, dedup choices | ✅ Yes |
| `/music/*` | Your music library (read-only is fine) | — |
| `/music/playlists` | Generated M3U8 output | ✅ Yes (shared with Navidrome) |

---

## Typical Workflow

1. **Config** → verify scan dirs and path mappings
2. **Full rebuild** → scan library and build cache (~seconds to minutes depending on size)
3. **Add playlist** → paste Deezer URL or playlist ID
4. **Full Scan** → match tracks; generates `.m3u8` + `report.json` + `missing.txt`
5. *(Optional)* **Enable Automation** → auto-scan and auto-download on a schedule per playlist
6. *(Optional)* Download missing tracks, run **Incremental cache refresh**, then **Quick Scan**
7. Navidrome auto-imports the `.m3u8` file

### Automation

Each playlist can be configured to auto-scan and optionally auto-download:
- Set interval in minutes/hours/days
- Visual badges on playlist cards ("Auto Scan", "Auto DL")
- Next scan countdown displayed

### Scan modes

| Button | Behaviour |
|--------|-----------|
| **Quick Scan** | Reuses cached matches; only re-matches unmatched/new tracks. Fast for mostly-matched playlists. |
| **Full Scan** | Re-matches every track from scratch. Use after library changes or for first-time conversion. |

### Library Check

When searching Deezer, ownership indicators show:
- **Tracks:** Green "Owned" badge if in library
- **Albums:** Yellow (partial) or green (complete) badge with `owned/total tracks`
- **Artists:** Yellow (partial) or green (complete) badge with `owned/total albums`

---

## Matching Engine

Each Deezer track is scored against library candidates using five factors:

| Factor | Weight / bonus |
|--------|---------------|
| Title similarity | 62% |
| Artist similarity | 25% |
| Album similarity | 8% |
| Duration proximity | up to +0.10 / -0.08 |
| Version flag match | +0.08 exact match / -0.18 conflict |

**Version flags** are detected from raw tag values including parenthetical content (e.g. `"Song (Live Version)"` → `live`, `"Track [Radio Edit]"` → `radio_edit`):

| Flag | Keywords |
|------|---------|
| `remix` | remix, rmx |
| `live` | live |
| `instrumental` | instrumental, instr |
| `remaster` | remaster, remastered |
| `radio_edit` | radio edit, radio mix, radio version |
| `extended` | extended, extended mix, extended version |
| `edit` | club edit, single edit, album edit, special edit |
| `session` | session, garage session, studio session |
| `original` | original, original version, original mix |
| `acapella` | acapella, a cappella |
| `demo` | demo |
| `alt` | alternate, alt version, alternative |
| `bonus` | bonus, bonus track |

> A version conflict (e.g. Deezer track is a remix but library file is the original) applies a **-0.18** score penalty, ensuring the correct variant wins when both are available.

---

## Deduplication

- Scans library cache and groups files by artist + album + title + version flags
- Ranks each group by quality score (codec > file size > tag completeness)
- Lets you mark which files to **keep**, then quarantine or permanently delete the rest
- Decisions are **persistent** — saved in `dedup_choices.json` and remembered across restarts

---

## Performance Tips

- Set `cpus` in `docker-compose.yml` to your actual core count — Docker may throttle to 1 core by default
- Set `MATCH_WORKERS` to your CPU count for parallel matching
- Set `LIBRARY_WORKERS_PER_DIR` based on storage type (`2` HDD · `8` SSD)
- Use **Quick Scan** for playlists that are already mostly matched
- Use **Incremental cache refresh** instead of full rebuild after adding new files

---

## Data Files (in `DATA_DIR`)

| File | Purpose |
|------|---------|
| `config.json` | App configuration including automation settings |
| `music_library_cache.json` | Indexed library metadata |
| `playlist_preview_state.json` | Per-playlist match cache (enables Quick Scan) |
| `dedup_report.json` | Latest dedup analysis |
| `dedup_choices.json` | **Persistent** user dedup decisions |
| `covers/` | Cached playlist artwork |
| `dedup_quarantine/` | Quarantined duplicate files |

## Key API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/playlist/<id>/automation` | Get/set automation settings for a playlist |
| `/automation/status` | Scheduler status for all playlists |
| `/search/library-check` | Check if items exist in local library |

---

## Supported Audio Formats

`.mp3` · `.flac` · `.m4a` · `.aac` · `.ogg` · `.opus` · `.wav` · `.wv` · `.mp4`

---

## Links

- 📖 [Full documentation & source code](https://github.com/CatChow0/deezer-to-navidrome)
- 🐛 [Report issues](https://github.com/CatChow0/deezer-to-navidrome/issues)
- 🐳 [Docker Hub](https://hub.docker.com/r/catchow/deezer-to-navidrome)
