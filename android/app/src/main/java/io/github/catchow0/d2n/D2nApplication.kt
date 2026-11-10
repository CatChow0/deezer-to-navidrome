package io.github.catchow0.d2n

import android.app.Application
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import coil3.request.crossfade

class D2nApplication : Application(), SingletonImageLoader.Factory {
    val graph: AppGraph by lazy { AppGraph(this) }

    /** Covers go through the app's client: the server's own carry the token
     * and the profile, Deezer's carry nothing. */
    override fun newImageLoader(context: PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            .components { add(OkHttpNetworkFetcherFactory(callFactory = { graph.mediaClient })) }
            .crossfade(true)
            .build()
}
