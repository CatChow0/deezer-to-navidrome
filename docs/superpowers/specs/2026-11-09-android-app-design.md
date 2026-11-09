# Android app: the web interface on the phone

## Context

Deezer → Navidrome is a Flask app the owner runs in Docker (`catchow/deezer-to-navidrome`), behind Authelia at `dzr-to-navi.phylumm.fr`. Version 1.17.0, built on branch `feature/api-v1` (commits `7bcafd7` and `2801a6b`, neither merged nor pushed yet), added **API v1**:

- Every function of the web interface has a counterpart under `/api/v1/`. A test enforces this parity, and `docs/api/openapi.yaml` describes all 104 operations (a contract test keeps it complete).
- A device signs in once with the app account (`POST /api/v1/auth/login`) and sends its token as `Authorization: Bearer d2n_…`. A password change signs every device out.
- The answers are JSON objects, a failure is `{"error": {"code", "message"}}`, and reads carry an ETag. The profile, meaning the Navidrome account a request is about, comes from the `X-Navidrome-Account` header.
- A long task can be followed through its event stream (resume with `Last-Event-ID`), or with `GET /api/v1/tasks/{id}/events?after=N&wait=25`.
- Covers and audio are linked under `/api/v1/` too. Authelia lets `^/api/v1/` through (documented in the README), and the device token protects it.

The app has **one account** (`APP_USERNAME`). The server's other people are Navidrome users, reached as **profiles**: each phone picks the profile it shows, as each browser does.

**Why:** the owner wants a native phone app that does what the web interface does. They approved this plan's phases 6 to 9 earlier (Kotlin + Compose). This document updates it with how the app is built and reaches the phone.

What the owner's PC has: JDK 21, the Android SDK (`%LOCALAPPDATA%\Android\Sdk`: platform 36, build-tools 35.0.0 and 36.1.0, the emulator, system images 28, 29, 31 and 36) and Docker Desktop. Jenkins builds the server image on every commit on an agent labeled `docker`, and pushes it to Docker Hub only from `main` (see `Jenkinsfile`).

## Decisions

### The owner's

- **Native Android:** Kotlin, Jetpack Compose and Material 3, Android 8 minimum (minSdk 26), target 36. Android only.
- **Scope:** the app does what the web interface does, using `/api/v1` only. The phase list below follows the approved plan.
- **Offline:** read-only from the cache. Actions are disabled while the server cannot be reached. Notifications when a task ends are optional, in phase 9.
- **Network:** `http://` is allowed, with a warning (the local network, Tailscale). Certificates the user added to the phone are trusted.
- **Build:** Jenkins builds the APK.
- **Distribution, by the server:** Jenkins puts the APK into the server's Docker image.
  - Settings in the web interface offers the download, for the first install.
  - The app offers an update when the server has a newer APK.
  - The app and the server share a version number.
- **Signing:** one key signs every build, so each version installs over the previous one. The owner keeps a backup of it.
- **The DEV image:** Claude builds it with its APK on the owner's PC, as before, and pushes it only after the owner approves. The signing key therefore lives on that PC as well as in Jenkins, outside the repository in both places.
- **The key's password on the PC:** it is saved encrypted for the owner's Windows account (DPAPI), next to the key, so Claude can build DEV APKs without anyone typing it. Any program running under that account can read it; another account, or a copy of the file on another machine, cannot.
- **The approved plan's choices that stand:**
  - Libraries: OkHttp, Retrofit and kotlinx.serialization, plus a stream client of the app's own that resumes from the last event. Coil for covers, sent with the token. Media3 for previews and audio. DataStore, and Tink with the Android Keystore for the token.
  - Look: the web's style, taken from `static/css/tokens.css`.
  - Navigation: a bottom bar (Dashboard, Made for you, Stats, Releases, More), the profile in the top bar, pull to refresh, swipe to decide, bottom sheets for actions on a track, skeletons while loading.
  - Share to the app from Deezer or Spotify to add a playlist.
  - New and Help shown as native formatted text, without a WebView.

### Claude's calls (can be overruled)

- **Package and name:** the package ID is `io.github.catchow0.d2n`. It is permanent: changing it later makes a different app, so every phone would have to reinstall. The launcher label is **D2N**, and the app's header says "Deezer → Navidrome". The interface is in English, like the web's.
- **Versions:**
  - `versionName` is the content of `VERSION`.
  - `versionCode` is `MAJOR×10000 + MINOR×100 + PATCH` (1.18.0 gives 11800).
  - The APK also carries its build identity, the commit and the build time.
  - **The update rule:** the app offers the server's APK when its `versionCode` is higher, or when it is equal and its build differs, which covers successive DEV builds of one version. Android installs an equal `versionCode` over itself and refuses a lower one, so the app never offers an older version.
- **The download needs a sign-in,** through the web session or the device token. The APK holds no secret, but there is no reason to make it public.
- **Where the APK goes:** the Android build writes `dist/android/deezer-to-navidrome.apk` and `dist/android/app.json` (version, `versionCode`, commit, build time, size, SHA-256).
  - The server image's existing `COPY . /app` picks them up when they exist. `android/` goes in `.dockerignore`, `dist/` does not.
  - An image built without them, from a fork or with no key, has no app, and Settings says so.
