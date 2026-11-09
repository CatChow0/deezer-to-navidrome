# Android app, phase 6: the signed foundation, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a signed Android app that installs, signs in, picks a profile, follows tasks live and updates itself. The same Docker build makes it in Jenkins and on the owner's PC, and the server image ships it for download from Settings.

**Architecture:**
- **Server.** It reads `dist/android/` (APK and `app.json`), copied into the image by the existing `COPY . /app`. It serves them through `/api/v1/app`, `/api/v1/app/apk` and a web route, and shows them in Settings.
- **Build.** `android/Dockerfile` builds and signs the APK with build secrets, and exports it with `--output`. `android/scripts/build-apk.sh` is the single entry point: Jenkins calls it, and `build-apk.ps1` calls it on the PC.
- **App.** A single-activity Compose app talks to `/api/v1` only, through OkHttp and Retrofit. A small hand-made dependency container wires it, and every piece of logic sits in a JVM-testable ViewModel or class.

**Tech Stack:**
- Server: Flask and unittest.
- App: Kotlin, Jetpack Compose and Material 3, OkHttp (with `mockwebserver` for tests), Retrofit with its kotlinx.serialization converter, kotlinx.coroutines, DataStore (preferences), and Tink (`tink-android`).
- Build: Gradle with the Kotlin DSL, Docker BuildKit and buildx, and Jenkins declarative.

**Spec:** `docs/superpowers/specs/2026-11-09-android-app-design.md`

## Global Constraints

**The app**
- Package ID `io.github.catchow0.d2n`, launcher label `D2N`, header text `Deezer → Navidrome`. English interface, dark theme only.
- minSdk 26, targetSdk 36, compileSdk 36, build-tools `36.1.0`. JDK 21 in the build image.
- Libraries in phase 6: those of the Tech Stack line, plus AndroidX core, activity, lifecycle and navigation for Compose. Coil and Media3 come in phase 7. Any other library needs its reason written in the task.
- Pin the versions to the latest stable releases on the day, checked on `maven.google.com`, Maven Central and `gradle.org`. A green Docker build proves them.

**Versions and update rule**
- `versionName` is the content of `VERSION`. `versionCode` is `MAJOR×10000 + MINOR×100 + PATCH` (1.18.0 gives 11800). MINOR and PATCH stay below 100, or the build fails.
- Update rule: offer the server's APK when its `version_code` is higher, or when it is equal and its `(commit, built_at)` differs. Never offer a lower one.

**Build outputs and secrets**
- Outputs: `dist/android/deezer-to-navidrome.apk` and `dist/android/app.json` = `{"version", "version_code", "commit", "built_at"}`. `built_at` is ISO 8601 UTC to the second, such as `2026-11-09T12:00:00Z`.
- Docker build secrets are `keystore` and `keystore_password`.
- The Gradle environment is `D2N_KEYSTORE_FILE` and `D2N_KEYSTORE_PASSWORD`, plus `D2N_KEY_ALIAS` (default `d2n`) and `D2N_KEY_PASSWORD` (defaults to the store password).
- Jenkins credentials: `android-keystore` (secret file) and `android-keystore-password` (secret text).
- The key folder on the PC is `%USERPROFILE%\.d2n-android\`, holding `release.jks` and `keystore-password.dpapi`.
- A key, a password or a device token never lands in the repository, an image layer, a log, the Jenkins console or the conversation. Every check in this plan uses a throwaway key in the scratchpad, never the owner's.

**Server**
- Every new `/api/v1` route goes into `docs/api/openapi.yaml`. The parity and contract tests stay green.
- Python tests use the temporary `DATA_DIR` that `tests/__init__.py` sets, and never write on `S:`.
- `android/` is in `.dockerignore`, `dist/` is not.

**Process**
- Branch `feature/android-app`, started from `feature/api-v1` (`2801a6b`). `VERSION` is `1.18.0`.
- The owner decides commits: each "Commit point" step is where a commit would go. Commit only once the owner has asked for commits. Never `git push` or push a Docker tag without their approval for that push.
- Talk to the owner in French. Every text in the app and the code is English.

## Review Focus

1. **A server address typed loosely:** `dzr-to-navi.phylumm.fr`, a trailing slash, spaces, capitals, or an install under a sub-path (`https://host/d2n`). The address should be normalized, and every call should keep the sub-path. Pinned in Task 4 (`ServerAddressTest`).
2. **The network drops halfway through an update download:** no partial file may stay or be installed, and a new try must work. Pinned in Task 6 (`a cut in the middle leaves no file`).
3. **The device token is revoked** (sign-out from the web, a new password) while the app is open: the app returns to sign-in with a message, instead of looping on errors. Pinned in Task 8 (`a 401 signs the app out`).
4. **The chosen profile is deleted on the web:** the app falls back to the default profile and stops sending the dead ID. Pinned in Task 8 (`a profile that no longer exists falls back to the default`).
5. **The server no longer knows a task** (it restarted, or the task was pruned): the stream sends one "Task not found" event, and the task screen shows the task as ended instead of reconnecting forever. Pinned in Task 5 (`a task the server no longer knows ends the flow`).

---

### Task 1: The server ships the app

**Files:**
- Create: `core/android_app.py`, `routes/android.py`, `routes/api_v1/app.py`, `templates/notes/1.18.0.html`, `tests/test_android_app.py`
- Modify:
  - `app.py`: register `android_bp`.
  - `routes/api_v1/__init__.py`: add `app` to the import list at the bottom.
  - `routes/playlists.py`: `render_app` passes `android_app=android_app.info()`.
  - `templates/_settings.html`: a new `set-row` after the "Sign-in and other apps" section.
  - `docs/api/openapi.yaml`: the two paths and an `AppInfo` schema.
  - `VERSION`: set to `1.18.0`.
  - `core/patch_notes.py`: add `{"version": "1.18.0", "date": "2026-11-09", "title": "The Android app"}` first.
  - `README.md` and `DOCKERHUB_README.md`: the version badges.

**Interfaces:**
- Produces, in `core/android_app.py`:
  - `DIST_DIR: Path` (repo root `/dist/android`), `APK_NAME = "deezer-to-navidrome.apk"`, `MIME = "application/vnd.android.package-archive"`, `MISSING = "This image was built without the Android app."`.
  - `info() -> dict`: `{"available": True, "version", "version_code", "build": {"commit", "built_at"}, "size", "sha256"}`, or `{"available": False, "reason": MISSING}`.
  - `apk_path() -> Path | None` and `download_name() -> str` (`deezer-to-navidrome-<version>.apk`).
- Produces: the web endpoint `android.apk` at `GET /app/android.apk`, and `GET /api/v1/app` and `GET /api/v1/app/apk` (Task 6 and Task 8 call them).

- [ ] **Step 1: Create the branch.** `git switch -c feature/android-app` from `feature/api-v1`; `git log --oneline -1` shows `2801a6b`.

- [ ] **Step 2: Write the failing tests** in `tests/test_android_app.py`.
  - Subclass `tests.test_api_v1.Base`, which gives a signed-in device token through `self.token()`.
  - In `setUp`, patch `core.android_app.DIST_DIR` to a fresh temporary folder, and clear the hash cache.
  - Use `self.put_apk(data=b"PK\x03\x04fake apk", meta={"version": "1.18.0", "version_code": 11800, "commit": "abc1234", "built_at": "2026-11-09T12:00:00Z"})`.

