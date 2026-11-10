# The Android app

Kotlin, Jetpack Compose and Material 3; Android 8 (API 26) or later, targeting API 36. The app talks to the server's `/api/v1` only, as described in `../docs/api/openapi.yaml`. Its design is in `../docs/superpowers/specs/2026-11-09-android-app-design.md`.

## What it does

The app covers the web interface, for the Navidrome profile picked at the top (each screen reloads when it changes):

- **Dashboard**: the profile's playlists with their counts, adding one (a Deezer or Spotify link, a playlist ID, or a CSV), and the library's counts. Sharing a Deezer or Spotify link to the app opens the same sheet. **Search** finds tracks, albums and artists on Deezer, says what the library already holds, plays previews and downloads.
- **A playlist**: quick or full scan, downloading what is missing, filters, and per track a preview, marking it missing, choosing a library file or finding it on Deezer; its automation and publishing in a menu.
- **Made for you**: the Daily Mix mode, Discover, the limits and trial rules, the quarantine (swipe right to keep, left to remove; TalkBack offers both as actions) and the Deezer mixes.
- **Stats**: the week, month, year or all time, with tops leading to artist, album and track pages, the plays, and the recaps played as stories.
- **Releases**: the feed of the profile's Deezer account, muting artists.
- **More**: Settings (every section of the web's), Activity, What's new, Help, and the app itself.

Anything that starts a task shows a snackbar leading to it in Activity; the pulse icon at the top counts what is running.

## Without the server

When the server cannot be reached, a banner says so and the app shows what it saved:

- Every page the server answered before comes back from OkHttp's cache, for the same profile only (the server answers `Vary: X-Navidrome-Account`). A page never opened shows an error with Retry.
- Nothing that changes something is sent: the buttons are off until the server answers again. Activity, the probe and `auth/status` are never read from the cache.
- Once the app knows the server is away, reads go straight to the cache instead of waiting for a timeout on each screen. The banner's Retry, or the next call that gets through, brings everything back.

## Working on it

You need JDK 21 and the Android SDK. Point Gradle at the SDK in `local.properties`, which git ignores:

```properties
sdk.dir=C:/Users/you/AppData/Local/Android/Sdk
```

Current AndroidX compiles against Android 17, so the build uses platform 37 (it downloads it when missing) and build-tools 36.1.0; the app still targets 36.

```bash
./gradlew testDebugUnitTest   # the JVM tests: API client, task stream, updates, ViewModels
./gradlew installDebug        # the debug app on a phone or an emulator
```

- The debug app is `io.github.catchow0.d2n.debug`: it installs beside the real one and never offers the server's updates.
- On an emulator, the PC is `http://10.0.2.2`: a server running on the PC's port 8097 is `http://10.0.2.2:8097`.
- Debug and test builds take their version from `../VERSION`, their commit from git and their build time from the clock.

## Release builds

A release build needs the signing key; without it, Gradle stops with "No signing key". The scripts pass it:

- `scripts/new-keystore.ps1` (or `.sh`) creates the key once, in `%USERPROFILE%\.d2n-android\`. Back it up with its password: phones can only update the app with this same key.
- `scripts/build-apk.ps1` (Windows, with the saved key) or `scripts/build-apk.sh` (with `D2N_KEYSTORE_FILE` and `D2N_KEYSTORE_PASSWORD`) builds and signs the app in Docker, as Jenkins does, into `../dist/android/`.

`D2N_VERSION=1.18.1 scripts/build-apk.sh` builds another version than `VERSION`: only for testing updates.

The release build is shrunk by R8 (`isMinifyEnabled`, `isShrinkResources`): the libraries bring their own rules, and `app/proguard-rules.pro` only keeps line numbers for stack traces. After changing a library or the way JSON is read, build a release and walk the app on an emulator before shipping: a missing rule shows there, not in the JVM tests.

### Releasing

1. Set `VERSION` (and the notes, `core/patch_notes.py` and `templates/notes/`) as for any server version: the app takes the same number.
2. Push to `main`: Jenkins runs `scripts/build-apk.sh` with the key from its credentials, then builds the server image with the APK in it. The phones see the new version from the server.
3. On the PC, `powershell -File android\scriptsuild-apk.ps1` gives the same APK in `distndroid\`, for testing it before.

### The signing key

Phones refuse an update signed with another key: losing it means uninstalling the app on every phone. Keep a copy of `%USERPROFILE%\.d2n-android
elease.jks` and of its password somewhere else than this PC (a password manager holds both). `keystore-password.dpapi` is the password encrypted for this Windows account only: it cannot be restored on another PC or account.

To restore the key on a new PC, put `release.jks` back in `%USERPROFILE%\.d2n-android\`, then save its password again for this account:

```powershell
Read-Host "Password" -AsSecureString | ConvertFrom-SecureString | Set-Content -Encoding ascii "$env:USERPROFILE\.d2n-android\keystore-password.dpapi"
```

For Jenkins, the same `release.jks` and password go in its credentials `android-keystore` (a file) and `android-keystore-password` (a secret text). Never put the key or its password in the repository, an image or a log.

## The baseline profile

`app/src/main/baseline-prof.txt` lists the code to compile ahead of time on install, so the app starts and scrolls faster from the first launch (`profileinstaller` applies it, as the APK does not come from a store). It is versioned: the Docker build ships it without generating anything.

Generate it again after big changes to the screens, on the PC, with the `Pixel_6` emulator (API 31) running and a server on port 8097 whose account has a few playlists:

```bash
adb uninstall io.github.catchow0.d2n   # a release signed with another key is in the way
ANDROID_SERIAL=emulator-5554 ./gradlew :app:generateBaselineProfile   -Pandroid.testInstrumentationRunnerArguments.d2nPassword=<the server's password>
```

The journey (`baselineprofile/`) signs in when needed (`d2nServer`, default `http://10.0.2.2:8097`; `d2nUser`, default `admin`), opens a playlist and each tab. The result replaces `app/src/main/baseline-prof.txt`. The password is a test server's: do not pass a real one on the command line.

## Versions

- `versionName` is the server's `VERSION`; `versionCode` is `MAJOR×10000 + MINOR×100 + PATCH`.
- `BuildConfig.D2N_COMMIT` and `BuildConfig.D2N_BUILT_AT` tell two builds of one version apart: the app offers the server's APK when its `versionCode` is higher, or equal with another build.

## The code

| Package | What it does |
|---|---|
| `data` | The API client (Retrofit, OkHttp with the token and profile headers, an HTTP cache for ETags), its errors, server addresses, and the session stored in DataStore with the token sealed by Tink and the Android Keystore |
| `tasks` | Following a task: the event stream resumed with `Last-Event-ID`, then waiting for events when the stream does not get through |
| `update` | The update rule, the checked download, and Android's `PackageInstaller` |
| `audio` | The one preview player (Media3 over the app's OkHttp client), paused when the app goes to the background |
| `ui/components` | The theme's building blocks: glass cards, buttons, chips, banners, sheets, list rows, covers (Coil over the app's client) |
| `ui/main` | The five tabs, the top bar with the profile picker, the reachability banner, the snackbar and the mini player |
| `ui/dashboard`, `search`, `playlists`, `madeforyou`, `stats`, `releases`, `settings`, `content` | One package per part of the app; each screen has its ViewModel on `D2nViewModel` (loading, actions, tasks, the profile) |
| `ui/signin`, `activity`, `update`, `about` | Sign-in, Activity and a task's page, the update banner, More's "This app" |

The tests (`app/src/test/`) check each API call against MockWebServer with the JSON the server sends (`app/src/test/resources/api/`), and the ViewModels against a fake API.

The fonts are Unbounded and Instrument Sans, under the SIL Open Font License (`app/src/main/assets/licenses/`).
