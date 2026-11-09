package io.github.catchow0.d2n.data

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

object ServerAddress {
    private val SCHEME = Regex("^[a-zA-Z][a-zA-Z0-9+.-]*://")
    private val PORT = Regex("^[^/]+:[0-9]+")

    /**
     * The address typed by the user, as the base of every call: https:// when
     * no scheme is given, the host in lower case, any sub-path kept, and a
     * trailing slash. Null for anything that cannot be a server. A short local
     * name (a NAS, a Tailscale machine) needs its scheme or its port, so that a
     * stray word is not taken for an address.
     */
    fun normalize(input: String): HttpUrl? {
        val text = input.trim()
        if (text.isEmpty() || text.any(Char::isWhitespace)) return null
        val explicit = SCHEME.containsMatchIn(text)
        val url = (if (explicit) text else "https://$text").toHttpUrlOrNull() ?: return null
        val host = url.host
        val named = host == "localhost" || '.' in host || ':' in host
        if (!named && !explicit && !PORT.containsMatchIn(text)) return null
        val path = if (url.encodedPath.endsWith("/")) url.encodedPath else url.encodedPath + "/"
        return url.newBuilder().encodedPath(path).query(null).fragment(null).build()
    }
}

/** Not encrypted: only for a local network or Tailscale, and the app says so. */
val HttpUrl.isCleartext: Boolean get() = scheme == "http"
