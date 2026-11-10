// The plugins' versions; app/ applies them. AGP 9 compiles Kotlin itself: no
// kotlin-android plugin. The Compose and serialization plugins bring the
// Kotlin version of the version catalog.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.android.test) apply false
    alias(libs.plugins.baselineprofile) apply false
}
