package io.github.catchow0.d2n.ui.playlists

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.AccountsRequest
import io.github.catchow0.d2n.data.AutomationRequest
import io.github.catchow0.d2n.data.LibraryFile
import io.github.catchow0.d2n.data.MatchRequest
import io.github.catchow0.d2n.data.NavidromeAccount
import io.github.catchow0.d2n.data.NavidromeStatus
import io.github.catchow0.d2n.data.PlaylistAutomation
import io.github.catchow0.d2n.data.PlaylistRow
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.data.PlaylistTracksAnswer
import io.github.catchow0.d2n.data.ScanRequest
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.data.SourceMatchRequest
import io.github.catchow0.d2n.data.TrackDownloadRequest
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.plural
import kotlinx.coroutines.Job
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Which tracks the list shows, as the web's filter. */
enum class TrackFilter(val label: String, val empty: String) {
    All("All", "This playlist has no tracks yet."),
    Missing("Missing", "Nothing is missing from your library."),
    Found("In library", "None of these tracks are in your library yet."),
    Unchecked("Not checked", "Every track has been checked."),
    Review("To review", "Nothing to review: every track has a sure Deezer match."),
}

/** An imported track whose Deezer match is worth a look: unsure, or none at all. */
fun PlaylistRow.needsReview(): Boolean {
    val source = xp ?: return false
    return source.status == "uncertain" || (!source.onDeezer && source.status != "pending")
}

/** Imported tracks without a Deezer track have an ID such as "src:sp:…": nothing to play or download. */
fun PlaylistRow.deezerId(): String? = trackId?.takeIf { id -> id.isNotEmpty() && id.all(Char::isDigit) }

fun PlaylistRow.shownBy(filter: TrackFilter, query: String): Boolean {
    val kept = when (filter) {
        TrackFilter.All -> true
        TrackFilter.Missing -> matched == false
        TrackFilter.Found -> matched == true
        TrackFilter.Unchecked -> matched == null
        TrackFilter.Review -> needsReview()
    }
    if (!kept) return false
    val words = query.trim().lowercase()
    return words.isEmpty() || "$deezerName $deezerAlbum $sourceName".lowercase().contains(words)
}

/** One playlist: its tracks and matches, scans and downloads, and where it goes in Navidrome. */
class PlaylistViewModel(deps: ScreenDeps, val id: String) : D2nViewModel(deps) {
    private val _tracks = MutableStateFlow(Remote<PlaylistTracksAnswer>())
    val tracks: StateFlow<Remote<PlaylistTracksAnswer>> = _tracks

    private val _tile = MutableStateFlow<PlaylistTile?>(null)

    /** The playlist as the dashboard lists it: kind, cover, accounts and automation. */
    val tile: StateFlow<PlaylistTile?> = _tile

    private val _accounts = MutableStateFlow<List<NavidromeAccount>>(emptyList())
    val accounts: StateFlow<List<NavidromeAccount>> = _accounts

    private val _files = MutableStateFlow<Remote<List<LibraryFile>>?>(null)

    /** "Choose a library file": what the library search found. */
    val files: StateFlow<Remote<List<LibraryFile>>?> = _files

    private val _picks = MutableStateFlow<Remote<List<SearchResult>>?>(null)

    /** "Find on Deezer": what the Deezer search found. */
    val picks: StateFlow<Remote<List<SearchResult>>?> = _picks

    private val _gone = MutableStateFlow(false)

    /** Deleted: the screen goes back. */
    val gone: StateFlow<Boolean> = _gone

    private var searching: Job? = null

    init {
        followProfile { load() }
    }

