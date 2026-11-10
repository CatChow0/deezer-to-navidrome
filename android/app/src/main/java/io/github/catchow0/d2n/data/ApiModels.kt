package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** The server may add fields: the app ignores what it does not know. */
val D2nJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
}

// The shapes of docs/api/openapi.yaml that phase 6 reads.

@Serializable
data class AuthStatus(val service: String = "", val api: Int = 0, val auth: String = "")

@Serializable
data class Credentials(val username: String, val password: String, val device: String)

@Serializable
data class DeviceInfo(val id: String, val name: String)

@Serializable
data class SignedIn(val token: String, val device: DeviceInfo, val username: String)

@Serializable
data class SignedOut(@SerialName("signed_out") val signedOut: Boolean = false)

@Serializable
data class Profile(val id: String, val label: String, @SerialName("is_default") val isDefault: Boolean = false)

@Serializable
data class ServerInfo(
    val version: String,
    val api: Int,
    val username: String? = null,
    @SerialName("auth_disabled") val authDisabled: Boolean = false,
    val profile: String? = null,
    val profiles: List<Profile> = emptyList(),
)

@Serializable
data class TaskSummary(
    val id: String,
    val title: String = "",
    val kind: String? = null,
    @SerialName("created_at") val createdAt: Double? = null,
    @SerialName("updated_at") val updatedAt: Double? = null,
    @SerialName("finished_at") val finishedAt: Double? = null,
    val done: Boolean = false,
    val error: Boolean = false,
    val stage: String? = null,
    val message: String? = null,
    val progress: Double? = null,
    val cancellable: Boolean = false,
    @SerialName("cancel_requested") val cancelRequested: Boolean = false,
    val cancelled: Boolean = false,
    val events: Int? = null,
)

@Serializable
data class TaskList(val tasks: List<TaskSummary> = emptyList())

@Serializable
data class TaskEnvelope(val task: TaskSummary)

@Serializable
data class TaskEvent(
    val index: Int = -1,
    val type: String = "status",
    val message: String? = null,
    val progress: Double? = null,
    val stage: String? = null,
    val done: Boolean = false,
    val error: Boolean = false,
    val cancelled: Boolean = false,
    val timestamp: Long? = null,
)

@Serializable
data class TaskEvents(val task: TaskSummary, val events: List<TaskEvent> = emptyList(), val after: Int = -1)

@Serializable
data class CancelAnswer(val cancelling: String = "")

@Serializable
data class AppBuild(val commit: String, @SerialName("built_at") val builtAt: String)

@Serializable
data class AppInfo(
    val available: Boolean,
    val version: String? = null,
    @SerialName("version_code") val versionCode: Int? = null,
    val build: AppBuild? = null,
    val size: Long? = null,
    val sha256: String? = null,
    val reason: String? = null,
)

@Serializable
data class ApiErrorDetail(val code: String, val message: String, @SerialName("retry_after") val retryAfter: Int? = null)

@Serializable
data class ApiErrorBody(val error: ApiErrorDetail)