```python
def test_without_an_apk_the_app_is_not_available(self):
    auth = {"Authorization": f"Bearer {self.token()}"}
    self.assertEqual(self.client.get("/api/v1/app", headers=auth).get_json(),
                     {"available": False, "reason": "This image was built without the Android app."})
    missing = self.client.get("/api/v1/app/apk", headers=auth)
    self.assertEqual((missing.status_code, missing.get_json()["error"]["code"]), (404, "not_found"))

def test_the_apk_and_what_it_is(self):
    data = self.put_apk()
    auth = {"Authorization": f"Bearer {self.token()}"}
    self.assertEqual(self.client.get("/api/v1/app", headers=auth).get_json(), {
        "available": True, "version": "1.18.0", "version_code": 11800,
        "build": {"commit": "abc1234", "built_at": "2026-11-09T12:00:00Z"},
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    apk = self.client.get("/api/v1/app/apk", headers=auth)
    self.assertEqual((apk.status_code, apk.mimetype, apk.data), (200, "application/vnd.android.package-archive", data))
    self.assertIn("deezer-to-navidrome-1.18.0.apk", apk.headers["Content-Disposition"])
    again = self.client.get("/api/v1/app/apk", headers={**auth, "If-None-Match": apk.headers["ETag"]})
    self.assertEqual(again.status_code, 304)

def test_the_size_and_hash_come_from_the_file(self):
    # A stale app.json cannot lie about the file: rewrite the APK only.
    self.put_apk(data=b"first")
    (core.android_app.DIST_DIR / "deezer-to-navidrome.apk").write_bytes(b"second, longer")
    info = core.android_app.info()
    self.assertEqual((info["size"], info["sha256"]), (14, hashlib.sha256(b"second, longer").hexdigest()))

def test_a_damaged_app_json_means_no_app(self):
    self.put_apk()
    (core.android_app.DIST_DIR / "app.json").write_text("{not json", encoding="utf-8")
    self.assertFalse(core.android_app.info()["available"])

def test_the_download_needs_a_sign_in(self):
    self.put_apk()
    self.assertEqual(self.client.get("/api/v1/app").status_code, 401)
    self.assertEqual(self.client.get("/api/v1/app/apk").status_code, 401)
    self.assertEqual(self.client.get("/app/android.apk").status_code, 401)
    with mock.patch.dict(os.environ, {"API_TOKEN": "catboard-token-123"}):
        self.assertEqual(self.client.get("/app/android.apk", headers={"Authorization": "Bearer catboard-token-123"}).status_code, 401)

def test_settings_offers_the_download(self):
    with mock.patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
        empty = self.client.get("/config", headers={"Accept": "text/html"}).get_data(as_text=True)
        self.put_apk()
        page = self.client.get("/config", headers={"Accept": "text/html"}).get_data(as_text=True)
        web = self.client.get("/app/android.apk")
    self.assertIn("This image was built without the Android app.", empty)
    self.assertIn("Android app", page)
    self.assertIn('href="/app/android.apk"', page)
    self.assertIn("1.18.0", page)
    self.assertEqual(web.status_code, 200)
```

- [ ] **Step 3: Run them to see them fail.**
  - Run: `"$SP/venv/Scripts/python" -m unittest tests.test_android_app -v`, with `SP` being the scratchpad. The repo has no global Python with the dependencies.
  - Expected: an error, because `core.android_app` does not exist.

- [ ] **Step 4: Implement `core/android_app.py`.**
  - `info()` reads `app.json` (the keys `version`, `version_code`, `commit`, `built_at`) and the APK.
  - It takes `size` and `sha256` from the APK file. The hash is cached in a module dict keyed by `(str(path), st_mtime_ns, st_size)`.
  - A missing file, invalid JSON or a missing key gives `{"available": False, "reason": MISSING}`.

- [ ] **Step 5: Implement the routes.**
  - **`routes/android.py`:** `android_bp`, with `@android_bp.get("/app/android.apk") def apk()`.
    - Without an APK, it answers `jsonify({"ok": False, "error": MISSING}), 404`.
    - Otherwise it answers `send_file(path, mimetype=MIME, as_attachment=True, download_name=download_name(), conditional=True, etag=True, max_age=0)`, with `Cache-Control: private, no-cache`.
  - **`routes/api_v1/app.py`:** `GET /app` returns `ok(android_app.info(), cache=True)`, and `expose("/app/apk", android.apk, name="app_apk")`.
  - **Register** `android_bp` in `app.py`.

- [ ] **Step 6: Add the Settings block and the version.**
  - **Settings block:** a section `id="android-app"` titled "Android app", with the subtitle "The app for your phone, built with this version of the server. It updates itself from here."
    - With an APK: `Version {{ version }} · {{ size in MB, 1 decimal }} MB · build {{ commit }}`, a `<a class="btn" href="{{ url_for('android.apk') }}" download>Download the app</a>` link, and a muted line: "Open this page on your phone to install it. Android asks once to allow installs from your browser."
    - Without one: `{{ android_app.reason }}`.
  - **`openapi.yaml`:** `/api/v1/app` (get, `AppInfo`) and `/api/v1/app/apk` (get: 200 `application/vnd.android.package-archive`, 404 `Error`).
  - **Version:** `VERSION` becomes `1.18.0`, with its `patch_notes` entry and badges.
  - **`templates/notes/1.18.0.html`:** a first paragraph, "The Android app: install it from Settings, and it updates itself from your server." Task 9 completes it.

- [ ] **Step 7: Run the new tests and the whole suite.**
  - Run: `"$SP/venv/Scripts/python" -m unittest tests.test_android_app -v`. Expected: 6 tests OK.
  - Then run `"$SP/venv/Scripts/python" -m unittest discover -s tests -t .`. Expected: everything OK, the parity and contract tests included.

- [ ] **Step 8: Commit point.** The files above: `feat(android): the server ships the app and offers it in Settings`.

---

### Task 2: The Android project and its build

**Files:**
- Modify: `.gitignore`, `.dockerignore` (add `android`).
- Create:
  - `.gitattributes`: `*.sh text eol=lf`, `android/gradlew text eol=lf`, `*.bat text eol=crlf`, `*.jar binary`, `*.ttf binary`, `*.png binary`.
  - `android/.dockerignore`: `**/build`, `.gradle`, `local.properties`, `keystore.properties`, `*.jks`, `*.keystore`, `.idea`.
  - Gradle: `android/settings.gradle.kts`, `android/build.gradle.kts`, `android/gradle.properties`, `android/gradle/libs.versions.toml`, the wrapper (`android/gradlew`, `android/gradlew.bat`, `android/gradle/wrapper/gradle-wrapper.jar`, `android/gradle/wrapper/gradle-wrapper.properties`, with `distributionSha256Sum`), and `android/app/build.gradle.kts`.
  - App: `android/app/src/main/AndroidManifest.xml`, `android/app/src/main/java/io/github/catchow0/d2n/MainActivity.kt` (a placeholder saying "Deezer → Navidrome"), `res/values/strings.xml` (`app_name` = `D2N`), `res/values/themes.xml` (`Theme.D2N`: no action bar, window background `#07061a`), `res/xml/network_security_config.xml`, and the adaptive icon in `res/mipmap-anydpi-v26/ic_launcher.xml` and `ic_launcher_round.xml`, with `res/drawable/ic_launcher_foreground.xml`.
  - Build: `android/Dockerfile`, `android/scripts/build-apk.sh`, `android/scripts/build-apk.ps1`, `android/scripts/new-keystore.ps1`, `android/scripts/new-keystore.sh`.
- The `.gitignore` entries: `*.jks`, `*.keystore`, `android/keystore.properties`, `android/local.properties`, `android/**/build/`, `android/.gradle/`, `dist/`.

**Interfaces:**
- Produces, as Gradle properties: `-Pd2n.version`, `-Pd2n.commit` and `-Pd2n.builtAt`.
  - Without them, the version is read from `../VERSION`, the commit from `git rev-parse --short=7 HEAD` (or `dev`), and the time is now.
