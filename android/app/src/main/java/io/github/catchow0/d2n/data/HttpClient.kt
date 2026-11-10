package io.github.catchow0.d2n.data

import java.io.File
import java.util.concurrent.TimeUnit
import okhttp3.Cache
import okhttp3.HttpUrl
import okhttp3.OkHttpClient

/** What every request to the server carries: the device's token and the
 * chosen profile. [server] is where they go: a cover or a preview from Deezer's
 * CDN never gets them. Null sends them everywhere (the tests' one server). */
data class RequestHeaders(val token: String?, val profile: String?, val server: HttpUrl? = null)

/** Whether [url] is on the app's server: same scheme, host and port. */
internal fun RequestHeaders.isForServer(url: HttpUrl): Boolean =
    server == null || (url.scheme == server.scheme && url.host == server.host && url.port == server.port)

private const val CACHE_BYTES = 20L * 1024 * 1024

/** An APK download and a task's event stream are unsuitable for the HTTP
 * cache: caching the installer would hand an older build back, and caching
 * an event stream would freeze the task on its old events. */
internal fun cacheFreePath(path: String): Boolean =
    path.endsWith("api/v1/app/apk") ||
        path.contains("/api/v1/tasks/") && path.contains("/events")
private val SIGN_IN_PATHS = listOf("api/v1/auth/login", "api/v1/auth/setup")

/**
 * The one client of the app. Reads keep the server's ETag in the cache, so an
 * unchanged answer comes back as a 304. A 401 outside sign-in means the token
 * was revoked (signed out from the web, a new password): [onUnauthorized]
 * runs, and the app goes back to its sign-in screen.
 */
fun buildHttpClient(
    cacheDir: File?,
    headers: () -> RequestHeaders,
    userAgent: String,
    onUnauthorized: () -> Unit = {},
): OkHttpClient = OkHttpClient.Builder()
    .apply { if (cacheDir != null) cache(Cache(File(cacheDir, "http"), CACHE_BYTES)) }
    .connectTimeout(10, TimeUnit.SECONDS)
    // A task's events can be waited for 25 s on the server.
    .readTimeout(35, TimeUnit.SECONDS)
    .addInterceptor { chain ->
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
        val response = chain.proceed(request)
        if (ours && response.code == 401 && SIGN_IN_PATHS.none { request.url.encodedPath.endsWith(it) }) onUnauthorized()
        response
    }
    .build()
