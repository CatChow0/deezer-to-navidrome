package io.github.catchow0.d2n.ui.content

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ContentHelpResponse
import io.github.catchow0.d2n.data.ContentNotesResponse
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ContentState(
    val loading: Boolean = false,
    val notes: ContentNotesResponse? = null,
    val help: ContentHelpResponse? = null,
    val error: String? = null,
)

class ContentViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(ContentState())
    val state: StateFlow<ContentState> = _state.asStateFlow()

    fun loadNotes() {
        viewModelScope.launch {
            _state.value = try { _state.value.copy(loading = true, error = null); val resp = apiCall { api().contentNotes() }; _state.value.copy(loading = false, notes = resp) } catch (e: Exception) { _state.value.copy(loading = false, error = e.message ?: "Failed") }
        }
    }

    fun loadHelp() {
        viewModelScope.launch {
            _state.value = try { _state.value.copy(loading = true, error = null); val resp = apiCall { api().contentHelp() }; _state.value.copy(loading = false, help = resp) } catch (e: Exception) { _state.value.copy(loading = false, error = e.message ?: "Failed") }
        }
    }

    fun markSeen() {
        viewModelScope.launch { try { apiCall { api().notesSeen() } } catch (_: Exception) {} }
    }
}