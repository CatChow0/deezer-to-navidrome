# Android app, phase 7: the main functions, Implementation Plan

> **For agentic workers:** resolve phase 6 issues first, then follow this plan task-by-task. Each task ends with tests and, on your approval, a commit point and a DEV build.

**Goal:** bring the web interface's main functions to the phone: Deezer search with covers/previews/downloads, the profile's playlists (link, CSV, scan, download, match, automation), and Made for you (swipe, lists, stats).

**Architecture:**
- **Navigation:** bottom bar keeps the approved set (Dashboard, Made for you, Stats, Releases, More). Deezer search and Playlists live under a Dashboard route set initially. Search is the entry to the profile's playlists; Made for you is reachable immediately.
- **API:** add typed endpoints for search, playlists and mixes to `D2nApi`, re-using the v1 contract (devices, profiles, ETags, task events) and `apiCall`.
- **UI:** Compose screens with `LazyColumn` goals, Coil for covers, Media3 for 30s previews.  Swipe gestures map to keep/remove tracks.
- **Tests:** JVM with MockWebServer for endpoint routing; emulator screenshots per screen; Docker unit tests in the PC build.

**Spec:** `docs/superpowers/specs/2026-11-09-android-app-design.md`

## Global constraints (unchanged from phase 6)
- Same stack, same minSdk 26,target 36, same theme. Any new library must be pinned and explained.
- New endpoints belong in `docs/api/openapi.yaml`, with parity/contract tests green.
- Python tests never write on `S:` and stay green.
- Commit points follow owner approval only. No push / DEV without approval.

## Phase 7 tasks

### 7.1 Bottom bar and empty destinations
- **Goal:** stop at two destination tabs; adopt the design's five destinations with placeholders.
- **Files:**
  - `android/app/src/main/java/io/github/catchow0/d2n/ui/main/MainScaffold.kt`
  - `android/app/src/main/java/io/github/catchow0/d2n/ui/main/ProfilePicker.kt`
  - Add icon drawables for Search, Made for you, Stats, Releases, More.
- **Behaviour:** tap placeholders print "coming in phase 8" message or snackbar; bottom bar still works.
- **Tests:** bottom tab navigation still passes; keep TaskViewModelTest green.

### 7.2 Dependencies for phase 7
- **Files:**
  - `android/gradle/libs.versions.toml`, `android/app/build.gradle.kts`
  - Add: Coil 2.x, Media3 (ExoPlayer, UI, common), Kotlinx serialization converter already there.
- **Verification:** `./gradlew assembleDebug` updates and does not break the existing tests.

### 7.3 D2nApi and models for search + previews
- **Files:**
  - `android/app/src/main/java/io/github/catchow0/d2n/data/D2nApi.kt`
  - `android/app/src/main/java/io/github/catchow0/d2n/data/ApiModels.kt`
  - `android/app/src/test/java/io/github/catchow0/d2n/data/ApiTest.kt`
- **Add endpoints:**
  - `GET /api/v1/search?q={}&type={track|album|artist}`
  - `GET /api/v1/search/album/{album_id}`
  - `GET /api/v1/search/artist/{artist_id}`
  - `GET /api/v1/preview/{track_id}`
  - `POST /api/v1/library/check` with body {items:List<{key,type,query...}>} → {results}
- **Models:** `SearchResult`, `LibraryCheckResult`, `Preview`, etc.

### 7.4 Deezer search UI
- **Goal:** search bar + filters + results + covers, quick actions (listen, download) with permission if missing, keep state.
- **Files:**
  - `android/app/src/main/java/io/github/catchow0/d2n/ui/search/SearchScreen.kt`
  - `.../search/SearchViewModel.kt`
  - Components: `TrackRow`, `AlbumCard`, `ArtistCard`.
- **Tests:** MockWebServer tests for default type, in-library badges, 404 on bad id.

### 7.5 Audio previews
- **Goal:** Media3 ExoPlayer plays a track preview inline; runs off the cleahtext allowed network config, releases on screen leave.

### 7.6 Playlists API models + screen
- **Goal:** list + create + scroll of the profile playlists, add bar, details.
- **Files:** D2nApi, ApiModels, ui/playlists/*.kt, tests MockWebServer.
- **Endpoints:** `GET /api/v1/playlists`, `POST /api/v1/playlists` body {link}, `DELETE .../{id}`.
- **Also:** add accounts, automation, scan, download, match actions; tasks linked to activity.

### 7.7 CSV import
- **Goal:** file picker → multipart upload → 201 and task follow.

### 7.8 Made for you
- **Goal:** settings (mode/limits), three lists, trial keep/remove restore, quarantine view, share to Deezer.
- **Files:** ui/madeForYou/*.kt; API `GET /api/v1/mixes`, `POST settings`, `POST generate`, trial actions.

### 7.9 Settings missing? (phase 8)
- Defer profiles etc to phase 8, only those necessary for playlists/app.
- Made for you screen only handles mode/limits via its own UI.

### 7.10 Tests
- JVM tests each VM; emulator screencaps.
- Docker build tests.

### 7.11 Documentation + Notes
- help sections: search and playlist; OpenAPI endpoints updated; stats parity tests (if added).

### 7.12 DEV build on approval

## Review Focus (phase 7)
1. Off-network edges: 304 caching and last-play must resume clean on relaunch.
2. Task events for heavy scans must not hang Activity.
3. CSV size and type boundaries (multipart).
4. Audio preview must stop when user leaves.

## Exit criteria
- Search works against DEV server; playlist works end-to-end; Made for you lists (list mode) shows and swipe action works; tests green.
- No server schema drift (parity tests).
- DEV image contains these features.