- Produces the `BuildConfig` fields `D2N_COMMIT` and `D2N_BUILT_AT`, besides `VERSION_CODE` and `VERSION_NAME`.
- Produces the Gradle task `:app:packageD2n`, which writes `app/build/d2n/deezer-to-navidrome.apk` and `app/build/d2n/app.json`.
- Produces the Dockerfile targets `sdk`, `build` and `out` (the last one is `FROM scratch` holding the two files). The build args are `D2N_VERSION`, `D2N_COMMIT` and `D2N_BUILT_AT`.
- Produces `bash android/scripts/build-apk.sh`.
  - It needs `D2N_KEYSTORE_FILE` and `D2N_KEYSTORE_PASSWORD`, and fills `dist/android/` at the repo root.
  - `D2N_VERSION` in the environment overrides `VERSION`, for the update test of Task 9 only.

- [ ] **Step 1: Ignore files and line endings.** Write the ignore files and `.gitattributes`. `git check-ignore -v dist/android/x android/app/build/x android/local.properties` lists all three.

- [ ] **Step 2: The Gradle project.**
  - **The wrapper:** generate it with the official `gradle:<version>-jdk21` image, then add `distributionSha256Sum` from gradle.org:
    `MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W)/android:/p" -w /p gradle:<version>-jdk21 gradle wrapper --gradle-version <version> --distribution-type bin`
  - **`app/build.gradle.kts`:**
    - It applies `com.android.application`, `org.jetbrains.kotlin.android`, `org.jetbrains.kotlin.plugin.compose` and `org.jetbrains.kotlin.plugin.serialization`.
    - It sets the IDs, SDK levels and build-tools of the Global Constraints, and Java/Kotlin target 17.
    - The `debug` type gets `applicationIdSuffix = ".debug"` and `versionNameSuffix = "-debug"`.
    - The `release` type keeps `isMinifyEnabled = false` (R8 comes in phase 9). Its `signingConfig` reads the four `D2N_KEY*` variables, and only when `D2N_KEYSTORE_FILE` is set.
  - **Version checks:** `versionCodeOf(version: String): Int` refuses anything other than `^\d+\.\d+\.\d+$`, or MINOR or PATCH ≥ 100, with `GradleException("VERSION must look like 1.18.0, with MINOR and PATCH below 100")`.
  - **Missing key:** `preReleaseBuild` gets a `doFirst` that fails with `GradleException("No signing key: set D2N_KEYSTORE_FILE and D2N_KEYSTORE_PASSWORD (android/scripts/build-apk.ps1 does it on the PC)")` when either is missing.
  - **`packageD2n`:** it depends on `assembleRelease`, copies `outputs/apk/release/app-release.apk`, and writes `app.json` from the same values as `versionCode` and `versionName`.

- [ ] **Step 3: The minimal app.**
  - **Manifest:** `INTERNET`, `android:networkSecurityConfig`, `android:label="@string/app_name"`, `Theme.D2N`, and `MainActivity` as the launcher.
  - **`network_security_config.xml`:** `cleartextTrafficPermitted="true"` on `base-config`, with `<certificates src="system"/>` and `<certificates src="user"/>`.
  - **Icon:** background `#07061a`, and as foreground a "→" stroke with a violet `#8b5cf6` to cyan `#22d3ee` gradient.
  - **Local check:** with `android/local.properties` holding `sdk.dir=C\:\\Users\\antho\\AppData\\Local\\Android\\Sdk`, `cd android && ./gradlew assembleDebug` succeeds.

- [ ] **Step 4: `android/Dockerfile`.**
  - **The `sdk` stage:** `eclipse-temurin:21-jdk-noble`, with its tag pinned. Then the Android command-line tools zip from `dl.google.com`, its build number and `sha256` pinned and checked with `sha256sum -c`. Then `yes | sdkmanager --licenses`, and `sdkmanager "platforms;android-36" "build-tools;36.1.0"`.
  - **The `build` stage:** `COPY` the wrapper and settings files first, then `app/`.
  - **The build command:** `RUN --mount=type=cache,target=/root/.gradle --mount=type=secret,id=keystore,required=true --mount=type=secret,id=keystore_password,required=true`.
    - It exports `D2N_KEYSTORE_FILE=/run/secrets/keystore` and `D2N_KEYSTORE_PASSWORD="$(cat /run/secrets/keystore_password)"` for this command only.
    - It runs `sh ./gradlew --no-daemon -Pd2n.version="$D2N_VERSION" -Pd2n.commit="$D2N_COMMIT" -Pd2n.builtAt="$D2N_BUILT_AT" testReleaseUnitTest packageD2n`.
  - **The `out` stage:** `FROM scratch` and `COPY --from=build /src/app/build/d2n/ /`.

- [ ] **Step 5: The scripts.**
  - **`build-apk.sh`:** `set -euo pipefail`. It fails with a clear message when either variable is missing.
    - It reads the version (`D2N_VERSION` or `VERSION`), the commit and the UTC time, then removes `dist/android`.
    - It runs `docker buildx build --file android/Dockerfile --target out --output type=local,dest=<root>/dist/android --secret id=keystore,src="$D2N_KEYSTORE_FILE" --secret id=keystore_password,env=D2N_KEYSTORE_PASSWORD --build-arg …` on the `android` context, then checks that both files exist.
  - **`build-apk.ps1`** has `-KeyDir`, defaulting to `$env:USERPROFILE\.d2n-android`.
    - It fails with "Create the key first: powershell -File android\scripts\new-keystore.ps1" when `release.jks` or `keystore-password.dpapi` is missing.
    - It decrypts the password (`ConvertTo-SecureString`, then `NetworkCredential`), sets the two variables for its own process only, runs `bash android/scripts/build-apk.sh`, and clears them in `finally`.
  - **`new-keystore.ps1`** has `-KeyDir` as well.
    - It refuses when `release.jks` already exists, saying that losing it means reinstalling on every phone.
    - It asks for the password twice with `Read-Host -AsSecureString`, requiring them to match and to have 12 characters or more.
    - It runs `keytool -genkeypair -keystore <KeyDir>\release.jks -storetype PKCS12 -storepass:env D2N_KS_PASS -alias d2n -keyalg RSA -keysize 4096 -validity 10950 -dname "CN=Deezer to Navidrome, O=CatChow0"`.
    - It saves `ConvertFrom-SecureString` into `keystore-password.dpapi`, and ends with the backup reminder.
  - **`new-keystore.sh`:** the same with `read -rs`, without DPAPI.

- [ ] **Step 6: Build with a throwaway key.**
  - **Create the key:** `keytool -genkeypair -keystore "$SP/testkey/release.jks" -storetype PKCS12 -storepass:env TEST_KS_PASS -alias d2n -keyalg RSA -keysize 2048 -validity 30 -dname "CN=D2N throwaway"`.
  - **Save its password with DPAPI:** `powershell -Command "ConvertTo-SecureString $env:TEST_KS_PASS -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -Encoding ascii '$SP/testkey/keystore-password.dpapi'"`.
  - **Build:** `powershell -File android/scripts/build-apk.ps1 -KeyDir "$SP/testkey"`. Expected: exit 0, and `dist/android/` holds both files.

