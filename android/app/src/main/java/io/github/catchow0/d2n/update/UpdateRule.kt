package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.AppInfo

object UpdateRule {
    /**
     * The server's APK is offered when its versionCode is higher, or equal with
     * another build (another commit, or the same one built again: successive
     * DEV builds of one version). Never a lower one: Android refuses it.
     */
    fun shouldOffer(own: BuildIdentity, server: AppInfo): Boolean {
        val code = server.versionCode ?: return false
        if (!server.available) return false
        if (code > own.versionCode) return true
        val build = server.build ?: return false
        return code == own.versionCode && (build.commit != own.commit || build.builtAt != own.builtAt)
    }
}
