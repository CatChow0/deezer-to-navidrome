package io.github.catchow0.d2n.data

import okhttp3.HttpUrl

/**
 * A picture or a sound the server links to. The answers give its own media
 * as "/api/v1/covers/…": it is read under the app's server address, sub-path
 * included. A Deezer CDN link stays as it is.
 */
fun HttpUrl.media(link: String?): String? {
    val value = link?.trim().orEmpty()
    if (value.isEmpty()) return null
    if (value.startsWith("http://") || value.startsWith("https://")) return value
    return resolve(value.removePrefix("/"))?.toString()
}
