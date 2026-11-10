package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Deezer search, previews, downloads and the library.

/** A search result: a track, an album or an artist, by [type]. */
@Serializable
data class SearchResult(
    val id: FlexibleId,
    val type: String = "track",
    val title: String = "",
    val subtitle: String = "",
    val artist: String = "",
    val album: String = "",
    val duration: Int? = null,
    val explicit: Boolean = false,
    val cover: String = "",
    @SerialName("track_count") val trackCount: Int? = null,
    @SerialName("nb_album") val nbAlbum: Int? = null,
)

@Serializable
data class SearchAnswer(val results: List<SearchResult> = emptyList())

@Serializable
data class AlbumTrack(
    val position: Int = 0,
    @SerialName("track_id") val trackId: FlexibleId = "",
    val title: String = "",
    val artist: String = "",
    val duration: Int? = null,
    val explicit: Boolean = false,
)

@Serializable
data class DeezerAlbum(
    val id: FlexibleId = "",
    val title: String = "",
    val artist: String = "",
    val cover: String = "",
    @SerialName("track_count") val trackCount: Int = 0,
    val explicit: Boolean = false,
    val tracks: List<AlbumTrack> = emptyList(),
)

@Serializable
data class AlbumAnswer(val album: DeezerAlbum = DeezerAlbum())

@Serializable
data class ArtistAlbum(
    val id: FlexibleId = "",
    val title: String = "",
    val cover: String = "",
    @SerialName("release_date") val releaseDate: String = "",
    @SerialName("record_type") val recordType: String = "",
    val explicit: Boolean = false,
)

@Serializable
data class DeezerArtist(
    val id: FlexibleId = "",
    val name: String = "",
    val picture: String = "",
    @SerialName("nb_album") val nbAlbum: Int = 0,
    val albums: List<ArtistAlbum> = emptyList(),
)

@Serializable
data class ArtistAnswer(val artist: DeezerArtist = DeezerArtist())

/** A 30-second preview. [gain] is Deezer's loudness in dB, 0 when unknown. */
@Serializable
data class Preview(
    val id: FlexibleId = "",
    val title: String = "",
    val artist: String = "",
    val album: String = "",
    val cover: String = "",
    val preview: String = "",
    val gain: Double = 0.0,
    val link: String = "",
)

@Serializable
data class LibraryCheckItem(
    val key: String,
    val type: String,
    val id: String? = null,
    val title: String = "",
    val artist: String = "",
    val album: String = "",
    val duration: Int? = null,
)

@Serializable
data class LibraryCheckRequest(val items: List<LibraryCheckItem>)

/** A track: [owned]. An album: [ownedCount] of [total]. An artist: [albumsOwned]. */
@Serializable
data class Owned(
    val owned: Boolean = false,
    @SerialName("owned_count") val ownedCount: Int = 0,
    val total: Int? = null,
    @SerialName("albums_owned") val albumsOwned: Int = 0,
    @SerialName("tracks_owned") val tracksOwned: Int = 0,
)

@Serializable
data class LibraryCheckAnswer(val results: Map<String, Owned> = emptyMap())

@Serializable
data class LibraryStats(
    val count: Int = 0,
    val artists: Int = 0,
    val albums: Int = 0,
    /** When the index was built, in seconds. */
    @SerialName("generated_at") val generatedAt: Double? = null,
)

/** A file of the library, as "Choose a library file" lists it. */
@Serializable
data class LibraryFile(
    val path: String,
    val artist: String = "",
    val title: String = "",
    val album: String = "",
    val duration: Double? = null,
    val file: String = "",
)

@Serializable
data class LibrarySearchAnswer(val results: List<LibraryFile> = emptyList())
