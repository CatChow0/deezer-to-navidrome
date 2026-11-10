package io.github.catchow0.d2n.audio

import android.content.Context
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.ui.common.AppEvents
import io.github.catchow0.d2n.ui.common.Notice
import kotlin.math.pow
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** What plays now, for the mini player. */
data class NowPlaying(
    val id: String,
    val title: String,
    val artist: String,
    val cover: String? = null,
    val playing: Boolean = false,
    val loading: Boolean = true,
    val progress: Float = 0f,
)

/**
 * The app's one player: a 30-second Deezer preview, or a file of the server
 * (a recap). Starting another stops the one before. It is created the first
 * time something plays, and runs on the main thread, as ExoPlayer wants.
 * Previews are levelled as on the web: towards -12 dB, from -12 to +6 dB.
 */
class PreviewPlayer(
    private val context: Context,
    private val client: okhttp3.OkHttpClient,
    private val api: () -> D2nApi,
    private val events: AppEvents,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _now = MutableStateFlow<NowPlaying?>(null)
    val now: StateFlow<NowPlaying?> = _now

    private var player: ExoPlayer? = null
    private var fallback: Triple<String, String, String>? = null
    private var ticker: Job? = null
    private var loading: Job? = null

    /** The preview of a Deezer track; the same one again pauses or resumes it. */
    fun playDeezer(trackId: String, title: String, artist: String, cover: String? = null) {
        if (_now.value?.id == trackId) {
            toggle()
            return
        }
        stop()
        _now.value = NowPlaying(trackId, title, artist, cover)
        loading = scope.launch {
            try {
                val preview = apiCall { api().preview(trackId) }
                if (_now.value?.id != trackId) return@launch
                if (preview.preview.isBlank()) {
                    events.post(Notice("Deezer has no preview of this track.", error = true))
                    _now.value = null
                    return@launch
                }
                _now.update { it?.copy(cover = cover ?: preview.cover.ifBlank { null }) }
                start(preview.preview, levelFor(preview.gain))
            } catch (e: ApiFailure) {
                if (_now.value?.id == trackId) _now.value = null
                events.post(Notice(e.message ?: "The preview cannot be played.", error = true))
            }
        }
    }

    /**
     * A file the server serves itself, such as a recap's track, from [startAtMs].
     * When it cannot be played, the Deezer preview of [fallbackDeezerId] plays
     * instead, and nothing is said: a recap goes on in silence at worst.
     */
    fun playUrl(
        id: String,
        url: String,
        title: String,
        artist: String,
        cover: String? = null,
        startAtMs: Long = 0,
        fallbackDeezerId: String? = null,
    ) {
        if (_now.value?.id == id) return
        stop()
        _now.value = NowPlaying(id, title, artist, cover)
        fallback = fallbackDeezerId?.takeIf { it.isNotBlank() }?.let { Triple(it, title, artist) }
        start(url, VOLUME, startAtMs)
    }

    fun toggle() {
        val p = player ?: return
        if (p.isPlaying) p.pause() else p.play()
    }

    fun resume() {
        player?.takeIf { _now.value != null }?.play()
    }

    /** Leaving the app pauses; it never plays in the background. */
    fun pause() {
        player?.pause()
    }

    fun stop() {
        fallback = null
        loading?.cancel()
        ticker?.cancel()
        player?.run {
            stop()
            clearMediaItems()
        }
        _now.value = null
    }

    @OptIn(UnstableApi::class)
    private fun ensurePlayer(): ExoPlayer = player ?: ExoPlayer.Builder(context)
        .setMediaSourceFactory(DefaultMediaSourceFactory(OkHttpDataSource.Factory(client)))
        .setAudioAttributes(
            AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(),
            /* handleAudioFocus = */ true,
        )
        .setHandleAudioBecomingNoisy(true)
        .build()
        .also { created ->
            created.addListener(object : Player.Listener {
                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    _now.update { it?.copy(playing = isPlaying, loading = false) }
                }

                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_ENDED) stop()
                }

                override fun onPlayerError(error: PlaybackException) {
                    val instead = fallback
                    stop()
                    if (instead != null) {
                        playDeezer(instead.first, instead.second, instead.third)
                    } else {
                        events.post(Notice("The preview cannot be played.", error = true))
                    }
                }
            })
            player = created
        }

    private fun start(url: String, volume: Float, startAtMs: Long = 0) {
        val p = ensurePlayer()
        p.volume = volume
        p.setMediaItem(MediaItem.fromUri(url), startAtMs)
        p.prepare()
        p.play()
        ticker?.cancel()
        ticker = scope.launch {
            while (isActive) {
                val duration = p.duration.takeIf { it > 0 } ?: 30_000L
                _now.update { it?.copy(progress = (p.currentPosition.toFloat() / duration).coerceIn(0f, 1f)) }
                delay(250)
            }
        }
    }

    private companion object {
        const val TARGET_DB = -12.0
        const val CUT_DB = -12.0
        const val BOOST_DB = 6.0
        const val VOLUME = 0.8f

        /** Deezer's gain in dB, 0 when unknown: the volume that levels it. */
        fun levelFor(gain: Double): Float {
            if (gain == 0.0) return VOLUME
            val db = (TARGET_DB - gain).coerceIn(CUT_DB, BOOST_DB)
            return (VOLUME * 10.0.pow(db / 20)).toFloat().coerceAtMost(1f)
        }
    }
}
