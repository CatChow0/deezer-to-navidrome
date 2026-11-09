package io.github.catchow0.d2n.data

import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/** The API of one server. The app talks to one server at a time: the last one
 * built is kept. */
class ApiProvider(private val client: OkHttpClient) {
    private var last: Pair<HttpUrl, D2nApi>? = null

    @Synchronized
    fun forServer(base: HttpUrl): D2nApi = last?.takeIf { it.first == base }?.second
        ?: Retrofit.Builder()
            .baseUrl(base)
            .client(client)
            .addConverterFactory(D2nJson.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(D2nApi::class.java)
            .also { last = base to it }
}
