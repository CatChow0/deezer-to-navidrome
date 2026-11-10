package io.github.catchow0.d2n.ui.share

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request

private val URL = Regex("""https?://[^\s"'<>]+""")

/** Deezer's share button gives a short link that redirects to the playlist. */
private val SHORT_HOSTS = setOf("link.deezer.com", "deezer.page.link", "dzr.page.link")

/** The first link in what another app shared ("Listen to … on Deezer: https://…"), or the text itself. */
fun linkIn(shared: String): String = URL.find(shared)?.value?.trimEnd('.', ',', ')') ?: shared.trim()

/**
 * The link to send to the server. A Deezer short link is followed to the
 * playlist it opens, with a client that never carries the app's token.
 */
suspend fun resolveShared(shared: String, bare: OkHttpClient): String {
    val link = linkIn(shared)
    val url = link.toHttpUrlOrNull() ?: return link
    if (url.host !in SHORT_HOSTS) return link
    return withContext(Dispatchers.IO) {
        try {
            bare.newCall(Request.Builder().url(url).get().build()).execute().use { it.request.url.toString() }
        } catch (e: Exception) {
            link
        }
    }
}
