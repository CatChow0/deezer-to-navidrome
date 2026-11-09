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

// Phase 7: playlists.
@Serializable
data class PlaylistTile(
    val id: String,
    val title: String = "",
    @SerialName("deezer_title") val deezerTitle: String = "",
    val kind: String = "",
    val source: String = "",
    val subtitle: String = "",
    val cover: String = "",
    val accounts: List<String> = emptyList(),
    val automation: PlaylistAutomation = PlaylistAutomation(),
)

@Serializable
data class PlaylistAutomation(
    val scan: Boolean = false,
    @SerialName("interval_minutes") val intervalMinutes: Int = 60,
    val download: Boolean = false,
)

@Serializable
data class PlaylistListResponse(
    val profile: String? = null,
    val playlists: List<PlaylistTile> = emptyList(),
    val navidrome: List<PlaylistTile> = emptyList(),
)

@Serializable
data class LinkBody(val link: String)

@Serializable
data class PlaylistAddResponse(
    val added: Boolean = false,
    val playlist: PlaylistTile? = null,
)

@Serializable
data class PlaylistImportResponse(
    val id: String = "",
    @SerialName("task_id") val taskId: String? = null,
    val message: String? = null,
)

@Serializable
data class TaskStartResponse(
    @SerialName("task_id") val taskId: String? = null,
    val total: Int? = null,
)

@Serializable
data class PlaylistRow(
    val number: Int = 0,
    @SerialName("track_id") val trackId: String? = null,
    @SerialName("deezer_name") val deezerName: String = "",
    @SerialName("deezer_artist") val deezerArtist: String = "",
    @SerialName("deezer_title") val deezerTitle: String = "",
    @SerialName("deezer_album") val deezerAlbum: String = "",
    val matched: Boolean? = null,
    @SerialName("source_name") val sourceName: String = "",
    val manual: Boolean = false,
    val downloaded: Boolean = false,
    @SerialName("local_path") val localPath: String? = null,
)

@Serializable
data class PlaylistPreview(
    @SerialName("playlist_id") val playlistId: String = "",
    @SerialName("playlist_title") val playlistTitle: String = "",
    val rows: List<PlaylistRow> = emptyList(),
    @SerialName("matched_count") val matchedCount: Int? = null,
    @SerialName("unmatched_count") val unmatchedCount: Int? = null,
    @SerialName("unchecked_count") val uncheckedCount: Int? = null,
)

@Serializable
data class PlaylistTracksResponse(
    val ok: Boolean = true,
    val playlist: PlaylistPreview? = null,
)

@Serializable
data class MixTrack(
    val id: String = "",
    val artist: String = "",
    val title: String = "",
    val album: String = "",
    val plays: Int = 0,
    val reason: String = "",
    val source: String = "",
    val cover: String? = null,
    @SerialName("days_left") val daysLeft: Int = 0,
    @SerialName("trash_days_left") val trashDaysLeft: Int = 0,
)

@Serializable
data class MixesResponse(
    @SerialName("on_trial") val onTrial: List<MixTrack> = emptyList(),
    val pending: List<MixTrack> = emptyList(),
    val trash: List<MixTrack> = emptyList(),
)

// Phase 7: helpers for made-for-you (deferred data models).

@Serializable
data class ApiErrorBody(val error: ApiErrorDetail)

// Phase 7: Deezer search.

@Serializable
data class SearchResult(
    val id: String,
    val type: String = "track",
    val title: String = "",
    val subtitle: String? = null,
    val artist: String? = null,
    val album: String? = null,
    val duration: Int? = null,
    val explicit: Boolean? = null,
    val cover: String? = null,
    @SerialName("track_count") val trackCount: Int? = null,
    @SerialName("nb_album") val nbAlbum: Int? = null,
    @SerialName("download_type") val downloadType: String? = null,
    @SerialName("download_id") val downloadId: String? = null,
)

@Serializable
data class SearchResponse(val results: List<SearchResult> = emptyList())

@Serializable
data class SearchAlbumTrack(
    val id: String = "",
    val title: String = "",
    val duration: Int? = null,
    val artist: String? = null,
    val preview: String? = null,
)

@Serializable
data class SearchAlbum(
    val id: String = "",
    val title: String = "",
    val artist: String? = null,
    val cover: String? = null,
    val tracks: List<SearchAlbumTrack> = emptyList(),
)

@Serializable
data class SearchAlbumResponse(val album: SearchAlbum? = null)

@Serializable
data class SearchArtist(val id: String = "", val title: String = "", val cover: String? = null)
@Serializable
data class SearchArtistResponse(val artist: SearchArtist? = null)

@Serializable
data class Preview(
    val id: String,
    val title: String = "",
    val artist: String = "",
    val album: String = "",
    val cover: String = "",
    val preview: String = "",
    val gain: Int = 0,
    val link: String = "",
)

// Phase 7: library check.

@Serializable
data class LibraryCheckItem(
    val key: String,
    val type: String,
    val id: String = "",
    val title: String = "",
    val artist: String = "",
    val album: String = "",
    val duration: Int? = null,
)

@Serializable
data class LibraryCheckResult(
    val owned: Boolean? = null,
    @SerialName("owned_count") val ownedCount: Int? = null,
    val total: Int? = null,
    @SerialName("albums_owned") val albumsOwned: Int? = null,
    @SerialName("tracks_owned") val tracksOwned: Int? = null,
)

@Serializable
data class LibraryCheckRequest(val items: List<LibraryCheckItem> = emptyList())

@Serializable
data class LibraryCheckResponse(val results: Map<String, LibraryCheckResult> = emptyMap())