    private suspend fun load() = coroutineScope {
        launch { _tracks.fill { playlistTracks(id) } }
        launch {
            try {
                _tile.value = call { playlists() }.playlists.firstOrNull { it.id == id }
            } catch (e: io.github.catchow0.d2n.data.ApiFailure) {
                // The header keeps what the tracks say.
            }
        }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    fun scan(quick: Boolean) {
        val mode = if (quick) "quick" else "full"
        act(
            "scan",
            { scanPlaylist(id, ScanRequest(mode)) },
            done = { Notice(if (quick) "Quick scan started" else "Full scan started", it.taskId) },
            after = { taskStarted(::refresh) },
        )
    }

    fun downloadMissing() {
        val missing = _tracks.value.value?.playlist?.rows?.count { it.matched == false && it.deezerId() != null && !it.downloaded } ?: 0
        act(
            "download-missing",
            { downloadMissing(id) },
            done = { Notice("Downloading ${plural(missing, "missing track")}", it.taskId) },
            after = { taskStarted(::refresh) },
        )
    }

    fun downloadTrack(row: PlaylistRow) {
        val trackId = row.deezerId() ?: return
        act("download-$trackId", { downloadTrack(trackId, TrackDownloadRequest(row.deezerName, id)) }, done = { Notice("Download started", it.taskId) })
    }

    /** Publishes again now, even unchanged: for a playlist edited in Navidrome. */
    fun publish() {
        act("publish", { publishPlaylist(id) }, done = { Notice("Publishing in Navidrome…") }, after = { setNavidrome(it.navidrome) })
    }

    /** The Navidrome accounts this playlist goes to; at least one. */
    fun setAccounts(accounts: List<String>) {
        if (accounts.isEmpty()) {
            notify("A playlist needs at least one account: delete it instead.")
            return
        }
        act(
            "accounts",
            { playlistAccounts(id, AccountsRequest(accounts)) },
            done = { Notice("Saved: it is being published") },
            after = { answer ->
                setNavidrome(answer.navidrome)
                _tile.update { it?.copy(accounts = accounts) }
            },
        )
    }

    fun loadAccounts() {
        viewModelScope.launch {
            try {
                _accounts.value = call { navidromeAccounts() }.accounts
            } catch (e: io.github.catchow0.d2n.data.ApiFailure) {
                notify(e.message ?: "The accounts could not be read.")
            }
        }
    }

    fun setAutomation(automation: PlaylistAutomation) {
        act(
            "automation",
            { playlistAutomation(id, AutomationRequest(automation.scan, automation.intervalMinutes, automation.download)) },
            done = { Notice(if (automation.scan) "Automation saved" else "Automatic scans turned off") },
            after = { _tile.update { it?.copy(automation = automation) } },
        )
    }

    /** [mode]: missing, auto, or file with [path]. */
    fun match(row: PlaylistRow, mode: String, path: String? = null) {
        val trackId = row.trackId ?: return
        act(
            "match-${row.number}",
            { matchTrack(id, MatchRequest(trackId, mode, path)) },
            done = { Notice(if (mode == "auto") "Back to automatic matching. The next scan will match it again." else "Match saved and playlist file updated") },
            after = { replaceRow(it.row) },
        )
    }

    /** An imported track's Deezer track: an ID, "auto", or null for "not on Deezer". */
    fun pickOnDeezer(row: PlaylistRow, deezerId: String?) {
        val key = row.xp?.key ?: return
        act(
            "pick-${row.number}",
            { sourceMatch(id, SourceMatchRequest(key, deezerId)) },
            done = {
                Notice(
                    when (deezerId) {
                        null -> "Marked as not on Deezer"
                        "auto" -> "Back to the automatic Deezer match"
                        else -> "Deezer track saved and playlist file updated"
                    },
                )
            },
            after = { answer ->
                replaceRow(answer.row)
                answer.xp?.let { summary ->
                    _tracks.update { remote ->
                        val shown = remote.value ?: return@update remote
                        remote.copy(value = shown.copy(playlist = shown.playlist.copy(xp = summary)))
                    }
                }
            },
        )
    }

    fun searchFiles(query: String) {
        searching?.cancel()
        _files.value = Remote()
        searching = viewModelScope.launch {
            val flow = MutableStateFlow(Remote<List<LibraryFile>>())
            flow.fill { librarySearch(query).results }
            _files.value = flow.value
        }
    }

    fun searchDeezer(query: String) {
        searching?.cancel()
        _picks.value = Remote()
        searching = viewModelScope.launch {
            val flow = MutableStateFlow(Remote<List<SearchResult>>())
            flow.fill { search(query, "track").results }
            _picks.value = flow.value
        }
    }

    fun closeSearches() {
        searching?.cancel()
        _files.value = null
        _picks.value = null
    }

    fun delete() {
        act("delete", { deletePlaylist(id) }, done = { Notice(it.message.ifBlank { "Playlist deleted." }) }, after = { _gone.value = true })
    }

    private fun setNavidrome(status: NavidromeStatus) {
        _tracks.update { it.copy(value = it.value?.copy(navidrome = status)) }
    }

    private fun replaceRow(row: PlaylistRow) {
        _tracks.update { remote ->
            val answer = remote.value ?: return@update remote
            val rows = answer.playlist.rows.map { if (it.number == row.number) row else it }
            remote.copy(
                value = answer.copy(
                    playlist = answer.playlist.copy(
                        rows = rows,
                        matchedCount = rows.count { it.matched == true },
                        unmatchedCount = rows.count { it.matched == false },
                        uncheckedCount = rows.count { it.matched == null },
                    ),
                ),
            )
        }
    }
}
