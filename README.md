# Deezer to Navidrome

**A comprehensive web application that converts Deezer playlists to Navidrome-compatible `.m3u8` playlists by matching them against your local music library.**

[![Docker Image Version](https://img.shields.io/badge/version-1.1.0-blue)](https://hub.docker.com/r/catchow/deezer-to-navidrome)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-web%20app-brightgreen)](https://flask.palletsprojects.com/)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Advanced Features](#advanced-features)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

---

## 🎯 Overview

Deezer-To-Navidrome is a Flask web application that bridges the gap between Deezer's streaming service and self-hosted music servers like [Navidrome](https://www.navidrome.org/). It allows you to:

- **Import Deezer playlists** by ID or URL
- **Scan local music library** and build an intelligent cache
- **Match tracks** using sophisticated string matching and metadata analysis
- **Download missing tracks** via integration with external Deezer Downloader
- **Generate M3U8 playlists** compatible with Navidrome and other players
- **Manage duplicates** with intelligent grouping and deduplication tools
- **Preview matches** before conversion with detailed match statistics

### Why Deezer-To-Navidrome?

If you're self-hosting music with Navidrome but also subscribe to Deezer, you want your playlists to sync across both services. This app fills that gap by:

1. ✅ Keeping your playlists organized
2. ✅ Finding matching files in your library (even with metadata variations)
3. ✅ Downloading missing tracks (optional)
4. ✅ Creating Navidrome playlists that stay synchronized
5. ✅ Managing library duplicates intelligently

---

## ✨ Features

### Core Playlist Management
- **Deezer Playlist Import** - Add playlists by ID or URL
- **Playlist Preview** - See match status (✅ matched, ❌ missing, ⚪ unchecked) before converting
- **M3U8 Export** - Generate Navidrome-compatible playlists
- **Cover Caching** - Automatically download and cache playlist artwork
- **Match Reports** - Detailed JSON reports showing how each track was matched

### Library Management
- **Full Cache Rebuild** - Re-scan entire music library from scratch
- **Incremental Refresh** - Fast updates after adding new files
- **Library Search** - Search Deezer for tracks, albums, and artists directly
- **Multi-Source Support** - Scan multiple directories with custom path mappings

### Duplicate Management
- **Intelligent Deduplication** - Groups duplicates by artist, album, and track
- **Version Detection** - Recognizes remix, live, instrumental, remaster variants
- **Quality Scoring** - Ranks files by quality (codec, bitrate, metadata completeness)
- **Persistent Choices** - Remembers dedup decisions across scans
- **Flexible Actions** - Quarantine or permanently delete duplicates

### Integration & Downloads
- **Deezer Downloader Integration** - Download missing tracks
- **Navidrome Auto-Import** - M3U8 files can be automatically synced to Navidrome
- **Path Mapping** - Handle different path representations between services
- **Task Progress Streaming** - Real-time progress via Server-Sent Events

### Configuration & Maintenance
- **Web Configuration UI** - Edit settings via browser
- **Multi-Source Support** - Configure multiple music library locations
- **Cleanup Tools** - Safely delete cache, playlists, or covers
- **Health Checks** - Monitor app status and version

---

## 🏗️ Architecture

### System Overview

```
┌──────────────────┐
│   Deezer API     │
│  • Playlists     │
│  • Search        │
│  • Metadata      │
└────────┬─────────┘
         │
         ▼
    ┌─────────────────────────────────┐
    │  Deezer-To-Navidrome            │
    │  ┌─────────────────────────────┐│
    │  │  Flask Web Server (8080)    ││
    │  │  • Routing & UI templates   ││
    │  │  • Task management          ││
    │  │  • Configuration            ││
    │  └─────────────────────────────┘│
    │  ┌─────────────────────────────┐│
    │  │  Matching Engine             ││
    │  │  • Text normalization        ││
    │  │  • Similarity scoring        ││
    │  │  • Best match selection      ││
    │  └─────────────────────────────┘│
    │  ┌─────────────────────────────┐│
    │  │  Cache System                ││
    │  │  • Library index (JSON)      ││
    │  │  • Dedup reports             ││
    │  │  • Playlist previews         ││
    │  │  • Dedup decisions (persistent)│
    │  └─────────────────────────────┘│
    │  ┌─────────────────────────────┐│
    │  │  Dedup Engine                ││
    │  │  • Group by identity         ││
    │  │  • Quality ranking           ││
    │  │  • Version flag detection    ││
    │  └─────────────────────────────┘│
    └────┬──────────────┬──────────────┘
         │              │
         ▼              ▼
    ┌──────────┐  ┌─────────────────┐
    │  Local   │  │  M3U8 Playlists │
    │ Library  │  │ + JSON Reports  │
    │  (audio  │  │ + Navidrome     │
    │  files)  │  │   Auto-Import   │
    └──────────┘  └─────────────────┘
         │              │
         ▼              ▼
    ┌──────────────────────┐
    │  Navidrome           │
    │  (Music Server)      │
    └──────────────────────┘
```

### Data Flow

1. **Scan Phase**: App scans local music directories, reads tags, builds enriched library cache
2. **Fetch Phase**: When adding playlist, app fetches metadata from Deezer API
3. **Normalize Phase**: Both Deezer and local data are normalized (lowercase, no accents, etc.)
4. **Match Phase**: Each Deezer track is scored against local files using multi-factor similarity
5. **Preview Phase**: Matches cached in per-playlist state file
6. **Download Phase** (optional): Missing tracks downloaded via external service
7. **Generate Phase**: M3U8 playlist generated with proper path mappings
8. **Import Phase**: Navidrome auto-imports and indexes the M3U8 file

### Multi-Layer Matching

```
For each Deezer track:
├─ Title Matching (62% weight)
│  └─ Compare against: tag_title, parsed_title, filename stem
│
├─ Artist Matching (25% weight)
│  └─ Compare against: tag_artist, parsed_artist, directory structure
│
├─ Album Matching (8% weight)
│  └─ Compare against: tag_album, album directory name
│
└─ Duration Matching (5% weight)
   └─ Check: ±2 seconds tolerance (high score)
              ±5 seconds (medium score)
              ±10 seconds (low score)
              >20 seconds (reject candidate)
```

**Matching Algorithm:**
- Uses Python's `SequenceMatcher.ratio()` for string similarity (0.0 to 1.0)
- Thresholds: Title ≥ 0.72, Artist ≥ 0.45 (if known)
- Returns best candidate above thresholds
- Falls back to "missing" if no match found

---

## 📦 Cache System

### Cache Files Overview

| File | Purpose | Size | Lifetime |
|------|---------|------|----------|
| `music_library_cache.json` | Complete library index | Large (1-100MB+) | Until full rebuild |
| `deezer_playlist_ids.json` | Playlist metadata | Small (<1MB) | Until deleted |
| `playlist_preview_state.json` | Per-playlist match state | Medium (varies) | Until playlist deleted |
| `dedup_report.json` | Latest dedup analysis | Medium (varies) | Until new scan |
| `dedup_choices.json` | **Persistent** user decisions | Small (<1MB) | Survives app restart |
| `covers/` | Playlist artwork | Medium (varies) | Until cleaned up |

### Library Cache Structure

Each entry in the cache contains:

```json
{
  "path": "/music/library/Artist/Album/01 - Track.mp3",
  "path_str": "/music/library/Artist/Album/01 - Track.mp3",
  "mtime_ns": 1234567890123456,
  "size": 5242880,
  
  "tag_artist": "Artist Name",
  "tag_title": "Track Title",
  "tag_album": "Album Name",
  "tag_track_number": 1,
  
  "parsed_artist": "Artist Name",
  "parsed_title": "Track Title",
  "parsed_track_title": "Track Title",
  
  "stem_norm": "01 track",
  "artist_dir_norm": "artist name",
  "album_dir_norm": "album name",
  "base_title": "track title",
  
  "duration": 180.5,
  "quality_score": 85.5,
  "version_flags": ["remaster", "live"]
}
```

### Incremental Cache Refresh

The app uses file timestamps and sizes to detect changes:

```python
# Efficient detection: O(1) per unchanged file
If file.mtime_ns == cached.mtime_ns AND file.size == cached.size:
  ✓ Keep cached entry (unchanged)
Else:
  ✗ Re-scan and re-extract metadata (changed or new)
```

**Performance:** Full rebuild on 10,000 files: a few minutes. Incremental: ~1-5s (depends on changed files).

### Cache Precomputation

During cache build, the app pre-computes:
- Normalized text fields (lowercase, accents removed, special chars cleaned)
- Version flags (remix, live, remaster, instrumental, etc.)
- Quality scores (file format + size + metadata completeness)
- Track numbers (extracted from filename or tags)

This makes matching and dedup analysis much faster.

---

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

The app recognizes these variants:

| Type | Keywords |
|------|----------|
| Remix | remix, rmx, mix |
| Live | live |
| Instrumental | instrumental, instr |
| Remaster | remaster, remastered |
| Acoustic | acoustic |
| Unplugged | unplugged |
| Radio Edit | radio edit |
| Extended | extended, extended mix |
| Demo | demo |
| Bonus | bonus, bonus track |
| Alternate | alternate, alt version, alternative |
| A Cappella | acapella, a cappella |
| Session | session, garage session, studio session |
| Original | original, original version, original mix |

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

## 🚀 Installation

### Prerequisites

- Docker & Docker Compose
- At least one music directory mounted in the container
- (Optional) Deezer Downloader service for downloading missing tracks
- (Optional) Navidrome server configured to auto-import M3U8 playlists

### Quick Start with Docker Compose

1. **Create `docker-compose.yml`:**

```yaml
version: "3.8"

services:
  deezer-to-navidrome:
    image: catchow/deezer-to-navidrome:1.0.43
    container_name: deezer-to-navidrome
    restart: unless-stopped

    ports:
      - "8080:8080"

    environment:
      SECRET_KEY: "change-this-to-a-random-string"
      DATA_DIR: "/data"

      # Music library paths (comma-separated)
      SCAN_DIRS: "/music/deezer-dl,/music/library"

      # Where to write M3U8 playlists
      PLAYLISTS_BASE_DIR: "/music/playlists"

      # Map container paths to Navidrome paths
      # Format: /container/path:/navidrome/path
      HOST_TO_NAVIDROME_ROOT: "/music/deezer-dl:/deezer-dl,/music/library:/music"

      # Optional: Deezer Downloader service URL
      DEEZER_DL_BASE_URL: "https://deezer-downloader.example.com"

    volumes:
      # Persistent data (config, cache, covers)
      - ./data:/data

      # Music library directories
      - /path/on/host/deezer-dl:/music/deezer-dl
      - /path/on/host/library:/music/library

      # Playlist output directory
      - /path/on/host/playlists:/music/playlists
```

2. **Start the app:**

```bash
docker compose up -d
```

3. **Access the web UI:**

```
http://localhost:8080
```

### Without Docker

If running locally (development):

```bash
pip install -r requirements.txt
export DATA_DIR=./data
export SCAN_DIRS=/path/to/library
export PLAYLISTS_BASE_DIR=/path/to/playlists
export HOST_TO_NAVIDROME_ROOT=/path/to/library:/music
flask run
```

---

## ⚙️ Configuration

### Environment Variables (Bootstrap Only)

These variables are used **only on first startup** to generate `config.json`. If `config.json` exists, these are ignored.

#### `SCAN_DIRS`

Comma-separated list of directories containing your music files.

```env
SCAN_DIRS=/music/deezer-dl,/music/library,/mnt/nas/music
```

**Supported Audio Formats:**
`.mp3`, `.flac`, `.m4a`, `.aac`, `.ogg`, `.opus`, `.wav`, `.wv`, `.mp4`

#### `PLAYLISTS_BASE_DIR`

Directory where M3U8 playlists will be generated.

```env
PLAYLISTS_BASE_DIR=/music/playlists
```

Each playlist gets its own subdirectory:
```
/music/playlists/
├── My Playlist/
│   ├── My Playlist.m3u8
│   ├── report.json
│   └── missing.txt
└── Another Playlist/
    ├── Another Playlist.m3u8
    ├── report.json
    └── missing.txt
```

#### `HOST_TO_NAVIDROME_ROOT`

Maps paths visible to this app to paths Navidrome can see.

**Format:** `host_path:navidrome_path` (comma-separated)

```env
HOST_TO_NAVIDROME_ROOT=/music/deezer-dl:/deezer-dl,/music/library:/music
```

**Example Mapping:**
- App sees file at: `/music/deezer-dl/Artist/Song.mp3`
- Navidrome sees it at: `/deezer-dl/Artist/Song.mp3`
- M3U8 contains: `/deezer-dl/Artist/Song.mp3`

**Important:** Both the app and Navidrome must see the same music files under their respective mapped paths.

#### `DEEZER_DL_BASE_URL`

Base URL of the Deezer Downloader service (optional).

```env
DEEZER_DL_BASE_URL=https://deezer-downloader.example.com
```

If not configured, download buttons are hidden.

#### `DATA_DIR`

Persistent directory for app data.

```env
DATA_DIR=/data
```

**Contents:**
- `config.json` - App configuration
- `music_library_cache.json` - Library index (~large)
- `deezer_playlist_ids.json` - Saved playlists
- `playlist_preview_state.json` - Match status cache
- `dedup_report.json` - Latest dedup analysis
- `dedup_choices.json` - User dedup decisions
- `covers/` - Cached playlist artwork
- `dedup_quarantine/` - Quarantined duplicate files

**Must be persistent volume** to preserve settings and choices across container restarts.

#### `SECRET_KEY`

Flask secret key for session signing.

```env
SECRET_KEY=your-random-secret-key-here
```

Generate one with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Web Configuration UI

After starting, open **Config** page to:
- Edit scan directories
- Modify playlist output directory
- Add/remove path mappings
- Change Deezer Downloader URL
- Clean up cache, playlists, or covers

Changes are saved to `config.json` and take effect immediately.

---

## 📖 Usage

### Typical Workflow

#### Step 1: Configure

1. Open **Config** page
2. Verify scan directories
3. Confirm path mappings for Navidrome
4. Set Deezer Downloader URL (optional)
5. Save if needed

#### Step 2: Build Library Cache

1. Click **Full rebuild** (first time)
2. Wait for completion (shows progress in real-time)
3. Check status: Shows "X files indexed"

**Or** use **Incremental refresh** after adding new files.

#### Step 3: Add Deezer Playlists

1. On home page, paste Deezer URL or playlist ID
2. Click **Add playlist**
3. App fetches metadata and caches cover
4. Playlist appears with thumbnail

#### Step 4: Preview Matches

1. Click playlist cover to open preview
2. See match status for each track:
   - ✅ **Matched** - Found locally
   - ❌ **Missing** - Not in library
   - ⚪ **Unchecked** - Not yet analyzed
3. View match statistics

#### Step 5: Download Missing (Optional)

1. In preview, click **Download missing**
2. App sends request to Deezer Downloader
3. Progress bar shows download status
4. Once done, rows update to ✅

#### Step 6: Refresh Cache (After Downloads)

1. Go to home, click **Refresh cache incremental**
2. Wait for completion
3. Re-open playlist preview
4. Click **Convert** to re-analyze with new files

#### Step 7: Convert to M3U8

1. In playlist preview, click **Convert**
2. App generates M3U8 file
3. Creates `report.json` with statistics
4. Creates `missing.txt` if applicable
5. Status updates in preview
6. Navidrome auto-imports M3U8

### Advanced Usage

#### Search & Download

1. Click **Search** (home page)
2. Search for a track, album, or artist on Deezer
3. View results with artwork
4. Click **Download** to fetch from Deezer Downloader

#### Manage Duplicates

1. Click **Scan dedup** (home page)
2. Wait for analysis to complete
3. View duplicates grouped by album
4. For each group:
   - See quality metrics (codec, size, metadata)
   - View file paths and folder locations
   - Pre-selected: Previous keeper choices
5. Check boxes for files to **keep**
6. Choose action:
   - **Quarantine** - Move to `dedup_quarantine/`
   - **Delete** - Permanently remove
7. Decisions saved (survive restarts)

#### Clear Cache

1. Go to **Config**
2. Scroll to **Danger Zone**
3. Choose:
   - Clear library cache
   - Clear playlist previews
   - Clear all playlists
   - Clear everything

---

## 🔌 API Reference

### REST Endpoints

#### Playlists

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Homepage |
| `/playlist/add` | POST | Add Deezer playlist |
| `/playlist/<id>/delete` | POST | Remove playlist |
| `/playlist/<id>/preview` | GET | Get match state |
| `/playlist/<id>/convert` | POST | Convert to M3U8 |
| `/playlist/<id>/convert/start` | POST | Async convert |
| `/playlist/<id>/download-missing/start` | POST | Download missing |

#### Cache

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/cache/rebuild` | POST | Full rebuild (blocking) |
| `/cache/full/start` | POST | Full rebuild (async) |
| `/cache/refresh` | POST | Incremental (blocking) |
| `/cache/incremental/start` | POST | Incremental (async) |

#### Dedup

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/dedup/start` | POST | Start dedup analysis |
| `/dedup/report` | GET | Get results |
| `/dedup/apply` | POST | Apply decisions |

#### Search

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search` | GET | Search Deezer |
| `/search/album/<id>` | GET | Album details |
| `/search/artist/<id>` | GET | Artist details |

#### Admin

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/config` | GET/POST | View/edit config |
| `/admin/clear/*` | POST | Delete caches |
| `/health` | GET | Health check |
| `/api/version` | GET | Get app version |
| `/tasks/<id>/stream` | GET | SSE progress |

---

## 🛠️ Troubleshooting

### "Unknown" displayed in version tag

**Issue:** Version appears as "v unknown" in header
**Cause:** `VERSION` file not found in container
**Fix:**
```bash
docker compose down
docker compose pull
docker compose up -d
```

### Playlists not converting

**Issue:** Convert button does nothing or shows error
**Possible Causes:**
1. **No matches found** - Check library cache status
2. **Path mapping wrong** - Verify `HOST_TO_NAVIDROME_ROOT`
3. **Permissions** - `PLAYLISTS_BASE_DIR` not writable
4. **Cache corrupted** - Clear and rebuild cache

**Debug:**
```bash
# Check container logs
docker logs deezer-to-navidrome

# Verify mounted paths
docker exec deezer-to-navidrome ls -la /music
```

### Downloads not working

**Issue:** Download buttons missing or downloads fail
**Causes:**
1. `DEEZER_DL_BASE_URL` not configured
2. Downloader service unreachable
3. Network connectivity issue

**Fix:**
```bash
# Test downloader service
curl https://deezer-downloader.example.com/health

# Update config if URL changed
# Go to /config and update DEEZER_DL_BASE_URL
```

### Library cache taking too long

**Issue:** Full rebuild takes >10 minutes for small library
**Causes:**
1. Very large library (100,000+ files)
2. Slow storage (network mount)
3. Many files without tags

**Solutions:**
- Use incremental refresh after initial build
- Add only frequently-changed directories
- Ensure good tag coverage (helps matching)

### No matches found

**Issue:** Playlists show ❌ for all tracks
**Likely Causes:**
1. **Tag quality** - Files lack artist/title metadata
2. **Path structure** - Unrecognized directory layout
3. **Text matching** - Unusual artist/title formatting
4. **Wrong directories** - SCAN_DIRS pointing to empty folders

**Debug:**
```bash
# Manually check a file
docker exec deezer-to-navidrome \
  python -c "
  from mutagen import File
  f = File('/music/path/to/file.mp3')
  print(f)
  "
```

### Duplicates keep reappearing

**Issue:** Dedup decisions not persisting
**Cause:** `DATA_DIR` not persistent (rebuilds on restart)
**Fix:** Ensure volume is properly mounted
```yaml
volumes:
  - ./data:/data  # ✓ Persistent
  # NOT: - /tmp/data:/data  (✗ ephemeral)
```

### Disk space growing rapidly

**Issue:** `dedup_quarantine/` or cache files consuming space
**Solutions:**
- Manually clean `dedup_quarantine/`:
  ```bash
  docker exec deezer-to-navidrome \
    rm -rf /data/dedup_quarantine/*
  ```
- Or use Config page: Danger Zone → Clear Everything

---

## 💻 Development

### Building Locally

```bash
git clone <repo>
cd Deezer-To-Navidrome

# Build image
docker build -t deezer-to-navidrome:dev .

# Run with local settings
docker run -p 8080:8080 \
  -e SCAN_DIRS=/music/lib \
  -e PLAYLISTS_BASE_DIR=/music/playlists \
  -v ./data:/data \
  -v /path/to/music:/music/lib \
  deezer-to-navidrome:dev
```

### Running Without Docker (Dev Mode)

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

pip install -r requirements.txt

export FLASK_ENV=development
export DATA_DIR=./data
export SCAN_DIRS=/path/to/music
export PLAYLISTS_BASE_DIR=/path/to/playlists
export HOST_TO_NAVIDROME_ROOT=/path/to/music:/music

flask run  # Runs on http://localhost:5000
```

### Code Structure

```
app.py (2650+ lines)
├── Initialization & Config
├── Library Scanning & Caching
├── Matching Engine
├── M3U8 Generation
├── Deduplication System
├── Task Management & SSE
├── Flask Routes
└── Helper Functions

templates/
├── base.html      # Layout & version tag
├── home.html      # Playlist list & search
└── config.html    # Settings & cleanup

static/
├── style.css      # Responsive styling
└── (JavaScript in templates)
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `scan_audio_files()` | Find all audio files recursively |
| `build_library_entry()` | Extract tags and metadata |
| `score_candidate()` | Calculate match score |
| `find_best_match()` | Find best matching file |
| `convert_playlist()` | Generate M3U8 |
| `build_dedup_groups()` | Identify duplicates |
| `apply_dedup_decisions()` | Quarantine/delete duplicates |

### Adding Features

1. **New route:** Add `@app.route()` in `app.py`
2. **New template:** Create `.html` in `templates/`
3. **New function:** Add to appropriate section in `app.py`
4. **Cache changes:** Update cache JSON structure + loader/saver
5. **UI changes:** Update `home.html` or `config.html`

### Testing

```bash
# Check library cache
python -c "
import json
from pathlib import Path
cache = json.loads(Path('./data/music_library_cache.json').read_text())
print(f\"Library: {cache['count']} files\")
"

# Check playlist state
python -c "
import json
from pathlib import Path
state = json.loads(Path('./data/playlist_preview_state.json').read_text())
for pid, rows in state.items():
    print(f\"Playlist {pid}: {len(rows)} tracks\")
"
```

---

## 📝 Notes

- **Matching quality depends on tag and filename quality** - Well-tagged files match much better
- **Environment variables are mainly for first startup** - Edit `/data/config.json` or use Web UI afterwards
- **Deezer Downloader is optional** - App works fine without it (just no download buttons)
- **Dedup decisions are persistent** - Stored in `dedup_choices.json` (survives restarts)
- **Path mappings are critical** - Must match exactly how Navidrome sees files
- **Large libraries benefit from incremental refresh** - Full rebuild on 50,000+ files can take time

---

## 📄 License

See LICENSE file for details.

## 🤝 Contributing

Contributions welcome! Please submit issues or pull requests.

## 🆘 Support

For bugs or questions:
1. Check this README
2. Check GitHub Issues
3. Review app logs: `docker logs deezer-to-navidrome`
4. Enable debug mode in Flask (development only)

---

**Last Updated:** 2025
**Version:** 1.0.45
