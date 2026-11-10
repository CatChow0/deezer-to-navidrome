package io.github.catchow0.d2n.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import kotlinx.serialization.json.JsonObject
import retrofit2.http.DELETE
import retrofit2.http.PUT
import okhttp3.MultipartBody
import retrofit2.http.Multipart
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** /api/v1, as far as phase 6 goes. The paths are relative, without a leading
 * slash, so a server installed under a sub-path keeps it. */
interface D2nApi {
    @GET("api/v1/auth/status")
    suspend fun authStatus(): AuthStatus

    @POST("api/v1/auth/login")
    suspend fun login(@Body body: Credentials): SignedIn

    @POST("api/v1/auth/setup")
    suspend fun setup(@Body body: Credentials): SignedIn

    @POST("api/v1/auth/logout")
    suspend fun logout(): SignedOut

    @GET("api/v1/info")
    suspend fun info(): ServerInfo

    // Phase 8: New and Help.
    @GET("api/v1/content/notes")
    suspend fun contentNotes(): ContentNotesResponse

    // Phase 8: Stats.
    @GET("api/v1/stats/overview")
    suspend fun statsOverview(@Query("period") period: String = "month", @Query("key") key: String = "", @Query("tz") tz: String): StatsOverviewResponse

    @GET("api/v1/stats/plays")
    suspend fun statsPlays(@Query("q") query: String? = null, @Query("page") page: Int = 1): StatsPlaysResponse

    @GET("api/v1/stats/recaps")
    suspend fun statsRecaps(@Query("tz") tz: String): StatsRecapsResponse

    @GET("api/v1/content/help")
    suspend fun contentHelp(): ContentHelpResponse

    // Phase 8: settings.
    @GET("api/v1/settings")
    suspend fun settings(): SettingsResponse

    @PUT("api/v1/settings")
    suspend fun saveSettings(@Body body: Map<String, Any?>): SettingsResponse

    @POST("api/v1/settings/clear/{what}")
    suspend fun clearSettings(@Path("what") what: String): ClearSettingsResponse

    @POST("api/v1/content/notes/seen")
    suspend fun notesSeen(): TaskStartResponse

    @GET("api/v1/tasks")
    suspend fun tasks(@Query("changed_since") changedSince: Double? = null): TaskList

    @GET("api/v1/tasks/{id}")
    suspend fun task(@Path("id") id: String): TaskEnvelope

    @GET("api/v1/tasks/{id}/events")
    suspend fun taskEvents(@Path("id") id: String, @Query("after") after: Int, @Query("wait") wait: Int): TaskEvents

    @POST("api/v1/tasks/{id}/cancel")
    suspend fun cancelTask(@Path("id") id: String): CancelAnswer

    @GET("api/v1/app")
    suspend fun app(): AppInfo

    // Phase 7: Deezer search.
    @GET("api/v1/search")
    suspend fun search(@Query("q") query: String, @Query("type") type: String = "track"): SearchResponse

    @GET("api/v1/search/album/{album_id}")
    suspend fun searchAlbum(@Path("album_id") albumId: String): SearchAlbumResponse

    @GET("api/v1/search/artist/{artist_id}")
    suspend fun searchArtist(@Path("artist_id") artistId: String): SearchArtistResponse

    @GET("api/v1/preview/{track_id}")
    suspend fun preview(@Path("track_id") trackId: String): Preview

    @POST("api/v1/library/check")
    suspend fun libraryCheck(@Body body: LibraryCheckRequest): LibraryCheckResponse

    // Phase 7: playlists.
    @GET("api/v1/playlists")
    suspend fun playlists(): PlaylistListResponse

    @POST("api/v1/playlists")
    suspend fun addPlaylist(@Body body: LinkBody): PlaylistAddResponse

    @DELETE("api/v1/playlists/{id}")
    suspend fun deletePlaylist(@Path("id") id: String): PlaylistListResponse

    @Multipart
    @POST("api/v1/playlists/import")
    suspend fun importPlaylist(@Part csvFile: MultipartBody.Part): PlaylistImportResponse

    @GET("api/v1/playlists/{id}/tracks")
    suspend fun playlistTracks(@Path("id") id: String): PlaylistTracksResponse

    @POST("api/v1/playlists/{id}/scan")
    suspend fun playlistScan(@Path("id") id: String, @Body body: Map<String, Any?> = emptyMap()): TaskStartResponse

    @POST("api/v1/playlists/{id}/download-missing")
    suspend fun playlistDownloadMissing(@Path("id") id: String): TaskStartResponse

    @POST("api/v1/playlists/{id}/match")
    suspend fun playlistMatch(@Path("id") id: String, @Body body: Map<String, Any?>): JsonObject

    @PUT("api/v1/playlists/{id}/automation")
    suspend fun playlistAutomation(@Path("id") id: String, @Body body: Map<String, Any?>): JsonObject

    @PUT("api/v1/playlists/{id}/accounts")
    suspend fun playlistAccounts(@Path("id") id: String, @Body body: Map<String, Any?>): JsonObject

    @POST("api/v1/playlists/{id}/publish")
    suspend fun playlistPublish(@Path("id") id: String): JsonObject

    // Phase 7: Navidrome accounts for a playlist.
    @GET("api/v1/navidrome/accounts")
    suspend fun navidromeAccounts(): NavidromeAccountsResponse

    // Phase 7: Made for you.
    @GET("api/v1/mixes")
    suspend fun mixes(): MixesResponse

    // Phase 8: Deezer mixes you can follow.
    @GET("api/v1/deezer/mixes")
    suspend fun deezerMixes(): DeezerMixesResponse

    @POST("api/v1/deezer/mixes/follow")
    suspend fun followDeezerMix(@Body body: Map<String, Any?>): DeezerMixFollowResponse

    // Phase 8: Releases.
    @GET("api/v1/releases")
    suspend fun releases(): ReleasesResponse

    @POST("api/v1/releases/refresh")
    suspend fun refreshReleases(): TaskStartResponse

    @POST("api/v1/releases/mute")
    suspend fun muteReleaseArtist(@Body body: Map<String, Any?>): MuteReleaseResponse

    @POST("api/v1/mixes/trial/{deezer_id}/keep")
    suspend fun mixKeep(@Path("deezer_id") deezerId: String): MixesResponse

    @POST("api/v1/mixes/trial/{deezer_id}/remove")
    suspend fun mixRemove(@Path("deezer_id") deezerId: String): MixesResponse

    @POST("api/v1/mixes/trial/{deezer_id}/restore")
    suspend fun mixRestore(@Path("deezer_id") deezerId: String): MixesResponse
}
