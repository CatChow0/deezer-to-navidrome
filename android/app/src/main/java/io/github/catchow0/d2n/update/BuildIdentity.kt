package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.BuildConfig

/** This build: its version, and the commit and time it was built at, which
 * tell two builds of one version apart. */
data class BuildIdentity(val versionCode: Int, val versionName: String, val commit: String, val builtAt: String) {
    companion object {
        fun current() = BuildIdentity(BuildConfig.VERSION_CODE, BuildConfig.VERSION_NAME, BuildConfig.D2N_COMMIT, BuildConfig.D2N_BUILT_AT)
    }
}
