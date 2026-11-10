package io.github.catchow0.d2n.data

import java.io.IOException
import kotlinx.serialization.SerializationException
import retrofit2.HttpException

/** What can go wrong with a call, as the screens tell it. */
sealed class ApiFailure(message: String, cause: Throwable? = null) : Exception(message, cause)

/** The server answered with {"error": {"code", "message"}}. */
class ApiError(val status: Int, val code: String, message: String, val retryAfterSeconds: Int?) : ApiFailure(message)

class Unreachable(cause: Throwable) : ApiFailure("The server cannot be reached.", cause)

/** An answer this app does not understand: a login page in front of the
 * server, another service, or a server too old. */
class NotThisServer(val detail: String) : ApiFailure(detail)

private val CODES = mapOf(
    400 to "invalid", 401 to "unauthorized", 403 to "forbidden", 404 to "not_found", 405 to "method_not_allowed",
    409 to "conflict", 413 to "too_large", 429 to "too_many_requests", 502 to "upstream_error", 503 to "unavailable",
)

/** Runs a call and turns what can go wrong into an [ApiFailure]. */
suspend fun <T> apiCall(block: suspend () -> T): T = try {
    block()
} catch (e: HttpException) {
    throw e.toApiError()
} catch (e: SerializationException) {
    throw NotThisServer("The server's answer is not what this app expects.")
} catch (e: IOException) {
    throw Unreachable(e)
}

private fun HttpException.toApiError(): ApiError {
    val status = code()
    val response = response()
    val fromHeader = response?.headers()?.get("Retry-After")?.trim()?.toIntOrNull()
    val detail = try {
        response?.errorBody()?.string()?.let { D2nJson.decodeFromString(ApiErrorBody.serializer(), it).error }
    } catch (e: Exception) {
        null
    }
    return ApiError(
        status = status,
        code = detail?.code ?: CODES[status] ?: if (status >= 500) "server_error" else "invalid",
        message = detail?.message ?: "The server answered $status.",
        retryAfterSeconds = detail?.retryAfter ?: fromHeader,
    )
}