- [ ] **Step 7: Check the APK.**
  - **`app.json`** shows `"version": "1.18.0"`, `"version_code": 11800`, and `"commit"` equal to `git rev-parse --short=7 HEAD`.
  - **Signature:** `"$LOCALAPPDATA/Android/Sdk/build-tools/36.1.0/apksigner.bat" verify --print-certs dist/android/deezer-to-navidrome.apk` prints `CN=D2N throwaway` and verifies with v2 or later.
  - **Badging:** `"$LOCALAPPDATA/Android/Sdk/build-tools/36.1.0/aapt2.exe" dump badging dist/android/deezer-to-navidrome.apk` shows `package: name='io.github.catchow0.d2n' versionCode='11800' versionName='1.18.0'`, `sdkVersion:'26'`, `targetSdkVersion:'36'` and `application-label:'D2N'`.
  - **No leak:** `grep -rl "$TEST_KS_PASS" android dist` finds nothing, and `git status --short` shows no key file.
  - **Failure without a key:** `env -u D2N_KEYSTORE_FILE bash android/scripts/build-apk.sh` fails with its message, and `dist/android` is absent.

- [ ] **Step 8: The server image picks up the APK.**
  - `docker build -t d2n-apk-check .`, then `docker run --rm d2n-apk-check python -c "from core import android_app; i = android_app.info(); print(i['available'], i['version_code'])"`. Expected: `True 11800`.
  - `docker run --rm d2n-apk-check ls /app/android` fails, because `android/` stays out of the image.
  - Remove the test image.

- [ ] **Step 9: Commit point.** `feat(android): the project, its Docker build, and the key and build scripts`.

---

### Task 3: Jenkins builds the app

**Files:**
- Modify: `Jenkinsfile`

**Interfaces:**
- Consumes: `bash android/scripts/build-apk.sh` and its two variables (Task 2), and `core.android_app.info()` (Task 1).

- [ ] **Step 1: Raise the timeout** from `timeout(time: 20, …)` to `timeout(time: 45, unit: 'MINUTES')`, with a comment that the first build downloads the SDK.

- [ ] **Step 2: Add the `Android` stage** between `Infos` and `Image`.
  - **Clear:** `sh 'rm -rf dist/android'`.
  - **Probe the key** in a `script` block: an empty `withCredentials([file(credentialsId: 'android-keystore', variable: 'KS_PROBE'), string(credentialsId: 'android-keystore-password', variable: 'KS_PASS_PROBE')]) { }` inside `try` and `catch (err)`. Only a missing credential can fail an empty block.
  - **When the key is missing:**
    - On `main`: `error('No Android signing key in Jenkins (android-keystore, android-keystore-password): an image from main must carry the app.')`.
    - Elsewhere: `echo 'WARNING: no Android signing key in Jenkins: this image is built without the app.'` and `env.HAS_APK = 'false'`.
  - **When it is there:** `withCredentials([file(credentialsId: 'android-keystore', variable: 'D2N_KEYSTORE_FILE'), string(credentialsId: 'android-keystore-password', variable: 'D2N_KEYSTORE_PASSWORD')]) { sh 'bash android/scripts/build-apk.sh' }`, then `env.HAS_APK = 'true'`. A failed build fails the stage.
  - **Keep the APK:** `archiveArtifacts artifacts: 'dist/android/*', allowEmptyArchive: true, fingerprint: true`.

- [ ] **Step 3: Extend the smoke test.** After `/health` answers, and only when `HAS_APK` is `true`:
  `docker exec $CONTAINER python -c "from core import android_app; import sys; sys.exit(0 if android_app.info()['available'] else 1)"`.

- [ ] **Step 4: Check it locally.** Jenkins cannot be run here.
  - **Jenkins's own command:** in Git Bash, with `D2N_KEYSTORE_FILE="$SP/testkey/release.jks"` and `D2N_KEYSTORE_PASSWORD="$TEST_KS_PASS"`, run `bash android/scripts/build-apk.sh`. Expected: exit 0, and both files.
  - **The smoke test's one-liner:** it exits 0 on an image built with `dist/android`, and 1 on one built after `rm -rf dist/android`.
  - **Read the Groovy again,** checking for balanced blocks, `IS_MAIN` used as a string, and no credential echoed. Note in the report that the first real run happens when the owner pushes the branch.

- [ ] **Step 5: Commit point.** `ci(android): Jenkins builds, signs and ships the app`.

---

### Task 4: The app's data layer

**Files:**
- Create in `android/app/src/main/java/io/github/catchow0/d2n/data/`: `ApiModels.kt`, `D2nApi.kt`, `ApiFailures.kt`, `HttpClient.kt`, `ApiProvider.kt`, `ServerAddress.kt`, `SettingsStore.kt`, `SecretBox.kt`.
- Create in `android/app/src/test/java/io/github/catchow0/d2n/`: `data/ApiTest.kt`, `data/ServerAddressTest.kt`, `data/SettingsStoreTest.kt`, `testutil/FakeSettingsStore.kt`, `testutil/MainDispatcherRule.kt`.
- Modify: `android/gradle/libs.versions.toml` and `android/app/build.gradle.kts` (the libraries of this task).

**Interfaces:**
- **The JSON setup:** `val D2nJson = Json { ignoreUnknownKeys = true; explicitNulls = false; coerceInputValues = true }`.
- **Models,** all `@Serializable`, with `@SerialName` for the snake_case keys:
  - `AuthStatus(service, api, auth)` and `Credentials(username, password, device)`.
  - `DeviceInfo(id, name)` and `SignedIn(token, device, username)`.
  - `Profile(id, label, isDefault)`, and `ServerInfo(version, api, username?, authDisabled, profile?, profiles: List<Profile>)`.
  - `TaskSummary(id, title, kind?, createdAt?, updatedAt?, finishedAt?, done, error, stage?, message?, progress?, cancellable, cancelRequested, cancelled, events?)`. All fields beyond `id` have defaults.
  - `TaskList(tasks)` and `TaskEnvelope(task)`.
  - `TaskEvent(index = -1, type = "status", message?, progress?, stage?, done = false, error = false, cancelled = false, timestamp?)`, and `TaskEvents(task, events, after)`.
  - `CancelAnswer(cancelling)`, `SignedOut(signedOut)`.
  - `AppBuild(commit, builtAt)`, and `AppInfo(available, version?, versionCode?, build?, size?, sha256?, reason?)`.
  - `ApiErrorBody(error: ApiErrorDetail(code, message, retryAfter?))`.
- **`interface D2nApi`:**
  - Every path is relative, `api/v1/...` with no leading `/`, so that a sub-path base keeps its path.
  - Its functions: `authStatus()`, `login(Credentials)`, `setup(Credentials)`, `logout()`, `info()`, `tasks(changedSince: Double? = null)`, `task(id)`, `taskEvents(id, after: Int, wait: Int)`, `cancelTask(id)`, `app()`.
- **Failures:**
  - `sealed class ApiFailure : Exception`.
  - `ApiError(status: Int, code: String, message: String, retryAfterSeconds: Int?)`, `Unreachable(cause)`, and `NotThisServer(detail)`.
  - `suspend fun <T> apiCall(block: suspend () -> T): T` maps `HttpException` to `ApiError`, reading the body, with the `Retry-After` header as a fallback. It maps `IOException` to `Unreachable`, and a `SerializationException` to `NotThisServer`.
- **The HTTP client:**
  - `data class RequestHeaders(val token: String?, val profile: String?)`.
  - `fun buildHttpClient(cacheDir: File?, headers: () -> RequestHeaders, userAgent: String, onUnauthorized: () -> Unit = {}): OkHttpClient`.
    - It adds `Authorization: Bearer` and `X-Navidrome-Account` when they are set, and `User-Agent: D2N/<versionName> (Android <sdk>)`.
    - A 20 MiB `Cache` lives in `cacheDir/http`.
    - The connect timeout is 10 s and the read timeout 35 s.
    - `onUnauthorized` runs on a 401 from any path except `api/v1/auth/login` and `api/v1/auth/setup`. Task 8 uses it.
