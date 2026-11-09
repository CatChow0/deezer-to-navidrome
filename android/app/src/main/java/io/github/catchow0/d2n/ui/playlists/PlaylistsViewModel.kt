package io.github.catchow0.d2n.ui.playlists

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.LinkBody
import io.github.catchow0.d2n.data.PlaylistImportResponse
import io.github.catchow0.d2n.data.PlaylistListResponse
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.data.apiCall
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PlaylistsState(
    val loading: Boolean = false,
    val playlists: List<PlaylistTile> = emptyList(),
    val navidrome: List<PlaylistTile> = emptyList(),
    val addLink: String = "",
    val error: String? = null,
    val message: String? = null,
)

class PlaylistsViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(PlaylistsState())
    val state: StateFlow<PlaylistsState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null, message = null)
            try {
                val resp: PlaylistListResponse = apiCall { api().playlists() }
                _state.value = _state.value.copy(
                    loading = false,
                    playlists = resp.playlists,
                    navidrome = resp.navidrome,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed to load playlists")
            }
        }
    }

    fun onAddLink(value: String) { _state.value = _state.value.copy(addLink = value) }

    fun add() {
        val link = state.value.addLink.trim()
        if (link.isEmpty()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp = apiCall { api().addPlaylist(LinkBody(link)) }
                _state.value = _state.value.copy(
                    loading = false,
                    addLink = "",
                    message = resp.playlist?.title ?: "Added",
                )
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Add failed")
            }
        }
    }

    fun delete(id: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                apiCall { api().deletePlaylist(id) }
                _state.value = _state.value.copy(loading = false, message = "Deleted")
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Delete failed")
            }
        }
    }

    fun importCsv(fileName: String, bytes: ByteArray) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val body = bytes.toRequestBody("text/csv".toMediaTypeOrNull())
                val part = MultipartBody.Part.createFormData("csv_file", fileName, body)
                val resp: PlaylistImportResponse = apiCall { api().importPlaylist(part) }
                _state.value = _state.value.copy(loading = false, message = resp.message ?: "Imported")
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Import failed")
            }
        }
    }

    fun clearMessage() { _state.value = _state.value.copy(message = null, error = null) }
}