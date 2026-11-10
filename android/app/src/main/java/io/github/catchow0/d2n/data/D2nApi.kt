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

    // ── Settings ────────────────────────────────────────────────────────────

    @GET("api/v1/settings")
    suspend fun settings(): SettingsAnswer

    @PUT("api/v1/settings")
    suspend fun saveSettings(@Body body: SettingsChange): SettingsAnswer

    @POST("api/v1/settings/clear/{what}")
    suspend fun clear(@Path("what") what: String): ClearAnswer

    @GET("api/v1/navidrome/accounts")
    suspend fun navidromeProfiles(): NavidromeProfilesAnswer

    @POST("api/v1/navidrome/accounts")
    suspend fun createNavidromeProfile(@Body body: NavidromeProfileFields): NavidromeProfilesAnswer

    @retrofit2.http.PATCH("api/v1/navidrome/accounts/{id}")
    suspend fun updateNavidromeProfile(@Path("id") id: String, @Body body: NavidromeProfileFields): NavidromeProfilesAnswer

    @DELETE("api/v1/navidrome/accounts/{id}")
    suspend fun deleteNavidromeProfile(@Path("id") id: String): NavidromeProfilesAnswer

    @POST("api/v1/navidrome/accounts/{id}/default")
    suspend fun defaultNavidromeProfile(@Path("id") id: String): NavidromeProfilesAnswer

    @POST("api/v1/navidrome/accounts/{id}/test")
    suspend fun testNavidromeProfile(@Path("id") id: String): NavidromeProfilesAnswer

    @POST("api/v1/navidrome/accounts/test")
    suspend fun testNavidromeFields(@Body body: NavidromeProfileFields): TestAnswer

    @GET("api/v1/navidrome/accounts/{id}/switch")
    suspend fun switchPreview(@Path("id") id: String): SwitchPreviewAnswer

    @POST("api/v1/navidrome/accounts/{id}/switch")
    suspend fun switchToUser(@Path("id") id: String): TaskStarted

    @GET("api/v1/deezer/accounts")
    suspend fun deezerProfiles(): DeezerProfilesAnswer

    @POST("api/v1/deezer/accounts")
    suspend fun createDeezerProfile(@Body body: DeezerProfileFields): DeezerProfilesAnswer

    @retrofit2.http.PATCH("api/v1/deezer/accounts/{id}")
    suspend fun updateDeezerProfile(@Path("id") id: String, @Body body: DeezerProfileFields): DeezerProfilesAnswer

    @DELETE("api/v1/deezer/accounts/{id}")
    suspend fun deleteDeezerProfile(@Path("id") id: String): DeezerProfilesAnswer

    @POST("api/v1/deezer/accounts/{id}/default")
    suspend fun defaultDeezerProfile(@Path("id") id: String): DeezerProfilesAnswer

    @POST("api/v1/deezer/accounts/{id}/download")
    suspend fun downloadDeezerProfile(@Path("id") id: String): DeezerProfilesAnswer

    @POST("api/v1/deezer/accounts/{id}/check")
    suspend fun checkDeezerProfile(@Path("id") id: String): DeezerProfilesAnswer

    @GET("api/v1/settings/security")
    suspend fun security(): SecurityAnswer

    @POST("api/v1/settings/password")
    suspend fun changePassword(@Body body: PasswordRequest): Unit

    @POST("api/v1/settings/api-token")
    suspend fun newApiToken(): TokenAnswer

    @PUT("api/v1/settings/webhook")
    suspend fun setWebhook(@Body body: WebhookRequest): WebhookAnswer

    @DELETE("api/v1/settings/webhook")
    suspend fun removeWebhook(): WebhookAnswer

    @POST("api/v1/settings/webhook/test")
    suspend fun testWebhook(): WebhookTestAnswer

    @GET("api/v1/devices")
    suspend fun devices(): DevicesAnswer

    @DELETE("api/v1/devices/{id}")
    suspend fun revokeDevice(@Path("id") id: String): Unit

    @GET("api/v1/stats/status")
    suspend fun statsStatus(): StatsStatus

    @POST("api/v1/stats/import")
    suspend fun importStats(@Body body: ImportRequest): TaskStarted

    @POST("api/v1/stats/import/preview")
    suspend fun previewStatsImport(): ImportPreview

    @POST("api/v1/stats/token")
    suspend fun setStatsToken(@Body body: StatsTokenRequest): StatsTokenAnswer

    @DELETE("api/v1/stats/token")
    suspend fun deleteStatsToken(): Unit

    @POST("api/v1/library/rebuild")
    suspend fun rebuildLibrary(): TaskStarted

    @POST("api/v1/downloads/repair")
    suspend fun repairDownloads(): TaskStarted

    @POST("api/v1/dedup/start")
    suspend fun scanDuplicates(): TaskStarted

    @GET("api/v1/dedup/report")
    suspend fun duplicates(): DuplicateReportAnswer

    @POST("api/v1/dedup/apply")
    suspend fun applyDuplicates(@Body body: DuplicateApply): DuplicateApplyAnswer

    // ── New and Help ────────────────────────────────────────────────────────

    @GET("api/v1/content/notes")
    suspend fun notes(): NotesAnswer

    @POST("api/v1/content/notes/seen")
    suspend fun notesSeen(): Unit

    @GET("api/v1/content/help")
    suspend fun help(): HelpAnswer

    // ── Stats ───────────────────────────────────────────────────────────────

    @GET("api/v1/stats/overview")
    suspend fun statsOverview(@Query("period") period: String, @Query("key") key: String, @Query("tz") tz: String): StatsOverview

    @GET("api/v1/stats/recaps")
    suspend fun recaps(@Query("tz") tz: String): RecapIndex

    @GET("api/v1/stats/recap")
    suspend fun recap(@Query("type") kind: String, @Query("key") key: String, @Query("tz") tz: String): Recap

    @GET("api/v1/stats/{kind}/{id}")
    suspend fun statsEntity(@Path("kind") kind: String, @Path("id") id: Long, @Query("tz") tz: String): StatsEntity

    @GET("api/v1/stats/plays")
    suspend fun plays(@Query("q") query: String, @Query("page") page: Int): PlaysPage

    // ── Releases ────────────────────────────────────────────────────────────

    @GET("api/v1/releases")
    suspend fun releases(): ReleasesAnswer

    @POST("api/v1/releases/refresh")
    suspend fun refreshReleases(): TaskStarted

    @POST("api/v1/releases/mute")
    suspend fun muteArtist(@Body body: MuteRequest): MutedAnswer

    @GET("api/v1/deezer/mixes")
    suspend fun deezerMixes(): DeezerMixesAnswer

    @POST("api/v1/deezer/mixes/follow")
    suspend fun followMix(@Body body: FollowMixRequest): FollowAnswer
}
