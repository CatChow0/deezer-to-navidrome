package io.github.catchow0.d2n.ui.releases

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.MuteReleaseResponse
import io.github.catchow0.d2n.data.ReleasesResponse
import io.github.catchow0.d2n.data.ReleaseItem
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ReleasesState(
    val loading: Boolean = false,
    val connected: Boolean = false,
    val accountLabel: String = "",
    val updatedAt: Long? = null,
    val releases: List<ReleaseItem> = emptyList(),
    val muted: Map<String, String> = emptyMap(),
    val error: String? = null,
)

class ReleasesViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(ReleasesState())
    val state: StateFlow<ReleasesState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: ReleasesResponse = apiCall { api().releases() }
                _state.value = _state.value.copy(
                    loading = false,
                    connected = resp.connected,
                    accountLabel = resp.deezerAccount?.label ?: "",
                    updatedAt = resp.updatedAt,
                    releases = resp.releases,
                    muted = resp.muted,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }

    fun mute(artistId: String, name: String, muted: Boolean) {
        viewModelScope.launch {
            try {
                val resp: MuteReleaseResponse = apiCall { api().muteReleaseArtist(mapOf("artist_id" to artistId, "name" to name, "muted" to muted)) }
                _state.value = _state.value.copy(muted = resp.muted)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Failed")
            }
        }
    }
}