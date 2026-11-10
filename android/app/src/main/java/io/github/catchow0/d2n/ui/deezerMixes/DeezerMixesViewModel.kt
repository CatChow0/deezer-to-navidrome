package io.github.catchow0.d2n.ui.deezerMixes

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.DeezerMixItem
import io.github.catchow0.d2n.data.DeezerMixesResponse
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class DeezerMixesState(
    val loading: Boolean = false,
    val mixes: List<DeezerMixItem> = emptyList(),
    val error: String? = null,
)

class DeezerMixesViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(DeezerMixesState())
    val state: StateFlow<DeezerMixesState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: DeezerMixesResponse = apiCall { api().deezerMixes() }
                _state.value = _state.value.copy(loading = false, mixes = resp.mixes)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }

    fun follow(mix: DeezerMixItem) {
        viewModelScope.launch {
            try {
                apiCall { api().followDeezerMix(mapOf("kind" to mix.kind, "source_id" to mix.sourceId, "title" to mix.title)) }
                _state.value = _state.value.copy(mixes = _state.value.mixes.map { if (it.kind == mix.kind && it.sourceId == mix.sourceId) it.copy(followed = true) else it })
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Failed")
            }
        }
    }
}