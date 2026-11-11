package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.AppInfo

object UpdateRule {
    /**
     * The server's APK is offered when its versionCode is higher, or equal with
     * a newer build (successive DEV builds of one version). Never a lower one,
     * nor an older build of the same version: a server rolled back, or someone
     * between the phone and the server, would otherwise take the app back.
     * Both times are ISO 8601 in UTC, so they compare as text.
     */
    fun shouldOffer(own: BuildIdentity, server: AppInfo): Boolean {
        val code = server.versionCode ?: return false
        if (!server.available) return false
        if (code > own.versionCode) return true
        val build = server.build ?: return false
        return code == own.versionCode && build.builtAt.isNotEmpty() && build.builtAt > own.builtAt
    }
}
