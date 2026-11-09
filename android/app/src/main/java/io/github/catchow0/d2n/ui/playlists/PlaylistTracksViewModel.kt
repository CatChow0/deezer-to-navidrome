package io.github.catchow0.d2n.ui.playlists

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.NavidromeAccount
import io.github.catchow0.d2n.data.PlaylistPreview
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.data.PlaylistTracksResponse
import io.github.catchow0.d2n.data.TaskStartResponse
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PlaylistTracksState(
    val loading: Boolean = false,
    val preview: PlaylistPreview? = null,
    val error: String? = null,
    val message: String? = null,
    val scanning: Boolean = false,
    val accounts: List<NavidromeAccount> = emptyList(),
    val selectedAccounts: Set<String> = emptySet(),
    val autoScan: Boolean = false,
    val autoInterval: String = "60",
    val autoDownload: Boolean = false,
    val settingsLoading: Boolean = false,
    val showSettings: Boolean = false,
)

class PlaylistTracksViewModel(private val api: () -> D2nApi, private val id: String) : ViewModel() {
    private val _state = MutableStateFlow(PlaylistTracksState())
    val state: StateFlow<PlaylistTracksState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: PlaylistTracksResponse = apiCall { api().playlistTracks(id) }
                // Load accounts + current settings from the playlist list (best effort).
                val accountsResp = try { apiCall { api().navidromeAccounts() } } catch (_: Exception) { null }
                val tile: PlaylistTile? = try {
                    apiCall { api().playlists() }.playlists.firstOrNull { it.id == id }
                        ?: apiCall { api().playlists() }.navidrome.firstOrNull { it.id == id }
                } catch (_: Exception) { null }
                _state.value = _state.value.copy(
                    loading = false,
                    preview = resp.playlist,
                    accounts = accountsResp?.accounts ?: emptyList(),
                    selectedAccounts = tile?.accounts?.toSet() ?: emptySet(),
                    autoScan = tile?.automation?.scan ?: false,
                    autoInterval = (tile?.automation?.intervalMinutes ?: 60).toString(),
                    autoDownload = tile?.automation?.download ?: false,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }

    fun scan(quick: Boolean = true) {
        viewModelScope.launch {
            _state.value = _state.value.copy(scanning = true, error = null)
            try {
                val resp: TaskStartResponse = apiCall { api().playlistScan(id, mapOf("mode" to if (quick) "quick" else "full")) }
                _state.value = _state.value.copy(scanning = false, message = "Scan started: ${resp.taskId}")
            } catch (e: Exception) {
                _state.value = _state.value.copy(scanning = false, error = e.message ?: "Scan failed")
            }
        }
    }

    fun downloadMissing() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: TaskStartResponse = apiCall { api().playlistDownloadMissing(id) }
                _state.value = _state.value.copy(loading = false, message = "Download started: ${resp.taskId}")
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Download failed")
            }
        }
    }

    fun mark(trackId: String, mode: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                apiCall { api().playlistMatch(id, mapOf("track_id" to trackId, "mode" to mode)) }
                _state.value = _state.value.copy(loading = false, message = "Updated")
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Match failed")
            }
        }
    }

    fun publish() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                apiCall { api().playlistPublish(id) }
                _state.value = _state.value.copy(loading = false, message = "Published")
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Publish failed")
            }
        }
    }

    fun openSettings() { _state.value = _state.value.copy(showSettings = true) }
    fun closeSettings() { _state.value = _state.value.copy(showSettings = false) }
    fun toggleAccount(id: String) {
        val current = _state.value.selectedAccounts
        _state.value = _state.value.copy(
            selectedAccounts = if (id in current) current - id else current + id,
        )
    }
    fun setAutoScan(value: Boolean) { _state.value = _state.value.copy(autoScan = value) }
    fun setAutoInterval(value: String) { _state.value = _state.value.copy(autoInterval = value) }
    fun setAutoDownload(value: Boolean) { _state.value = _state.value.copy(autoDownload = value) }

    fun saveSettings() {
        viewModelScope.launch {
            _state.value = _state.value.copy(settingsLoading = true, error = null)
            try {
                apiCall {
                    api().playlistAccounts(id, mapOf("accounts" to _state.value.selectedAccounts.toList()))
                }
                apiCall {
                    api().playlistAutomation(id, mapOf(
                        "auto_scan_enabled" to _state.value.autoScan,
                        "auto_scan_interval_minutes" to (_state.value.autoInterval.toIntOrNull() ?: 60),
                        "auto_download_after_scan" to _state.value.autoDownload,
                    ))
                }
                _state.value = _state.value.copy(settingsLoading = false, showSettings = false, message = "Saved")
            } catch (e: Exception) {
                _state.value = _state.value.copy(settingsLoading = false, error = e.message ?: "Save failed")
            }
        }
    }

    fun clearMessage() { _state.value = _state.value.copy(message = null, error = null) }
}