- **The API provider:** `class ApiProvider(client: OkHttpClient) { fun forServer(base: HttpUrl): D2nApi }` keeps the last instance for each base.
- **Server addresses:** `object ServerAddress { fun normalize(input: String): HttpUrl? }` and `val HttpUrl.isCleartext: Boolean`.
- **Storage:**
  - `data class StoredSession(ready = false, serverUrl: String? = null, token: String? = null, authDisabled = false, profile: String? = null, deviceName: String? = null, lastUpdateCheck: Long = 0)`.
  - `interface SettingsStore`: `val state: StateFlow<StoredSession>`, `suspend fun setServer(url: String, authDisabled: Boolean)` (a new URL clears the token and the profile), `setToken(token: String?)`, `setProfile(id: String?)`, `setDeviceName(name: String)`, `setLastUpdateCheck(epochMillis: Long)`.
  - `class DataStoreSettingsStore(dataStore: DataStore<Preferences>, box: SecretBox, scope: CoroutineScope) : SettingsStore`.
  - `interface SecretBox { fun seal(plain: String): String; fun open(sealed: String): String }`.
  - `class TinkSecretBox(context: Context) : SecretBox` uses AES256-GCM AEAD with `AndroidKeysetManager` and the master key `android-keystore://d2n_master_key`.

- [ ] **Step 1: Write the failing tests.**

```kotlin
// ServerAddressTest
@Test fun `a bare host gets https and a trailing slash`() =
    assertEquals("https://dzr-to-navi.phylumm.fr/", ServerAddress.normalize("  dzr-to-navi.phylumm.fr ")?.toString())
@Test fun `a sub-path is kept`() =
    assertEquals("https://host.example/d2n/", ServerAddress.normalize("https://Host.Example/d2n")?.toString())
@Test fun `http is kept and flagged`() =
    assertTrue(ServerAddress.normalize("http://192.168.1.10:8080")!!.isCleartext)
@Test fun `nonsense is refused`() = assertNull(ServerAddress.normalize("not an address"))

// ApiTest, against MockWebServer at server.url("/d2n/") so every path must keep the sub-path
@Test fun `signing in returns the token and the device`()          // 201 {"token":"d2n_x","device":{"id":"d1","name":"Pixel"},"username":"admin"}; recorded path "/d2n/api/v1/auth/login"
@Test fun `a wrong password raises wrong_credentials`()            // 401 body → ApiError(401, "wrong_credentials", "Wrong username or password.", null)
@Test fun `too many attempts carries the wait`()                   // 429, header Retry-After: 30 → retryAfterSeconds == 30
@Test fun `every request carries the token and the profile`()      // two calls; both recorded requests have "Bearer d2n_x" and X-Navidrome-Account "nd2"
@Test fun `a read the server says is unchanged comes from the cache`() // 1st: 200 + ETag "abc" + Cache-Control "private, no-cache"; 2nd: request has If-None-Match "abc", server 304; both results equal
@Test fun `unknown fields are ignored`()                           // info() with an extra "future": {...} key parses
@Test fun `a server that is gone raises Unreachable`()             // server.shutdown() then call → Unreachable

// SettingsStoreTest, with PreferenceDataStoreFactory on a temp file and a SecretBox that reverses strings
@Test fun `the token is stored sealed`()        // raw preferences do not contain "d2n_secret"; state.token == "d2n_secret"
@Test fun `a new server forgets the token and the profile`()
```

- [ ] **Step 2: Run the tests to see them fail.** Run `cd android && ./gradlew testDebugUnitTest --tests "io.github.catchow0.d2n.data.*"`. Expected: compilation errors, because the classes are missing.

- [ ] **Step 3: Implement the files listed above** to the Interfaces block.
  - `normalize` trims, adds `https://` when the scheme is missing, and parses with `toHttpUrlOrNull()`. It requires a host with a dot, a host named `localhost`, or an IP address, and ends the path with `/`.

- [ ] **Step 4: Run the tests to see them pass.** Run the same command. Expected: 13 tests passing.

- [ ] **Step 5: Commit point.** `feat(android): the API client, its errors, and the encrypted session`.

---

### Task 5: Following a task

**Files:**
- Create: `android/app/src/main/java/io/github/catchow0/d2n/tasks/SseParser.kt`, `tasks/TaskFollower.kt`
- Test: `android/app/src/test/java/io/github/catchow0/d2n/tasks/TaskFollowerTest.kt`. The parser is tested through the follower.

**Interfaces:**
- Consumes: `D2nApi.taskEvents`, `TaskEvent`, `D2nJson` and the `OkHttpClient` (Task 4).
- Produces:
  - `data class SseMessage(val id: Int?, val data: String?, val retryMillis: Long?)`, and `object SseParser { fun messages(source: BufferedSource): Sequence<SseMessage> }`. It ignores `:` comment lines, and a message ends at a blank line.
  - `sealed interface TaskUpdate { data class Event(val event: TaskEvent) : TaskUpdate; data class Ended(val error: Boolean, val message: String?) : TaskUpdate }`.
  - `class TaskFollower(client: OkHttpClient, api: (HttpUrl) -> D2nApi, pause: suspend (Long) -> Unit = { delay(it) })`, with `fun follow(base: HttpUrl, taskId: String, after: Int = -1): Flow<TaskUpdate>`.

**Behaviour:**
- **The stream:** `GET <base>api/v1/tasks/<id>/stream`, with `Last-Event-ID: <last>` once an event has been seen.
- **Each event:** the `id:` sets the event's `index`. An event with `done` emits `Event`, then `Ended(error, message)`, and completes.
- **A message without an ID** carrying `done` and `error` is the server's "Task not found": `Ended(true, message)`, with no further request.
- **The end of a segment** reconnects after the server's `retry` (1500 ms).
- **Failures:** three connection failures or HTTP errors in a row switch to `taskEvents(id, after = last, wait = 25)` in a loop, until done. An I/O error waits 1, 2, 5 then 10 s.
- **Stopping:** cancelling the collector closes the call.

- [ ] **Step 1: Write the failing tests.** MockWebServer with a `Dispatcher`, and `pause = {}`.

```kotlin
@Test fun `events arrive in order and the flow ends with the task`()  // body "retry: 1500\n\nid: 0\ndata: {...message one}\n\nid: 1\ndata: {...done:true}\n\n" → [Event(0), Event(1), Ended(false, ...)]
@Test fun `after a cut it resumes from the last event`()              // 1st response ends after id 1 without done; 2nd request header Last-Event-ID == "1"; returns id 2 done
@Test fun `keepalives and retry lines are ignored`()                  // ": keepalive\n\n" between events changes nothing
@Test fun `when the stream keeps failing it waits for events instead`() // 3 × 503 on /stream, then request path "/api/v1/tasks/t1/events?after=-1&wait=25" answered with 2 events, the last done
@Test fun `a task the server no longer knows ends the flow`()         // body "retry: 1500\n\ndata: {\"type\":\"status\",\"message\":\"Task not found\",\"done\":true,\"error\":true}\n\n" → [Ended(true, "Task not found")]; server.requestCount == 1
```

- [ ] **Step 2: Run the tests to see them fail.** Run `cd android && ./gradlew testDebugUnitTest --tests "io.github.catchow0.d2n.tasks.*"`. Expected: compilation errors.

- [ ] **Step 3: Implement `SseParser` and `TaskFollower`** with the behaviour above. Use `callbackFlow`, or `flow` with `withContext(Dispatchers.IO)`, and run the blocking reads on IO.

- [ ] **Step 4: Run the tests to see them pass.** Expected: the 5 tests of TaskFollowerTest pass.

