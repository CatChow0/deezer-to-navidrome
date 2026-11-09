package io.github.catchow0.d2n.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
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
}