- **One build environment for Jenkins and the PC:** `android/Dockerfile` holds JDK 21, the Android command-line tools, platform 36 and pinned build-tools, and runs the unit tests and `assembleRelease`.
  - The key and its password arrive as build secrets (`docker build --secret`), so they never end up in an image layer.
  - The APK comes out with `--output` and no bind mount, which also works when the Jenkins agent itself runs in a container.
  - A cache keeps Gradle's downloads between builds.
- **Jenkins:**
  - An `Android` stage before `Image` clears `dist/android`, builds and signs the APK, and keeps it as a build artifact.
  - On `main`, missing key credentials fail the build: an image on Docker Hub without its app would break updates. On another branch, the stage is skipped with a warning.
  - The credentials are `android-keystore` (secret file) and `android-keystore-password` (secret text). The key alias is `d2n`.
  - The timeout goes from 20 to 45 minutes, because the first build downloads the SDK.
  - The smoke test also checks that the image holds the APK whenever the stage built one.
- **Scripts on the PC:**
  - `android/scripts/new-keystore.ps1` creates the key once: RSA 4096, valid for 10,000 days or more, in `%USERPROFILE%\.d2n-android\release.jks`.
    - It asks for the password without showing it, and saves it encrypted with DPAPI in the same folder.
    - It never writes the password into the repository, and ends with a reminder to back up the key and the password.
    - A `.sh` version does the same on Linux, without DPAPI: it reads the password from an environment variable or asks for it.
  - `android/scripts/build-apk.ps1` and `.sh` run the same Docker build with that key, and the PowerShell version reads the saved password. They fill `dist/android/`, which the local DEV image build then includes.
- **Server side, in phase 6:**
  - `GET /api/v1/app` returns `{available, version, version_code, build, size, sha256}`.
  - `GET /api/v1/app/apk` serves the file (`application/vnd.android.package-archive`, named `deezer-to-navidrome-<version>.apk`, with an ETag).
  - A web route serves the same file from a signed-in session, so the parity test covers it.
  - Settings gets an "Android app" block: the version in the image and a Download button, or why the image has no app.
  - The README, the help and the notes describe the install.
- **The update in the app:**
  - On start and on return to the foreground, at most every few hours, the app asks `GET /api/v1/app`.
  - When an update is ready, a banner offers it. The app downloads the APK with progress, checks its SHA-256, then hands it to Android's installer.
  - The first time, the app guides the user to allow installs from it. Android also checks that the signature matches the installed app.
- **Look:** dark only, like the web.
  - The `--ink` background with the aurora (violet, magenta, cyan, mint), glass cards (`--glass`, `--line`), and corner radii of 12, 16, 24 and 30.
  - Unbounded and Instrument Sans as TTF files from the Google Fonts repository (OFL licence), since the web's `.woff2` files do not work on Android.
  - Below Android 12, translucent surfaces replace the background blur.
- **The app's code:** a single-activity Compose app with Navigation Compose, ViewModels, coroutines and Flow. Modules and dependency injection are the builder's choice, with as few libraries as possible.
- **Security:**
  - The token is encrypted at rest and never logged. HTTP logging is off in release builds.
  - The device's name defaults to the phone's model and can be edited at sign-in.
- **One server at a time:** changing the address signs the app out.
- **A login proxy in the way:** when the address answers but `/api/v1/auth/status` does not say `"service": "deezer-to-navidrome"` (an Authelia login page, a redirect to another host), the app says so. It asks to let `/api/v1/` through, as the README shows, instead of showing a generic error.
- **When the server lacks something:** the app knows the API version it needs (`api` in `/api/v1/auth/status`). A route that answers 404 shows "update the server". The app never reimplements server logic. If a screen needs data the API does not give, the endpoint is added on the server, with tests and its openapi entry.
- **Branch and numbering:**
  - The work goes on branch `feature/android-app`, started from `feature/api-v1`.
  - The first server version that ships the app is **1.18.0**, "The Android app". 1.17.0 stays the API's release.
- **The first DEV push with the app** comes at the end of phase 6, once it installs, signs in and follows tasks, so the server and the app are tested together. The owner did not object to this timing when it was proposed.

### Not in this work

- iOS, the Play Store, or any store.
- Offline actions queued for later.
- A full music player for the library: Navidrome's own clients do that. The app plays what the web plays: 30-second previews, recap audio and trial tracks.
- Several app accounts, home-screen widgets, Android Auto, and layouts designed for tablets (the app works on them without being shaped for them).
- Jenkins running the Python tests: it does not today, and that is outside this work.

### Failure even if it technically works