- [ ] **Step 5: Commit point.** `feat(android): follow a task, resuming the stream or waiting for events`.

---

### Task 6: Updates from the server

**Files:**
- Create in `android/app/src/main/java/io/github/catchow0/d2n/update/`: `BuildIdentity.kt`, `UpdateRule.kt`, `UpdateChecker.kt`, `ApkDownloader.kt`, `ApkInstaller.kt` (with its install-status receiver).
- Modify: `AndroidManifest.xml`, adding `android.permission.REQUEST_INSTALL_PACKAGES` and the receiver (`exported="false"`).
- Test: `android/app/src/test/java/io/github/catchow0/d2n/update/UpdateRuleTest.kt`, `UpdateCheckerTest.kt`, `ApkDownloaderTest.kt`.

**Interfaces:**
- Consumes: `AppInfo`, `D2nApi.app()`, `SettingsStore` and `apiCall` (Task 4).
- Produces:
  - `data class BuildIdentity(versionCode: Int, versionName: String, commit: String, builtAt: String)`, and `BuildIdentity.current()` read from `BuildConfig`.
  - `object UpdateRule { fun shouldOffer(own: BuildIdentity, server: AppInfo): Boolean }`.
  - `class UpdateChecker(api: () -> D2nApi?, store: SettingsStore, own: BuildIdentity, now: () -> Long, minIntervalMillis: Long = 6 * 3_600_000L)`.
    - `suspend fun check(force: Boolean = false): AppInfo?` returns the offer, or `null`.
    - It saves the check's time with `setLastUpdateCheck`.
    - A 404 means a server older than 1.18.0, without `/api/v1/app`: no offer, and no error.
  - `class ApkDownloader(client: OkHttpClient)`, with `suspend fun download(url: HttpUrl, dir: File, expectedSha256: String, onProgress: (read: Long, total: Long) -> Unit): File`.
    - It writes `deezer-to-navidrome.apk.part`, then checks the hash and renames the file to `deezer-to-navidrome.apk`.
    - A wrong hash deletes the file and throws `DamagedDownload`. A cut deletes the `.part` and throws `Unreachable`.
  - `interface ApkInstaller { fun canInstall(): Boolean; fun openInstallSettings(); fun install(apk: File) }`.
  - `class PackageInstallerApkInstaller(context: Context) : ApkInstaller`.
    - It streams the APK into a `PackageInstaller` session, whose status receiver starts the confirmation intent on `STATUS_PENDING_USER_ACTION`.
    - `openInstallSettings` opens `ACTION_MANAGE_UNKNOWN_APP_SOURCES` for this package.

- [ ] **Step 1: Write the failing tests.**

```kotlin
// UpdateRuleTest, own = BuildIdentity(11800, "1.18.0", "abc1234", "2026-11-09T12:00:00Z")
@Test fun `a higher version code is offered`()                    // server 11801 → true
@Test fun `the same version from another commit is offered`()     // 11800, commit "def5678" → true
@Test fun `the same commit rebuilt later is offered`()            // 11800, same commit, built_at "2026-11-09T13:00:00Z" → true
@Test fun `the very same build is not offered`()                  // → false
@Test fun `a lower version code is never offered`()               // 11799, other commit → false
@Test fun `an image without the app offers nothing`()             // AppInfo(available = false) → false

// UpdateCheckerTest, with a fake clock and FakeSettingsStore
@Test fun `a check within six hours is skipped`()   // 2nd check() at +5 h makes no request and returns null
@Test fun `a forced check always asks`()            // check(force = true) at +1 min makes a request
@Test fun `the time of the check is saved`()
@Test fun `a server without app updates offers nothing`()   // /api/v1/app answers 404 → null, no exception

// ApkDownloaderTest
@Test fun `the file is kept when its hash matches`()   // progress ends at (n, n); file bytes equal
@Test fun `a damaged file is refused and deleted`()    // wrong sha256 → DamagedDownload; dir has no .apk and no .part
@Test fun `a cut in the middle leaves no file`()       // SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY → Unreachable; dir empty; a 2nd download then succeeds
```

- [ ] **Step 2: Run the tests to see them fail.** Run `cd android && ./gradlew testDebugUnitTest --tests "io.github.catchow0.d2n.update.*"`. Expected: compilation errors.

- [ ] **Step 3: Implement the files listed above** to the Interfaces block. `UpdateRule` follows the Global Constraints rule word for word.

- [ ] **Step 4: Run the tests to see them pass.** Expected: 13 tests passing. The installer is checked on the emulator in Task 9.

- [ ] **Step 5: Commit point.** `feat(android): find, download and install the server's newer app`.

---

### Task 7: The look, and getting in

**Files:**
- Create in `android/app/src/main/java/io/github/catchow0/d2n/`:
  - `D2nApplication.kt` and `AppGraph.kt` (the dependency container).
  - `ui/theme/Color.kt`, `ui/theme/Type.kt`, `ui/theme/Shape.kt`, `ui/theme/Theme.kt`.
  - `ui/components/Aurora.kt`, `GlassCard.kt`, `D2nButton.kt`, `Chip.kt`, `Banner.kt`, `Skeleton.kt`.
  - `ui/Navigation.kt`.
  - `ui/signin/ServerProbe.kt`, `ServerScreen.kt`, `ServerViewModel.kt`, `SignInScreen.kt`, `SignInViewModel.kt`, `SetupScreen.kt`, `SetupViewModel.kt`.
- Create: `res/font/unbounded.ttf` and `res/font/instrument_sans.ttf`, the variable fonts from the `google/fonts` repository (`ofl/unbounded/Unbounded[wght].ttf` and `ofl/instrumentsans/InstrumentSans[wdth,wght].ttf`, at a pinned commit). Their OFL licences go in `assets/licenses/`.
- Modify: `MainActivity.kt`, which now hosts `D2nTheme { Navigation(appGraph) }`, and `AndroidManifest.xml` (`android:name=".D2nApplication"`).
- Test in `android/app/src/test/java/io/github/catchow0/d2n/ui/signin/`: `ServerProbeTest.kt`, `ServerViewModelTest.kt`, `SignInViewModelTest.kt`.

**Interfaces:**
- **Consumes:** Task 4's `ServerAddress`, `ApiProvider`, `SettingsStore`, `apiCall` and `D2nApi`.
- **Theme values** come from `static/css/tokens.css`:
  - Colors: `Ink #07061a`, `Ink2 #0e0c26`, `Violet #8b5cf6`, `Magenta #e0479e`, `Cyan #22d3ee`, `Mint #5eead4`.
  - Surfaces: `Glass rgba(14,12,34,.58)`, `GlassStrong rgba(12,10,30,.82)`, `GlassRaised rgba(255,255,255,.05)`, `Line rgba(255,255,255,.09)`, `LineStrong rgba(255,255,255,.16)`.
  - Text and state colors: read `--text`, `--muted`, `--danger` and `--ok` in the same file.
  - Radii are 12, 16, 24 and 30, and a chip is round. Unbounded is the display font, Instrument Sans the body font.
- **Produces:**
  - `sealed interface ServerProbe { Required; Setup; Disabled; TooOld; NotThisServer(why); Unreachable(why) }`.
  - `suspend fun probeServer(client: OkHttpClient, base: HttpUrl): ServerProbe`.
    - It calls `GET <base>api/v1/auth/status` with redirects off.
    - **`TooOld`:** a JSON answer without `service`, such as `{"ok": false, "error": "Sign in first"}` from a version older than 1.17.0. This is the app's own server, before API v1.
    - **`NotThisServer`:** a 3xx, an answer that is not JSON (a login page), or JSON whose `service` is another app.
