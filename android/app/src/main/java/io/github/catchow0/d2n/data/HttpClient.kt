package io.github.catchow0.d2n.data

import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import okhttp3.Cache
import okhttp3.CacheControl
import okhttp3.HttpUrl
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response

/** What every request to the server carries: the device's token and the
 * chosen profile. [server] is where they go: a cover or a preview from Deezer's
 * CDN never gets them. Null sends them everywhere (the tests' one server). */
data class RequestHeaders(val token: String?, val profile: String?, val server: HttpUrl? = null)

/** Whether [url] is on the app's server: same scheme, host and port. */
internal fun RequestHeaders.isForServer(url: HttpUrl): Boolean =
    server == null || (url.scheme == server.scheme && url.host == server.host && url.port == server.port)

private const val CACHE_BYTES = 20L * 1024 * 1024

/** An APK download, a task's events and the answers holding a secret are
 * unsuitable for the HTTP cache: caching the installer would hand an older
 * build back, a cached stream would freeze the task on its old events (and
 * fill the cache, pushing out the saved screens), and the cache is a plain
 * file on the phone, where a token must never be written. */
internal fun cacheFreePath(path: String): Boolean =
    path.endsWith("api/v1/app/apk") ||
        path.contains("/api/v1/tasks/") && (path.contains("/events") || path.endsWith("/stream")) ||
        path.endsWith("api/v1/settings/security") || path.endsWith("api/v1/stats/status")
private val SIGN_IN_PATHS = listOf("api/v1/auth/login", "api/v1/auth/setup")

/**
 * Reads that must come from the server or fail: whether it answers (an old
 * copy would say it does) and the running tasks (an old copy would show a
 * task running forever).
 */
internal fun liveOnlyPath(path: String): Boolean =
    cacheFreePath(path) || path.endsWith("api/v1/auth/status") || path.contains("api/v1/tasks")

/** On an answer read from the cache because the server could not be reached. */
const val SAVED_ANSWER_HEADER = "X-D2N-Saved"

/**
 * The one client of the app. Reads keep the server's ETag in the cache, so an
 * unchanged answer comes back as a 304. A 401 outside sign-in means the token
 * was revoked (signed out from the web, a new password): [onUnauthorized]
 * runs, and the app goes back to its sign-in screen.
 *
 * When the server cannot be reached, a read it answered before comes back
 * from the cache, marked with [SAVED_ANSWER_HEADER], and [onSaved] runs (the
 * app's banner) with when the call started, in [System.nanoTime]. While [offline] says so, reads go to the cache first rather
 * than wait for the connection to time out on each screen. The server's
 * answers vary on the profile header, so the cache only hands back the same
 * profile's copy. Changes still fail.
 */
fun buildHttpClient(
    cacheDir: File?,
    headers: () -> RequestHeaders,
    userAgent: String,
    onSaved: (startedAt: Long) -> Unit = {},
    offline: () -> Boolean = { false },
    onUnauthorized: () -> Unit = {},
): OkHttpClient = OkHttpClient.Builder()
    .apply { if (cacheDir != null) cache(Cache(File(cacheDir, "http"), CACHE_BYTES)) }
    // A redirect from https to http would send the token, or a password, in
    // clear: the server is always reached at the address it was given.
    .followSslRedirects(false)
    .connectTimeout(10, TimeUnit.SECONDS)
    // A task's events can be waited for 25 s on the server.
    .readTimeout(35, TimeUnit.SECONDS)
    .addInterceptor { chain ->
        val started = System.nanoTime()
        val current = headers()
        val ours = current.isForServer(chain.request().url)
        val noStore = cacheFreePath(chain.request().url.encodedPath)
        val request = chain.request().newBuilder()
            .header("User-Agent", userAgent)
            .apply {
                if (ours) {
                    current.token?.let { header("Authorization", "Bearer $it") }
                    current.profile?.let { header("X-Navidrome-Account", it) }
                }
                if (noStore) header("Cache-Control", "no-store")
            }
            .build()
        val savable = request.method == "GET" && ours && !liveOnlyPath(request.url.encodedPath)
        if (savable && offline()) savedCopy(chain, request)?.let { return@addInterceptor it }
        val response = try {
            chain.proceed(request)
        } catch (e: IOException) {
            if (!savable) throw e
            val saved = savedCopy(chain, request) ?: throw e
            onSaved(started)
            saved
        }
        if (ours && response.code == 401 && SIGN_IN_PATHS.none { request.url.encodedPath.endsWith(it) }) onUnauthorized()
        response
    }
    .build()

/** The cache's copy of [request], or null when none was saved (OkHttp's 504). */
private fun savedCopy(chain: Interceptor.Chain, request: Request): Response? {
    val saved = chain.proceed(request.newBuilder().cacheControl(CacheControl.FORCE_CACHE).build())
    if (!saved.isSuccessful) {
        saved.close()
        return null
    }
    return saved.newBuilder().header(SAVED_ANSWER_HEADER, "1").build()
}
