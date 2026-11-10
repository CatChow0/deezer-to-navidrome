package io.github.catchow0.d2n.data

import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** /api/v1 (docs/api/openapi.yaml). The paths are relative, without a leading
 * slash, so a server installed under a sub-path keeps it. Every body is a
 * @Serializable class: the JSON converter cannot write a Map of Any. */
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

    // ── The profile's playlists ─────────────────────────────────────────────

    @GET("api/v1/playlists")
    suspend fun playlists(): PlaylistsAnswer

    @POST("api/v1/playlists")
    suspend fun addPlaylist(@Body body: LinkRequest): AddPlaylistAnswer

    @Multipart
    @POST("api/v1/playlists/import")
    suspend fun importPlaylist(@Part file: MultipartBody.Part): ImportAnswer

    @DELETE("api/v1/playlists/{id}")
    suspend fun deletePlaylist(@Path("id") id: String): DeleteAnswer

    @GET("api/v1/playlists/{id}/tracks")
    suspend fun playlistTracks(@Path("id") id: String): PlaylistTracksAnswer

    @GET("api/v1/playlists/{id}/navidrome")
    suspend fun playlistNavidrome(@Path("id") id: String): NavidromeAnswer

    @PUT("api/v1/playlists/{id}/accounts")
    suspend fun playlistAccounts(@Path("id") id: String, @Body body: AccountsRequest): NavidromeAnswer

    @PUT("api/v1/playlists/{id}/automation")
    suspend fun playlistAutomation(@Path("id") id: String, @Body body: AutomationRequest): AutomationAnswer

    @POST("api/v1/playlists/{id}/scan")
    suspend fun scanPlaylist(@Path("id") id: String, @Body body: ScanRequest): TaskStarted

    @POST("api/v1/playlists/{id}/download-missing")
    suspend fun downloadMissing(@Path("id") id: String): TaskStarted

    @POST("api/v1/playlists/{id}/match")
    suspend fun matchTrack(@Path("id") id: String, @Body body: MatchRequest): RowAnswer

    @POST("api/v1/playlists/{id}/source-match")
    suspend fun sourceMatch(@Path("id") id: String, @Body body: SourceMatchRequest): RowAnswer

    @POST("api/v1/playlists/{id}/publish")
    suspend fun publishPlaylist(@Path("id") id: String): NavidromeAnswer

    @GET("api/v1/navidrome/playlists/{account}/{id}")
    suspend fun navidromePlaylist(@Path("account") account: String, @Path("id") id: String): NavidromePlaylistAnswer

    @GET("api/v1/navidrome/accounts")
    suspend fun navidromeAccounts(): NavidromeAccountsAnswer

    // ── Deezer search, previews and downloads ───────────────────────────────

    @GET("api/v1/search")
    suspend fun search(@Query("q") query: String, @Query("type") type: String): SearchAnswer

    @GET("api/v1/search/album/{id}")
    suspend fun album(@Path("id") id: String): AlbumAnswer

    @GET("api/v1/search/artist/{id}")
    suspend fun artist(@Path("id") id: String): ArtistAnswer

    @GET("api/v1/preview/{id}")
    suspend fun preview(@Path("id") trackId: String): Preview

    @POST("api/v1/downloads")
    suspend fun download(@Body body: DownloadRequest): TaskStarted

    @POST("api/v1/downloads/track/{id}")
    suspend fun downloadTrack(@Path("id") trackId: String, @Body body: TrackDownloadRequest): TaskStarted

    // ── The library ─────────────────────────────────────────────────────────

    @GET("api/v1/library/stats")
    suspend fun libraryStats(): LibraryStats

    @GET("api/v1/library/search")
    suspend fun librarySearch(@Query("q") query: String): LibrarySearchAnswer

    @POST("api/v1/library/check")
    suspend fun libraryCheck(@Body body: LibraryCheckRequest): LibraryCheckAnswer

    @POST("api/v1/library/refresh")
    suspend fun refreshLibrary(): TaskStarted

    // ── Made for you ────────────────────────────────────────────────────────

    @GET("api/v1/mixes")
    suspend fun mixes(): MixesAnswer

    @POST("api/v1/mixes/settings")
    suspend fun mixSettings(@Body body: MixSettingsChange): MixesAnswer

    @POST("api/v1/mixes/generate")
    suspend fun generateMixes(): TaskStarted

    @POST("api/v1/mixes/trial/{id}/keep")
    suspend fun keepTrack(@Path("id") deezerId: String): MixesAnswer

    @POST("api/v1/mixes/trial/{id}/remove")
    suspend fun removeTrack(@Path("id") deezerId: String): MixesAnswer

    @POST("api/v1/mixes/trial/{id}/restore")
    suspend fun restoreTrack(@Path("id") deezerId: String): MixesAnswer

    @POST("api/v1/mixes/trial/keep-pending")
    suspend fun keepPending(@Body body: IdsRequest): MixesAnswer

    @POST("api/v1/mixes/trial/empty-trash")
    suspend fun emptyTrash(): MixesAnswer

    @POST("api/v1/library/metadata/fix")
    suspend fun fixMetadata(): TaskStarted

    @POST("api/v1/library/metadata/undo")
    suspend fun undoMetadata(): TaskStarted

    @GET("api/v1/deezer/mixes")
    suspend fun deezerMixes(): DeezerMixesAnswer

    @POST("api/v1/deezer/mixes/follow")
    suspend fun followMix(@Body body: FollowMixRequest): FollowAnswer
}
