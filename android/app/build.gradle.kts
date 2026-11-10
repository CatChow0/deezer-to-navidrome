import java.time.Instant
import java.time.temporal.ChronoUnit

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// The app shares the server's version. The Docker build passes it, with the
// commit and the build time, as -Pd2n.* (its context is android/ alone);
// elsewhere they come from ../VERSION, git and the clock.
val d2nVersion: String = providers.gradleProperty("d2n.version").orNull
    ?: rootDir.resolve("../VERSION").readText().trim()

fun gitCommit(): String = try {
    val commit = providers.exec {
        commandLine("git", "rev-parse", "--short=7", "HEAD")
        isIgnoreExitValue = true
    }.standardOutput.asText.get().trim().ifEmpty { "dev" }
    val clean = try {
        providers.exec {
            commandLine("git", "diff", "--quiet", "HEAD")
            isIgnoreExitValue = true
        }.result.get().exitValue == 0
    } catch (e: Exception) {
        true
    }
    if (clean) commit else "$commit-dirty"
} catch (e: Exception) {
    "dev"
}

val d2nCommit: String = providers.gradleProperty("d2n.commit").orNull ?: gitCommit()
val d2nBuiltAt: String = providers.gradleProperty("d2n.builtAt").orNull
    ?: Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()

/** MAJOR×10000 + MINOR×100 + PATCH: 1.18.0 gives 11800. */
fun versionCodeOf(version: String): Int {
    val parts = Regex("""^(\d+)\.(\d+)\.(\d+)$""").matchEntire(version)?.groupValues?.drop(1)?.map(String::toInt)
    if (parts == null || parts[1] >= 100 || parts[2] >= 100) {
        throw GradleException("VERSION must look like 1.18.0, with MINOR and PATCH below 100")
    }
    return parts[0] * 10000 + parts[1] * 100 + parts[2]
}

val d2nVersionCode = versionCodeOf(d2nVersion)
val keystoreFile: String? = System.getenv("D2N_KEYSTORE_FILE")?.takeIf { it.isNotBlank() }

android {
    namespace = "io.github.catchow0.d2n"
    // Current AndroidX needs Android 17 to compile against; the target stays 36.
    compileSdk = 37
    buildToolsVersion = "36.1.0"

    defaultConfig {
        applicationId = "io.github.catchow0.d2n"
        minSdk = 26
        targetSdk = 36
        versionCode = d2nVersionCode
        versionName = d2nVersion
        buildConfigField("String", "D2N_COMMIT", "\"$d2nCommit\"")
        buildConfigField("String", "D2N_BUILT_AT", "\"$d2nBuiltAt\"")
    }

    // The release key never lives in the repository: the build scripts pass it.
    signingConfigs {
        if (keystoreFile != null) {
            create("release") {
                storeFile = file(keystoreFile)
                storePassword = System.getenv("D2N_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("D2N_KEY_ALIAS") ?: "d2n"
                keyPassword = System.getenv("D2N_KEY_PASSWORD") ?: System.getenv("D2N_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("release") {
            // R8 shrinks and optimizes the release. The libraries bring their own
            // rules (OkHttp, Retrofit, kotlinx.serialization, Navigation, Coil,
            // Media3); proguard-rules.pro holds only what the app adds.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (keystoreFile != null) signingConfig = signingConfigs.getByName("release")
        }
        getByName("debug") {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // android.util.Log and the like answer nothing in JVM tests instead of throwing.
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.foundation)
    implementation(libs.compose.material3)

    implementation(libs.okhttp)
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.tink.android)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    // Covers, and the 30-second previews: both through the app's OkHttp client.
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.datasource.okhttp)
    // Applies src/main/baseline-prof.txt on the phone: the APK is installed
    // from the server, not a store, so nothing else would.
    implementation(libs.androidx.profileinstaller)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}

// The baseline profile, generated on a PC by :baselineprofile (see android/README.md):
// ./gradlew :app:generateBaselineProfile with the API 31 emulator running. The result
// lands in src/main/baseline-prof.txt, which is versioned, so the Docker build (where
// :baselineprofile is absent) ships it without this plugin.
if (rootProject.findProject(":baselineprofile") != null) {
    apply(plugin = "androidx.baselineprofile")
    dependencies { "baselineProfile"(project(":baselineprofile")) }
    extensions.configure<androidx.baselineprofile.gradle.consumer.BaselineProfileConsumerExtension> {
        mergeIntoMain = true
        automaticGenerationDuringBuild = false
    }
    // Without the release key on this PC, the profiling build is signed with the debug key.
    if (keystoreFile == null) {
        android.buildTypes.configureEach {
            if (name.startsWith("nonMinified") || name.startsWith("benchmark")) signingConfig = android.signingConfigs.getByName("debug")
        }
    }
    val keepProfile = tasks.register("keepProfile") {
        description = "Moves the generated baseline profile to src/main/baseline-prof.txt."
        val generated = layout.projectDirectory.dir("src/main/generated/baselineProfiles")
        val kept = layout.projectDirectory.file("src/main/baseline-prof.txt")
        doLast {
            val from = generated.file("baseline-prof.txt").asFile
            if (!from.isFile) throw GradleException("No profile at $from")
            from.copyTo(kept.asFile, overwrite = true)
            generated.asFile.parentFile.deleteRecursively()
        }
    }
    tasks.matching { it.name == "generateBaselineProfile" }.configureEach { finalizedBy(keepProfile) }
}

// A release build without the key fails here, clearly, instead of producing
// an unsigned APK.
tasks.matching { it.name == "preReleaseBuild" }.configureEach {
    doFirst {
        if (System.getenv("D2N_KEYSTORE_FILE").isNullOrBlank() || System.getenv("D2N_KEYSTORE_PASSWORD").isNullOrBlank()) {
            throw GradleException(
                "No signing key: set D2N_KEYSTORE_FILE and D2N_KEYSTORE_PASSWORD (android/scripts/build-apk.ps1 does it on the PC)"
            )
        }
    }
}

// What the server image ships: the signed APK and what it is.
tasks.register("packageD2n") {
    description = "Copies the signed release APK to build/d2n and writes app.json beside it."
    dependsOn("assembleRelease")
    val apk = layout.buildDirectory.file("outputs/apk/release/app-release.apk")
    val out = layout.buildDirectory.dir("d2n")
    val meta = """{"version":"$d2nVersion","version_code":$d2nVersionCode,"commit":"$d2nCommit","built_at":"$d2nBuiltAt"}"""
    outputs.dir(out)
    doLast {
        val dir = out.get().asFile
        dir.deleteRecursively()
        dir.mkdirs()
        apk.get().asFile.copyTo(dir.resolve("deezer-to-navidrome.apk"), overwrite = true)
        dir.resolve("app.json").writeText(meta + "\n")
    }
}