- An update that needs the app uninstalled: a lost or changed key, a changed package ID, or a `versionCode` that goes down.
- The signing key, its password or a device token in the repository, an image layer, a log or the Jenkins console.
- An image from `main` on Docker Hub without its APK, or with the APK of another version.
- The app showing something the web does not, or deciding something the server should decide.
- A Navidrome password or a Deezer ARL displayed in the app (the API never sends them).

## Phases

Each phase ends with a full Python suite, the Android tests, a check on the emulator, and a report. A DEV image follows at the end of phase 6 and after each later phase, on the owner's approval.

### Phase 6: the signed foundation, and how it reaches the phone

- **The project in `android/`:** Gradle with the Kotlin DSL and a version catalog, a checked-in wrapper, the theme, the fonts and the base components (glass card, chips, buttons, banner, skeleton).
- **Screens:**
  - The server address, with a warning for `http://`.
  - Sign-in: the device name, wrong password, and too many attempts (shown with `Retry-After`).
  - A new server: create the account (`/auth/setup`).
  - A server with `DISABLE_AUTH`: the app runs without a token.
  - The profile picker in the top bar, from `/api/v1/info`.
  - Activity: tasks as they run, a task's events live (stream with resume, long-poll fallback), and cancel.
  - A banner when the server cannot be reached, with Retry.
  - About: the app, server and API versions.
  - Sign out.
- **Update:** the check, the banner, the download, the SHA-256 check and the installer.
- **Server:** `/api/v1/app` and `/api/v1/app/apk`, the web download route and Settings block, with tests (parity, contract, no APK, a fake APK, sign-in required).
- **Build:** `android/Dockerfile`, the key and build scripts, the Jenkins stage, and the `.gitignore` entries (`*.jks`, `*.keystore`, `android/keystore.properties`, `android/local.properties`, `android/**/build/`, `android/.gradle/`, `dist/`) and `.dockerignore` entry (`android/`).
- **Tests:**
  - JVM tests with MockWebServer: sign-in (201, 401, 429), the profile header on every request, a cached read answered 304, the stream resuming after a cut, the long-poll fallback, and the update rule.
  - On the emulator (system image 36): the screens at phone size.
  - `apksigner verify` on the APK.
  - Installs over a previous build: same `versionCode` with another build, then a higher one. The app's data must survive both.

### Phase 7: the main functions (from the approved plan)

- **Deezer search:** tracks, albums and artists, with the "in library" badges, previews and download.
- **The profile's playlists:**
  - Add one by link, including through Share from Deezer or Spotify.
  - Import a CSV with the file picker.
  - A playlist's tracks with filters, manual match and "Find on Deezer".
  - Scans, download of missing tracks, automation, the accounts it goes to, and publishing state.
  - The playlists the user made in Navidrome, read-only.
- **Made for you:** the mode and limits, the trial rules, and the three lists with search, sort, filters and covers. Swipe a track to keep or remove it.
- **Activity**, linked from each action that starts a task.

### Phase 8: the rest (from the approved plan)

- **Stats:**
  - Periods and charts drawn in Compose.
  - Artist, album and track pages, and the paged list of plays.
  - Recaps as full-screen stories, with sound and gestures.
- **Releases and Deezer mixes.**
- **Settings in full:**
  - Navidrome and Deezer accounts, the library index, paths, performance (with the same choices as the web's menus).
  - Fix metadata and Undo, Repair, duplicates (scan and apply).
  - Webhook, API token, devices, and Reset data.
- **New and Help.**

### Phase 9: polish

- **Offline:** the cache, data marked as old, and Retry.
- **Accessibility:** TalkBack labels and large fonts.
- **Performance:** a baseline profile and R8.
- **Optional:** notifications when a task ends.
- **Documentation:** the Android README, the reverse proxy, and the release procedure, key backup and restore included.

## What only the owner can do

- **Once, at the start of phase 6:**
  - Run the key script in a PowerShell window of their own (`powershell -File android\scripts\new-keystore.ps1`), not through the session, so the password never passes through the conversation. Choose the password there.
  - Back up `release.jks` and its password somewhere safe.
- **Before the first Jenkins run that builds the app:**
  - Add the `android-keystore` and `android-keystore-password` credentials.
  - Check that the agent can reach `dl.google.com`, `maven.google.com` and `services.gradle.org`, and has about 6 GB free.
- **On the phone (Android 8 or later):** allow installs from the browser for the first install, and from D2N for updates.
- **Pushes:** approve each git push and DEV push. Jenkins builds a branch only once it is on GitHub.

## Verification

- The Python suite stays green without writing on `S:`, with the new routes in the parity and contract tests.
- The Android unit tests run in the Docker build, on the PC and in Jenkins.
- The emulator, from the local system images, is used for screens and screenshots. The oldest local image is Android 9 (28), so Android 8 itself is not run. The owner's phone is used for the real install and the first update.
- `apksigner verify` checks that every APK carries the same certificate.
- The first Jenkins run happens when the owner pushes the branch or merges it. It is the only check of the agent's environment: Docker build secrets and internet access.

**Known limits:** Claude has no Android phone and cannot reach the Jenkins agent, so the emulator and the PC's Docker stand in until the owner tests.
