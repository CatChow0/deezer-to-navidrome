package io.github.catchow0.d2n.ui.signin

import io.github.catchow0.d2n.data.D2nJson
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request

/** What an address answers to /api/v1/auth/status. */
sealed interface ServerProbe {
    /** This app, asking for a sign-in. */
    data object Required : ServerProbe

    /** This app, without an account yet. */
    data object Setup : ServerProbe

    /** This app, with sign-in turned off (DISABLE_AUTH). */
    data object Disabled : ServerProbe

    /** This app before API v1 (1.16.0 or older). */
    data object TooOld : ServerProbe

    /** Something else: a login page in front of it (Authelia), or another service. */
    data class NotThisServer(val why: String) : ServerProbe

    data class Unreachable(val why: String) : ServerProbe
}

/**
 * Asks the address what it is, without following redirects: a login proxy
 * answers with one. [client] must not carry the token of another server, so
 * the app probes with a client of its own.
 */
suspend fun probeServer(client: OkHttpClient, base: HttpUrl): ServerProbe = withContext(Dispatchers.IO) {
    val plain = client.newBuilder().followRedirects(false).followSslRedirects(false).build()
    val request = Request.Builder().url(base.resolve("api/v1/auth/status")!!).header("Accept", "application/json").build()
    try {
        plain.newCall(request).execute().use { response ->
            if (response.isRedirect) return@use ServerProbe.NotThisServer("redirected to ${response.header("Location")}")
            val type = response.body.contentType()
            val text = response.body.string()
            val json = if (type?.subtype == "json") runCatching { D2nJson.parseToJsonElement(text) as? JsonObject }.getOrNull() else null
            val service = json?.get("service")?.jsonPrimitive?.contentOrNull
            when {
                json == null -> ServerProbe.NotThisServer("not JSON (${type ?: "no type"})")
                // The app's own answer, from before API v1: {"ok": false, "error": "Sign in first"}.
                service == null -> ServerProbe.TooOld
                service != "deezer-to-navidrome" -> ServerProbe.NotThisServer("another service: $service")
                else -> when (json["auth"]?.jsonPrimitive?.contentOrNull) {
                    "setup" -> ServerProbe.Setup
                    "disabled" -> ServerProbe.Disabled
                    else -> ServerProbe.Required
                }
            }
        }
    } catch (e: IOException) {
        ServerProbe.Unreachable(e.message ?: e.javaClass.simpleName)
    }
}
