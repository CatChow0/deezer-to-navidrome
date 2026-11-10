package io.github.catchow0.d2n.ui.search

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.AlbumTrack
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.DeezerAlbum
import io.github.catchow0.d2n.data.DeezerArtist
import io.github.catchow0.d2n.data.DownloadRequest
import io.github.catchow0.d2n.data.LibraryCheckItem
import io.github.catchow0.d2n.data.LibraryCheckRequest
import io.github.catchow0.d2n.data.Owned
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.data.TrackDownloadRequest
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What a search looks for. */
enum class SearchKind(val api: String, val label: String) { Track("track", "Tracks"), Album("album", "Albums"), Artist("artist", "Artists") }

/** "In library", or how much of it is: what the web's chips say. */
fun ownedLabel(kind: SearchKind, owned: Owned?, total: Int?): String? {
    owned ?: return null
    return when (kind) {
        SearchKind.Track -> if (owned.owned) "In library" else null
        SearchKind.Album -> {
            val all = owned.total ?: total ?: 0
            when {
                owned.ownedCount <= 0 -> null
                all > 0 && owned.ownedCount >= all -> "In library"
                all > 0 -> "${owned.ownedCount}/$all tracks owned"
                else -> "${owned.ownedCount} tracks owned"
            }
        }
        SearchKind.Artist -> when {
            owned.albumsOwned <= 0 -> null
            (total ?: 0) > 0 -> "${owned.albumsOwned}/$total albums owned"
            else -> "${owned.albumsOwned} albums owned"
        }
    }
}

private fun SearchResult.checkItem(kind: SearchKind) = when (kind) {
    SearchKind.Track -> LibraryCheckItem(id, "track", title = title, artist = artist, album = album, duration = duration)
    SearchKind.Album -> LibraryCheckItem(id, "album", id = id, title = title, artist = artist.ifBlank { subtitle })
    SearchKind.Artist -> LibraryCheckItem(id, "artist", title = title)
}

/** Shared by the search and its album and artist pages: downloads, and what the library has. */
abstract class DeezerViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    /** [type]: track, album, or artist for the whole discography. */
    fun download(type: String, id: String, label: String) {
        val notice = when (type) {
            "album" -> "Downloading the album"
            "artist" -> "Downloading the discography"
            else -> "Download started"
        }
        act(
            "download-$type-$id",
            { if (type == "track") downloadTrack(id, TrackDownloadRequest(label)) else download(DownloadRequest(type, id, label)) },
            done = { Notice(notice, it.taskId) },
        )
    }

    protected suspend fun owned(items: List<LibraryCheckItem>): Map<String, Owned> = if (items.isEmpty()) emptyMap() else try {
        call { libraryCheck(LibraryCheckRequest(items.take(100))) }.results
    } catch (e: ApiFailure) {
        emptyMap()
    }
}

class SearchViewModel(deps: ScreenDeps) : DeezerViewModel(deps) {
    data class Results(val kind: SearchKind, val query: String, val items: List<SearchResult>, val owned: Map<String, Owned> = emptyMap())

    private val _kind = MutableStateFlow(SearchKind.Track)
    val kind: StateFlow<SearchKind> = _kind

    private val _results = MutableStateFlow<Remote<Results>?>(null)

    /** Null before the first search. */
    val results: StateFlow<Remote<Results>?> = _results

    private var running: Job? = null
    private var lastQuery = ""

    fun setKind(kind: SearchKind) {
        if (kind == _kind.value) return
        _kind.value = kind
        if (lastQuery.isNotBlank()) search(lastQuery)
    }

    fun search(query: String) {
        val text = query.trim()
        lastQuery = text
        running?.cancel()
        if (text.isEmpty()) {
            _results.value = null
            return
        }
        val kind = _kind.value
        _results.update { (it ?: Remote()).copy(loading = true, error = null) }
        running = viewModelScope.launch {
            try {
                val items = call { search(text, kind.api) }.results
                _results.value = Remote(Results(kind, text, items), loading = false)
                // Then what the library has, which takes longer for albums.
                val owned = owned(items.map { it.checkItem(kind) })
                _results.update { remote -> remote?.copy(value = remote.value?.copy(owned = owned)) }
            } catch (e: ApiFailure) {
                _results.update { (it ?: Remote()).copy(loading = false, error = e.message) }
            }
        }
    }

    fun clear() {
        running?.cancel()
        lastQuery = ""
        _results.value = null
    }
}

class AlbumViewModel(deps: ScreenDeps, private val id: String) : DeezerViewModel(deps) {
    data class Page(val album: DeezerAlbum, val owned: Map<String, Owned> = emptyMap())

    private val _page = MutableStateFlow(Remote<Page>())
    val page: StateFlow<Remote<Page>> = _page

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _page.update { it.copy(loading = true, error = null) }
            try {
                val album = call { album(id) }.album
                _page.value = Remote(Page(album), loading = false)
                val owned = owned(album.tracks.map { it.checkItem(album) })
                _page.update { remote -> remote.copy(value = remote.value?.copy(owned = owned)) }
            } catch (e: ApiFailure) {
                _page.update { it.copy(loading = false, error = e.message) }
            }
        }
    }

    private fun AlbumTrack.checkItem(album: DeezerAlbum) =
        LibraryCheckItem(trackId, "track", title = title, artist = artist.ifBlank { album.artist }, album = album.title, duration = duration)
}

class ArtistViewModel(deps: ScreenDeps, private val id: String) : DeezerViewModel(deps) {
    data class Page(val artist: DeezerArtist, val owned: Map<String, Owned> = emptyMap(), val summary: Owned? = null)

    private val _page = MutableStateFlow(Remote<Page>())
    val page: StateFlow<Remote<Page>> = _page

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _page.update { it.copy(loading = true, error = null) }
            try {
                val artist = call { artist(id) }.artist
                _page.value = Remote(Page(artist), loading = false)
                val summary = owned(listOf(LibraryCheckItem(artist.id, "artist", title = artist.name)))[artist.id]
                _page.update { remote -> remote.copy(value = remote.value?.copy(summary = summary)) }
                val owned = owned(artist.albums.map { LibraryCheckItem(it.id, "album", id = it.id, title = it.title, artist = artist.name) })
                _page.update { remote -> remote.copy(value = remote.value?.copy(owned = owned)) }
            } catch (e: ApiFailure) {
                _page.update { it.copy(loading = false, error = e.message) }
            }
        }
    }
}
