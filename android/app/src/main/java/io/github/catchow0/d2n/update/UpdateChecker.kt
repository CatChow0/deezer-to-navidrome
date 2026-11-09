package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.AppInfo
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.apiCall

/**
 * Asks the server about the app it ships, at most every [minIntervalMillis]
 * unless forced. Returns the APK to offer, or null. A failure to reach the
 * server is thrown (a forced check shows it) and does not count as a check.
 */
class UpdateChecker(
    private val api: () -> D2nApi?,
    private val store: SettingsStore,
    private val own: BuildIdentity,
    private val now: () -> Long,
    private val minIntervalMillis: Long = 6 * 3_600_000L,
) {
    suspend fun check(force: Boolean = false): AppInfo? {
        val service = api() ?: return null
        val at = now()
        if (!force && at - store.state.value.lastUpdateCheck < minIntervalMillis) return null
        val info = try {
            apiCall { service.app() }
        } catch (e: ApiError) {
            // A server older than 1.18.0 has no /api/v1/app: nothing to offer.
            if (e.status != 404) throw e
            store.setLastUpdateCheck(at)
            return null
        }
        store.setLastUpdateCheck(at)
        return info.takeIf { UpdateRule.shouldOffer(own, it) }
    }
}