- **The ViewModels** take their dependencies as constructor parameters, and never a `Context`. Each exposes a `StateFlow` and the actions below.
  - **`ServerViewModel(probe: suspend (HttpUrl) -> ServerProbe, store: SettingsStore)`:**
    - Actions: `onInput(text)` and `submit()`.
    - State: the input, `cleartext`, `checking`, `error: String?`, and `next` (one of `SignIn`, `Setup`, `Main`).
  - **`SignInViewModel(api: () -> D2nApi, store: SettingsStore, defaultDevice: String, ticker: suspend (Long) -> Unit = { delay(it) })`:**
    - State: username, password, device, `busy`, `error`, `waitSeconds` (counting down to 0), and `next`.
    - It stores the token, and the device name the user typed.
  - **`SetupViewModel`** works the same way through `api.setup`.
- **Copy, exact** where the tests check it:
  - `HTTP_WARNING = "This address is not encrypted: your password and data travel in clear. Use it only on your local network or Tailscale."`
  - `NOT_THIS_SERVER = "This address does not answer as Deezer → Navidrome. If a login page (Authelia) protects it, let /api/v1/ through, as the README shows."`
  - `UNREACHABLE = "The server cannot be reached. Check the address and your connection."`
  - `TOO_OLD = "This server does not have the app's API yet. Update Deezer → Navidrome to 1.17.0 or later."`
  - `TOO_MANY = "Too many attempts. Try again in %d s."`
- **Navigation start:**
  - Until `ready`, a blank Ink screen.
  - No `serverUrl`: the Server screen. A `serverUrl` with no `token` and `authDisabled == false`: Sign-in. Otherwise: Main, a placeholder until Task 8.

- [ ] **Step 1: Write the failing tests.**

```kotlin
// ServerProbeTest (MockWebServer)
@Test fun `this app's status is recognised`()            // 200 {"service":"deezer-to-navidrome","api":1,"auth":"required"} → Required
@Test fun `a redirect elsewhere is a login page`()       // 302 Location https://auth.example/?rd=… → NotThisServer
@Test fun `an html answer is a login page`()             // 200 text/html → NotThisServer
@Test fun `another JSON service is not this app`()       // 200 {"service":"other"} → NotThisServer
@Test fun `an older server is told to update`()          // 401 {"ok":false,"error":"Sign in first"} → TooOld

// ServerViewModelTest (fake probe, FakeSettingsStore, MainDispatcherRule)
@Test fun `http shows the warning`()                      // onInput("http://10.0.2.2:8097") → cleartext == true
@Test fun `a login page in front is explained`()          // probe NotThisServer → error == NOT_THIS_SERVER
@Test fun `sign-in turned off goes straight in`()         // probe Disabled → store.serverUrl set, authDisabled true, token null, next == Main
@Test fun `a new server leads to account creation`()      // probe Setup → next == Setup

// SignInViewModelTest
@Test fun `signing in stores the token and the device name`()
@Test fun `too many attempts counts down then lets you try again`() // ApiError(429, retryAfter 30) → waitSeconds 30, submit disabled; advanceTimeBy(30_000) → 0
@Test fun `a server with no account leads to setup`()      // ApiError(409, "setup_needed") → next == Setup
```

- [ ] **Step 2: Run the tests to see them fail.** Run `cd android && ./gradlew testDebugUnitTest --tests "io.github.catchow0.d2n.ui.signin.*"`. Expected: compilation errors.

- [ ] **Step 3: Implement the theme, the components and the screens.**
  - **Aurora:** soft radial gradients (violet, magenta, cyan, mint) over Ink, static.
  - **GlassCard:** a translucent `Glass` surface with a 1 dp `Line` border and radius 24.
  - **Banner:** a tone (info, warn, error), a message, and an optional action.
  - **The screens** follow the web's sign-in page for layout. The device field defaults to `Build.MODEL`. Sign-in and Setup have a "Use another server" link back to the Server screen.
  - **`AppGraph`** builds the client with `TinkSecretBox` and a DataStore named `d2n`.
  - **No backdrop blur:** over the static, soft aurora, translucent glass looks the same as blurred glass. Leave the blur out, and note it for phase 9 in case the look needs it.

- [ ] **Step 4: Run the tests to see them pass.** Expected: 12 tests passing.

- [ ] **Step 5: Look at the screens.**
  - Start the emulator: `"$LOCALAPPDATA/Android/Sdk/emulator/emulator.exe" -avd Pixel_6 -no-snapshot-save -no-audio -no-boot-anim`.
  - Install `./gradlew installDebug`, then save `adb exec-out screencap -p` captures to `$SP/android6/` for each screen: the Server screen with `http://10.0.2.2:8097` (warning shown), Sign-in with a wrong password, and Setup.
  - Expected: the Ink background with the aurora, glass cards, the Unbounded titles, and no text cut off at 1080×2400.

- [ ] **Step 6: Commit point.** `feat(android): the look, and signing in to a server`.

---

### Task 8: Inside the app: profile, Activity, About, updates

**Files:**
- Create in `android/app/src/main/java/io/github/catchow0/d2n/ui/`:
  - `main/MainScaffold.kt`, `main/ProfilePicker.kt`, `main/SessionViewModel.kt`, `main/Reachability.kt`.
  - `activity/ActivityScreen.kt`, `activity/ActivityViewModel.kt`, `activity/TaskScreen.kt`, `activity/TaskViewModel.kt`.
  - `about/AboutScreen.kt`, `about/AboutViewModel.kt`.
  - `update/UpdateBanner.kt`, `update/UpdateViewModel.kt`.
- Modify: `AppGraph.kt` (it wires `onUnauthorized` to the session) and `ui/Navigation.kt` (it adds Main: Activity, Task/{id} and About).
- Test: `android/app/src/test/java/io/github/catchow0/d2n/ui/main/SessionViewModelTest.kt`, `main/ReachabilityTest.kt`, `activity/TaskViewModelTest.kt`, `update/UpdateViewModelTest.kt`.

**Interfaces:**
- **Consumes:** `D2nApi`, `SettingsStore` and `buildHttpClient(onUnauthorized)` (Task 4), `TaskFollower` (Task 5), `UpdateChecker`, `ApkDownloader` and `ApkInstaller` (Task 6), and `Banner` and `GlassCard` (Task 7).
- **Produces:**
  - **`SessionViewModel(api: () -> D2nApi, store: SettingsStore)`:**
    - State: `profiles`, `selected: Profile?`, `serverVersion`, and `signedOutMessage: String?`.
    - Actions: `refresh()`, `select(id)`, and `onUnauthorized()`. The last clears the token and sets `SIGNED_OUT = "This phone was signed out: sign in again."`
    - When the stored profile is not among the profiles, it switches to `info.profile` and stores that.
  - **`Reachability(probe: suspend () -> Boolean, scope: CoroutineScope, everyMillis: Long = 30_000)`:**
    - It exposes `online: StateFlow<Boolean>`.
    - `reportFailure()` turns it offline and starts checking every 30 s until the probe succeeds. `retryNow()` checks at once.
  - **`ActivityViewModel(api, reachability)`:** the tasks, newest first, and `refresh()`.
  - **`TaskViewModel(follower, api, base, taskId)`:**
    - State: the summary, the last 200 events, `ended`, and `notice: String?`.
    - `cancel()` turns a 409 `not_cancellable` into `notice = "This task cannot be stopped."`
  - **`AboutViewModel(api, store, own: BuildIdentity, checker)`:**
    - State: the app's version, commit and build time, plus the server and API versions.
    - Actions: `signOut()` (`POST /auth/logout`, then the token is cleared) and `checkNow()`.
  - **`UpdateViewModel(checker, downloader, installer, base, store)`:**
    - State: `offer: AppInfo?`, `progress`, `error`, and `needsPermission`.
    - Actions: `check()` (on start, and on each `ProcessLifecycleOwner` `ON_START`), `download()` and `install()`.

