package io.github.catchow0.d2n.ui.playlists

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.PlaylistPreview
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
)

class PlaylistTracksViewModel(private val api: () -> D2nApi, private val id: String) : ViewModel() {
    private val _state = MutableStateFlow(PlaylistTracksState())
    val state: StateFlow<PlaylistTracksState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: PlaylistTracksResponse = apiCall { api().playlistTracks(id) }
                _state.value = _state.value.copy(loading = false, preview = resp.playlist)
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

    fun clearMessage() { _state.value = _state.value.copy(message = null, error = null) }
}