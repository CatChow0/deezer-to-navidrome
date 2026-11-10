package io.github.catchow0.d2n.ui.dashboard

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.LibraryStats
import io.github.catchow0.d2n.data.LinkRequest
import io.github.catchow0.d2n.data.PlaylistsAnswer
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/** Playlists that are the user's own: Made for you and Deezer's mixes have their tab. */
fun PlaylistsAnswer.own() = playlists.filter { it.kind != "mix" && it.kind != "auto" }

/** The dashboard: the profile's playlists, those made in Navidrome, and the library. */
class DashboardViewModel(
    deps: ScreenDeps,
    /** A shared link, made ready for the server (a Deezer short link followed). */
    private val resolveLink: suspend (String) -> String = { it },
) : D2nViewModel(deps) {
    private val _playlists = MutableStateFlow(Remote<PlaylistsAnswer>())
    val playlists: StateFlow<Remote<PlaylistsAnswer>> = _playlists

    private val _library = MutableStateFlow(Remote<LibraryStats>())
    val library: StateFlow<Remote<LibraryStats>> = _library

    private val _opened = MutableStateFlow<String?>(null)

    /** A playlist just added: the screen opens it, then calls [onOpened]. */
    val opened: StateFlow<String?> = _opened

    init {
        followProfile { load() }
    }

    private suspend fun load() = coroutineScope {
        launch { _playlists.fill { playlists() } }
        launch { _library.fill { libraryStats() } }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    /** A Deezer or Spotify playlist, by its link or a Deezer ID. */
    fun add(link: String) {
        val text = link.trim()
        if (text.isEmpty()) return
        act(
            "add",
            { addPlaylist(LinkRequest(resolveLink(text))) },
            done = { Notice(it.message.ifBlank { "Playlist added" }, it.taskId) },
            after = { answer ->
                _playlists.fill { playlists() }
                if (answer.id.isNotEmpty()) _opened.value = answer.id
            },
        )
    }

    /** A CSV export (Exportify, TuneMyMusic, Soundiiz): finding its tracks on Deezer is a task. */
    fun importCsv(fileName: String, bytes: ByteArray) {
        if (bytes.size > MAX_CSV_BYTES) {
            notify("This file is over 5 MB: export a smaller playlist.")
            return
        }
        val part = MultipartBody.Part.createFormData("csv_file", fileName, bytes.toRequestBody("text/csv".toMediaType()))
        act(
            "import",
            { importPlaylist(part) },
            done = { Notice(it.message.ifBlank { "Playlist imported" }, it.taskId) },
            after = { answer ->
                _playlists.fill { playlists() }
                if (answer.id.isNotEmpty()) _opened.value = answer.id
            },
        )
    }

    fun onOpened() {
        _opened.value = null
    }

    /** Index new and changed files. */
    fun startLibraryRefresh() {
        act("library", { refreshLibrary() }, done = { Notice("Library refresh started", it.taskId) }, after = { taskStarted(::refresh) })
    }

    private companion object {
        const val MAX_CSV_BYTES = 5 * 1024 * 1024
    }
}
