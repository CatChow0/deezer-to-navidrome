package io.github.catchow0.d2n.ui.madeforyou

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.MixesResponse
import io.github.catchow0.d2n.data.MixTrack
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class MixesState(
    val loading: Boolean = false,
    val onTrial: List<MixTrack> = emptyList(),
    val pending: List<MixTrack> = emptyList(),
    val trash: List<MixTrack> = emptyList(),
    val error: String? = null,
)

class MixesViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(MixesState())
    val state: StateFlow<MixesState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: MixesResponse = apiCall { api().mixes() }
                _state.value = _state.value.copy(loading = false, onTrial = resp.onTrial, pending = resp.pending, trash = resp.trash)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }

    fun keep(id: String) = decide(id) { api().mixKeep(id) }
    fun remove(id: String) = decide(id) { api().mixRemove(id) }
    fun restore(id: String) = decide(id) { api().mixRestore(id) }

    private fun decide(id: String, call: suspend () -> MixesResponse) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp = apiCall { call() }
                _state.value = _state.value.copy(loading = false, onTrial = resp.onTrial, pending = resp.pending, trash = resp.trash)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }
}