- [ ] **Step 1: Write the failing tests.**

```kotlin
// SessionViewModelTest (MockWebServer + FakeSettingsStore)
@Test fun `choosing a profile sends it with the next requests`()           // select("nd2") → next recorded request has X-Navidrome-Account nd2
@Test fun `a profile that no longer exists falls back to the default`()    // store profile "nd9", info profiles [nd1, nd2], profile "nd1" → selected nd1, store.profile == "nd1"
@Test fun `a 401 signs the app out`()                                      // /api/v1/info answers 401 → store.token == null, signedOutMessage == SIGNED_OUT

// ReachabilityTest (StandardTestDispatcher)
@Test fun `losing the server turns the banner on`()           // reportFailure() → online false
@Test fun `Retry brings it back`()                            // probe true; retryNow() → online true
@Test fun `while offline it checks every 30 seconds`()        // probe false twice then true; advanceTimeBy(60_000) → 3 probes, online true

// TaskViewModelTest (fake follower flow)
@Test fun `events pile up and the end is shown`()
@Test fun `a task that cannot be stopped says so`()           // cancelTask → ApiError(409, "not_cancellable") → notice "This task cannot be stopped."

// UpdateViewModelTest (fakes)
@Test fun `an offer shows the banner and a download installs it`()   // checker offers 11801 → offer set; download() then install() calls installer.install(file)
@Test fun `without permission it asks for it first`()                // installer.canInstall() false → needsPermission true; install not called
```

- [ ] **Step 2: Run the tests to see them fail.** Run `cd android && ./gradlew testDebugUnitTest --tests "io.github.catchow0.d2n.ui.*"`. Expected: compilation errors in the new tests.

- [ ] **Step 3: Implement the screens and ViewModels.**
  - **The top bar:** the "Deezer → Navidrome" title and the profile picker, a dropdown of the profiles' labels. The default profile is marked.
  - **Under the top bar:** the unreachable banner, `Banner(warn, "Can't reach the server.", action "Retry")`, then the update banner, `"Version %s is ready." / "Update"`.
  - **Two destinations** until phase 7: Activity, which is home, and More, which leads to About.
  - **Activity:** a skeleton list while loading, pull to refresh, task cards showing title, stage or message, progress, and state. A tap opens the task.
  - **The task screen:** the events live, and Cancel when the task can be stopped.
  - **A 401 anywhere** goes back to Sign-in, with `SIGNED_OUT` shown.

- [ ] **Step 4: Run all the Android tests.** Run `cd android && ./gradlew testDebugUnitTest`. Expected: every test of Tasks 4 to 8 passes.

- [ ] **Step 5: Commit point.** `feat(android): profiles, Activity, About and updates`.

---

### Task 9: End to end, and the documentation

**Files:**
- Create: `templates/help/android-app.html` and `android/README.md`, which covers building on the PC with the local SDK, `gradlew` and its tests, the emulator, and the release key.
- Modify:
  - `core/content.py`: add `("android-app", "Android app")` after `("sign-in", …)` in `HELP_SECTIONS`.
  - `templates/notes/1.18.0.html`.
  - `README.md`, with a new "📱 Android app" section after "API v1" covering: installing from Settings; the Authelia rule; updates; the key, its backup and its restoration; building on the PC; the Jenkins credentials and agent needs.
  - `templates/help/settings.html`: one line about the Android app block.

- [ ] **Step 1: The help section.**
  - `templates/help/android-app.html` follows `templates/help/sign-in.html`'s markup and covers four things:
    - installing (Settings → Android app, and allowing installs from the browser);
    - signing in (the address, the device name, and `http://` only on a local network or Tailscale);
    - Authelia (let `^/api/v1/` through);
    - updates (the banner, and allowing installs from D2N).
  - Run `"$SP/venv/Scripts/python" -m unittest tests.test_api_v1_resources tests.test_new_and_help`. Expected: OK. The help test compares against `HELP_SECTIONS`, so it now expects 13 sections.

- [ ] **Step 2: A local server for the emulator.** Follow `$SP/api5b_run.py`: a fresh `DATA_DIR` in the scratchpad, `D2N_SCHEDULER=off`, `APP_USERNAME`, `APP_PASSWORD`, and the scratchpad's `serve4.py` on `127.0.0.1:8097`, which the emulator reaches at `http://10.0.2.2:8097`. Create a second profile through `POST /api/v1/navidrome/accounts`.

- [ ] **Step 3: The first install.**
  - `powershell -File android/scripts/build-apk.ps1 -KeyDir "$SP/testkey"`, then `adb install dist/android/deezer-to-navidrome.apk`.
  - Walk through it on the emulator, saving a capture at each step to `$SP/android6/`:
    1. The address `http://10.0.2.2:8097` (warning shown).
    2. Sign-in (the device then appears in web Settings → Devices).
    3. Switch profile (the next request carries `X-Navidrome-Account`, in the server log).
    4. Start `POST /api/v1/library/refresh`, and watch it live in Activity.
    5. Cancel a scan of a Deezer playlist added with `POST /api/v1/playlists`.
    6. Stop the server: the banner shows. Start it again and tap Retry: it disappears.
    7. Revoke the device from web Settings: the app returns to Sign-in with `SIGNED_OUT`.

- [ ] **Step 4: Updates over the previous build.**
  - **Same version:** run `build-apk.ps1` again, which gives a new `built_at`.
    - Expected: the app shows "Version 1.18.0 is ready." Update downloads it, Android's installer asks to allow installs from D2N, then Update.
    - Accept with `adb shell input tap`, or the REA `capture_adb_screen` and `start_adb_activity` tools.
    - The app reopens still signed in, with the same profile.
  - **Higher version:** `D2N_VERSION=1.18.1` with `bash android/scripts/build-apk.sh` and the two variables. Expected: the update is offered and installs, and `aapt2 dump badging` shows `versionCode='11801'`.
  - **Signature:** `apksigner verify --print-certs` shows the same certificate on all three builds.
  - **Clean up:** remove the 1.18.1 APK, so it never stays in `dist/`.

- [ ] **Step 5: The documentation and the notes.**
  - **`templates/notes/1.18.0.html`**, in the style of `templates/notes/1.17.0.html`:
    - the app (sign-in, profiles, Activity live, updates from the server);
    - Settings → Android app;
    - "After the update": allowing installs from the browser, and the Authelia rule when it is not in place yet.
  - **The README section and `android/README.md`**, as listed under Files.

- [ ] **Step 6: Final checks.**
  - The whole Python suite: `"$SP/venv/Scripts/python" -m unittest discover -s tests -t .`, all OK.
  - The Android tests: `cd android && ./gradlew testDebugUnitTest`, all pass. They also passed inside the Docker build of Step 4.
  - `git status --short`: no key, no `dist/`, nothing under `android/**/build`.
  - Nothing was written on `S:`.

- [ ] **Step 7: Report to the owner, in French.**
  - The captures, what was checked, and what stays for them:
    - create the real key in a PowerShell window of their own, and back it up;
    - add the two Jenkins credentials;
    - approve the commits, the push of the branch, and the DEV push. The DEV image is built with the real key through `build-apk.ps1`, then `docker build -t catchow/deezer-to-navidrome:DEV .`.
  - Ask which of these to do, with AskUserQuestion.

- [ ] **Step 8: Commit point.** `docs(android): install, update and build the app; help and notes for 1.18.0`.
