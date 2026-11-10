package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// The release feed of the profile's Deezer account (GET /api/v1/releases).

@Serializable
data class ArtistRef(val id: FlexibleId = "", val name: String = "")

/** A recent release. [featured]: the followed artist is only a guest on it. */
@Serializable
data class Release(
    val id: FlexibleId,
    val title: String = "",
    val cover: String = "",
    @SerialName("release_date") val releaseDate: String = "",
    @SerialName("record_type") val recordType: String = "album",
    val explicit: Boolean = false,
    val artist: String = "",
    @SerialName("artist_id") val artistId: FlexibleId = "",
    @SerialName("nb_tracks") val nbTracks: Int = 0,
    val featured: Boolean = false,
    val followed: List<ArtistRef> = emptyList(),
)

@Serializable
data class FollowedArtist(
    val id: FlexibleId,
    val name: String = "",
    val picture: String = "",
    val releases: Int = 0,
)

@Serializable
data class DeezerAccountRef(val id: String? = null, val label: String = "", val name: String = "")

@Serializable
data class ReleasesAnswer(
    val connected: Boolean = false,
    @SerialName("deezer_account") val deezerAccount: DeezerAccountRef? = null,
    @SerialName("refresh_hours") val refreshHours: Int = 24,
    /** Artist ID to name. */
    val muted: Map<String, String> = emptyMap(),
    @SerialName("updated_at") val updatedAt: Double? = null,
    val artists: Int = 0,
    @SerialName("failed_artists") val failedArtists: Int = 0,
    @SerialName("window_days") val windowDays: Int = 0,
    @SerialName("followed_artists") val followedArtists: List<FollowedArtist> = emptyList(),
    val releases: List<Release> = emptyList(),
)

@Serializable
data class MuteRequest(
    @SerialName("artist_id") val artistId: String,
    val name: String,
    val muted: Boolean,
)

@Serializable
data class MutedAnswer(val muted: Map<String, String> = emptyMap())
