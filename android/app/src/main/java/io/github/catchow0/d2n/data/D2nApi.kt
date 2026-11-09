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
}
