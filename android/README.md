# The Android app

Kotlin, Jetpack Compose and Material 3; Android 8 (API 26) or later, targeting API 36. The app talks to the server's `/api/v1` only, as described in `../docs/api/openapi.yaml`. Its design is in `../docs/superpowers/specs/2026-11-09-android-app-design.md`.

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

## Release procedure

1. Keep a secure backup of `release.jks` and its password; restore both to `%USERPROFILE%\.d2n-android\` before any update.
2. Build from a clean checkout of the intended commit: `scripts/build-apk.ps1` on Windows, or the `.sh` equivalent.
3. Check the APK with `apksigner verify`, extract its version/build, then let the server image copy `dist/android/` through the ordinary `COPY . /app` step.
4. On the phone, the app installs over a previous build of the same version only if the certificate matches.

## Offline, accessibility and build

- GET reads are answered from the HTTP cache when the server does not answer, and screens show the "Can't reach the server" banner with Retry.
- Compose uses `sp` text and follows the system font scale; TalkBack labels are carried on navigation icons and covers.
- Release builds use R8 (`proguard-rules.pro`). Debug builds stay unminified for fast iteration.
## Versions

- `versionName` is the server's `VERSION`; `versionCode` is `MAJOR×10000 + MINOR×100 + PATCH`.
- `BuildConfig.D2N_COMMIT` and `BuildConfig.D2N_BUILT_AT` tell two builds of one version apart: the app offers the server's APK when its `versionCode` is higher, or equal with another build.

## The code

| Package | What it does |
|---|---|
| `data` | The API client (Retrofit, OkHttp with the token and profile headers, an HTTP cache for ETags), its errors, server addresses, and the session stored in DataStore with the token sealed by Tink and the Android Keystore |
| `tasks` | Following a task: the event stream resumed with `Last-Event-ID`, then waiting for events when the stream does not get through |
| `update` | The update rule, the checked download, and Android's `PackageInstaller` |
| `ui` | The theme from the web's `tokens.css`, the components, sign-in, Deezer search, playlists, Made for you, releases, Deezer mixes, stats, settings and the app's inside: profile, Activity, More |

The fonts are Unbounded and Instrument Sans, under the SIL Open Font License (`app/src/main/assets/licenses/`).
