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

// Phase 7: Navidrome accounts, used to choose where a playlist is published.
@Serializable
data class NavidromeAccount(
    val id: String = "",
    val label: String = "",
    val url: String = "",
    val username: String = "",
    @SerialName("is_default") val isDefault: Boolean = false,
    val complete: Boolean = false,
)

@Serializable
data class NavidromeAccountsResponse(
    val ok: Boolean = true,
    val accounts: List<NavidromeAccount> = emptyList(),
    val default: String? = null,
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

// Phase 8: Releases.
@Serializable
data class ReleaseFollowedArtist(
    val id: String = "",
    val name: String = "",
    val picture: String = "",
    val releases: Int = 0,
)

@Serializable
data class ReleaseFollowed(
    val id: String = "",
    val name: String = "",
)

@Serializable
data class ReleaseItem(
    val id: String = "",
    val title: String = "",
    val cover: String = "",
    @SerialName("release_date") val releaseDate: String = "",
    @SerialName("record_type") val recordType: String = "",
    val explicit: Boolean = false,
    val artist: String = "",
    @SerialName("artist_id") val artistId: String = "",
    @SerialName("nb_tracks") val nbTracks: Int = 0,
    val featured: Boolean = false,
    val followed: List<ReleaseFollowed> = emptyList(),
)

@Serializable
data class DeezerAccountBrief(
    val id: String? = null,
    val label: String? = null,
    val name: String? = null,
)

@Serializable
data class ReleasesResponse(
    val connected: Boolean = false,
    @SerialName("deezer_account") val deezerAccount: DeezerAccountBrief? = null,
    @SerialName("refresh_hours") val refreshHours: Int = 0,
    val muted: Map<String, String> = emptyMap(),
    @SerialName("artists") val artists: Int = 0,
    @SerialName("failed_artists") val failedArtists: Int = 0,
    @SerialName("window_days") val windowDays: Int = 0,
    @SerialName("updated_at") val updatedAt: Long? = null,
    @SerialName("followed_artists") val followedArtists: List<ReleaseFollowedArtist> = emptyList(),
    val releases: List<ReleaseItem> = emptyList(),
)

@Serializable
data class MuteReleaseResponse(val muted: Map<String, String> = emptyMap())

// Phase 8: Deezer mixes.
@Serializable
data class DeezerMixItem(
    val kind: String = "",
    @SerialName("source_id") val sourceId: String = "",
    val title: String = "",
    val subtitle: String = "",
    val group: String = "",
    val followed: Boolean = false,
)

@Serializable
data class DeezerMixPlaylist(
    val id: String = "",
    val title: String = "",
    val subtitle: String = "",
    val picture: String = "",
    val group: String = "",
    val followed: Boolean = false,
)

@Serializable
data class DeezerMixesResponse(
    val mixes: List<DeezerMixItem> = emptyList(),
    val playlists: List<DeezerMixPlaylist> = emptyList(),
)

@Serializable
data class DeezerMixFollowResponse(
    @SerialName("id") val id: String = "",
    val added: Boolean = false,
)

// Phase 8: New and Help.
@Serializable
data class ContentNote(
    val version: String = "",
    val date: String = "",
    val title: String = "",
    val html: String = "",
    val unseen: Boolean? = null,
)

@Serializable
data class ContentNotesResponse(
    val notes: List<ContentNote> = emptyList(),
    val unseen: Boolean = false,
)

@Serializable
data class ContentHelpSection(
    val id: String = "",
    val title: String = "",
    val html: String = "",
)

@Serializable
data class ContentHelpResponse(
    val sections: List<ContentHelpSection> = emptyList(),
)

// Phase 8: Settings.
@Serializable
data class SettingsResponse(
    val settings: kotlinx.serialization.json.JsonObject = kotlinx.serialization.json.JsonObject(emptyMap()),
    @SerialName("downloads_folder") val downloadsFolder: kotlinx.serialization.json.JsonObject? = null,
    val choices: kotlinx.serialization.json.JsonObject? = null,
)

@Serializable
data class ClearSettingsResponse(
    val cleared: String = "",
    val message: String = "",
)

// Phase 8: Stats.
@Serializable
data class StatsTotals(
    val plays: Int = 0,
    val seconds: Double = 0.0,
    val artists: Int = 0,
    val albums: Int = 0,
    val tracks: Int = 0,
)

@Serializable
data class StatsCoverage(
    @SerialName("length_pct") val lengthPct: Int = 0,
    @SerialName("genre_pct") val genrePct: Int = 0,
)

@Serializable
data class StatsRankRow(
    val id: Int = 0,
    val name: String? = null,
    val title: String? = null,
    val artist: String? = null,
    val image: String? = null,
    val plays: Int = 0,
    @SerialName("deezer_track_id") val deezerTrackId: String? = null,
)

@Serializable
data class StatsTop(
    val artists: List<StatsRankRow> = emptyList(),
    val albums: List<StatsRankRow> = emptyList(),
    val tracks: List<StatsRankRow> = emptyList(),
)

@Serializable
data class StatsGenre(
    val name: String = "",
    val plays: Int = 0,
    val seconds: Double = 0.0,
    val share: Double = 0.0,
)

@Serializable
data class StatsBusiestDay(
    val date: String = "",
    val plays: Int = 0,
)

@Serializable
data class StatsLongestStreak(
    val days: Int = 0,
)

@Serializable
data class StatsHabits(
    val heatmap: List<List<Int>> = emptyList(),
    @SerialName("busiest_day") val busiestDay: StatsBusiestDay? = null,
    @SerialName("longest_streak") val longestStreak: StatsLongestStreak? = null,
)

@Serializable
data class StatsOverviewResponse(
    val period: String = "month",
    val key: String = "",
    val label: String = "",
    val totals: StatsTotals? = null,
    val coverage: StatsCoverage? = null,
    val top: StatsTop? = null,
    val genres: List<StatsGenre> = emptyList(),
    val habits: StatsHabits? = null,
)

@Serializable
data class StatsPlayRow(
    val id: Int? = null,
    @SerialName("listened_at") val listenedAt: Double = 0.0,
    val source: String? = null,
    @SerialName("track_id") val trackId: Int? = null,
    val title: String = "",
    val artist: String = "",
    val album: String? = null,
)

@Serializable
data class StatsPlaysResponse(
    val plays: List<StatsPlayRow> = emptyList(),
    val total: Int = 0,
    val page: Int = 1,
    val pages: Int = 1,
)

@Serializable
data class StatsRecapEntry(
    val key: String = "",
    val label: String = "",
    val plays: Int = 0,
    val partial: Boolean = false,
    @SerialName("so_far") val soFar: Boolean = false,
)

@Serializable
data class StatsRecapsResponse(
    val months: List<StatsRecapEntry> = emptyList(),
    val years: List<StatsRecapEntry> = emptyList(),
    @SerialName("latest_complete") val latestComplete: String? = null,
)