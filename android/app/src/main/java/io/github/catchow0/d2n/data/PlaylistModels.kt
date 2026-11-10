package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// The profile's playlists (GET /api/v1/playlists) and what a playlist holds.

@Serializable
data class PlaylistAutomation(
    val scan: Boolean = false,
    @SerialName("interval_minutes") val intervalMinutes: Int = 60,
    val download: Boolean = false,
)

/** How far the last scan got; null before the first one. */
@Serializable
data class TrackCounts(
    val total: Int = 0,
    val matched: Int? = null,
    val unmatched: Int? = null,
    val unchecked: Int? = null,
)

/** A playlist of the dashboard. [kind] is "" for Deezer, "xp" when imported
 * from Spotify or a CSV, "mix" for a Deezer mix, "auto" for Made for you. */
@Serializable
data class PlaylistTile(
    val id: FlexibleId,
    val title: String = "",
    @SerialName("deezer_title") val deezerTitle: String = "",
    val kind: String = "",
    val source: String = "",
    val subtitle: String = "",
    val cover: String = "",
    val accounts: List<String> = emptyList(),
    val automation: PlaylistAutomation = PlaylistAutomation(),
    val tracks: TrackCounts? = null,
)

/** A playlist its user made by hand in Navidrome: shown, never changed. */
@Serializable
data class NavidromePlaylistTile(
    val account: String = "",
    val id: FlexibleId,
    val name: String = "",
    @SerialName("song_count") val songCount: Int = 0,
    val duration: Int = 0,
    val cover: String = "",
)

@Serializable
data class PlaylistsAnswer(
    val profile: String? = null,
    val playlists: List<PlaylistTile> = emptyList(),
    val navidrome: List<NavidromePlaylistTile> = emptyList(),
)

@Serializable
data class AddPlaylistAnswer(
    val id: FlexibleId = "",
    val added: Boolean = false,
    val message: String = "",
    @SerialName("task_id") val taskId: String? = null,
)

@Serializable
data class ImportAnswer(
    val id: FlexibleId = "",
    val message: String = "",
    @SerialName("task_id") val taskId: String? = null,
)

@Serializable
data class DeleteAnswer(
    val deleted: Boolean = false,
    val complete: Boolean = true,
    val message: String = "",
)

/** An answer that started a task. */
@Serializable
data class TaskStarted(@SerialName("task_id") val taskId: String? = null)

/** An imported track: what the other platform calls it, and its Deezer pick. */
@Serializable
data class SourceTrack(
    val key: String = "",
    val status: String = "pending",
    @SerialName("on_deezer") val onDeezer: Boolean = false,
    @SerialName("source_title") val sourceTitle: String = "",
    @SerialName("source_artist") val sourceArtist: String = "",
    @SerialName("source_duration") val sourceDuration: Int? = null,
)

@Serializable
data class PlaylistRow(
    val number: Int = 0,
    @SerialName("track_id") val trackId: FlexibleId? = null,
    @SerialName("deezer_name") val deezerName: String = "",
    @SerialName("deezer_artist") val deezerArtist: String = "",
    @SerialName("deezer_title") val deezerTitle: String = "",
    @SerialName("deezer_album") val deezerAlbum: String = "",
    val matched: Boolean? = null,
    @SerialName("source_name") val sourceName: String = "",
    val manual: Boolean = false,
    val downloaded: Boolean = false,
    @SerialName("local_path") val localPath: String? = null,
    val xp: SourceTrack? = null,
)

/** An imported playlist: where it comes from and how much was found on Deezer. */
@Serializable
data class SourceSummary(
    val source: String? = null,
    @SerialName("source_name") val sourceName: String = "",
    @SerialName("source_url") val sourceUrl: String = "",
    val truncated: Boolean = false,
    val total: Int = 0,
    @SerialName("on_deezer") val onDeezer: Int = 0,
    val review: Int = 0,
    @SerialName("not_found") val notFound: Int = 0,
    val pending: Int = 0,
)

@Serializable
data class PlaylistPreview(
    @SerialName("playlist_id") val playlistId: FlexibleId = "",
    @SerialName("playlist_title") val playlistTitle: String = "",
    val rows: List<PlaylistRow> = emptyList(),
    @SerialName("matched_count") val matchedCount: Int = 0,
    @SerialName("unmatched_count") val unmatchedCount: Int = 0,
    @SerialName("unchecked_count") val uncheckedCount: Int = 0,
    val xp: SourceSummary? = null,
)

@Serializable
data class Publication(
    @SerialName("song_count") val songCount: Int = 0,
    val missing: Int = 0,
    val hidden: Int = 0,
    @SerialName("published_at") val publishedAt: Double? = null,
    @SerialName("tried_at") val triedAt: Double? = null,
    val error: String? = null,
    @SerialName("custom_title") val customTitle: String? = null,
    @SerialName("in_navidrome") val inNavidrome: Boolean = false,
)

/** One Navidrome account, and the playlist there. [mode] is "api" or "m3u8". */
@Serializable
data class PublishedIn(
    val id: String,
    val label: String = "",
    val member: Boolean = false,
    val mode: String = "api",
    val complete: Boolean = false,
    val publication: Publication? = null,
)

@Serializable
data class NavidromeStatus(val accounts: List<PublishedIn> = emptyList())

@Serializable
data class PlaylistTracksAnswer(
    val playlist: PlaylistPreview = PlaylistPreview(),
    val navidrome: NavidromeStatus? = null,
)

@Serializable
data class NavidromeAnswer(val navidrome: NavidromeStatus = NavidromeStatus())

@Serializable
data class RowAnswer(val row: PlaylistRow, val xp: SourceSummary? = null)

@Serializable
data class AutomationAnswer(
    @SerialName("next_run_at") val nextRunAt: Double? = null,
    @SerialName("last_run_at") val lastRunAt: Double? = null,
)

@Serializable
data class NavidromeTrack(
    val title: String = "",
    val artist: String = "",
    val album: String = "",
    val duration: Int = 0,
)

@Serializable
data class NavidromePlaylist(
    val id: FlexibleId = "",
    val name: String = "",
    val owner: String = "",
    val comment: String = "",
    @SerialName("song_count") val songCount: Int = 0,
    val duration: Int = 0,
    val tracks: List<NavidromeTrack> = emptyList(),
)

@Serializable
data class NavidromePlaylistAnswer(val playlist: NavidromePlaylist = NavidromePlaylist())

/** A Navidrome account, as Settings and a playlist's accounts show it: never its secret. */
@Serializable
data class NavidromeAccount(
    val id: String,
    val label: String = "",
    val url: String = "",
    val username: String = "",
    @SerialName("publish_mode") val publishMode: String = "api",
    @SerialName("is_default") val isDefault: Boolean = false,
    val complete: Boolean = false,
)

@Serializable
data class NavidromeAccountsAnswer(
    val accounts: List<NavidromeAccount> = emptyList(),
    val default: String? = null,
)
