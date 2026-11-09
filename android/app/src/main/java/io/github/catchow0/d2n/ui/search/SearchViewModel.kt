package io.github.catchow0.d2n.ui.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.LibraryCheckItem
import io.github.catchow0.d2n.data.LibraryCheckRequest
import io.github.catchow0.d2n.data.SearchResponse
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SearchState(
    val query: String = "",
    val type: String = "track",
    val loading: Boolean = false,
    val results: List<SearchResult> = emptyList(),
    val inLibrary: Map<String, Boolean> = emptyMap(),
    val error: String? = null,
    val previewUrl: String? = null,
)

class SearchViewModel(
    private val api: () -> D2nApi,
    val scope: Any? = null,
) : ViewModel() {
    private val _state = MutableStateFlow(SearchState())
    val state: StateFlow<SearchState> = _state.asStateFlow()

    fun onQuery(value: String) { _state.value = _state.value.copy(query = value) }
    fun onType(type: String) { _state.value = _state.value.copy(type = type) }

    fun preview(trackId: String) {
        viewModelScope.launch {
            try {
                val preview = apiCall { api().preview(trackId) }
                _state.value = _state.value.copy(previewUrl = preview.preview.ifBlank { preview.link })
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Preview failed")
            }
        }
    }

    fun closePreview() { _state.value = _state.value.copy(previewUrl = null) }

    fun submit() {
        val q = state.value.query.trim()
        if (q.isEmpty()) {
            _state.value = _state.value.copy(results = emptyList(), error = null)
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: SearchResponse = apiCall { api().search(q, _state.value.type) }
                val keyOf: (SearchResult) -> String = { r -> "${r.type}:${r.id}" }
                val items = resp.results.take(100).map { r ->
                    LibraryCheckItem(
                        key = keyOf(r),
                        type = r.type,
                        id = r.downloadId ?: r.id,
                        title = r.title,
                        artist = r.artist ?: "",
                        album = r.album ?: "",
                        duration = r.duration,
                    )
                }
                val check = try {
                    apiCall { api().libraryCheck(LibraryCheckRequest(items)) }
                } catch (_: Exception) { null }
                val inLibrary = check?.results?.mapValues { entry ->
                    entry.value.owned == true || (entry.value.ownedCount ?: 0) > 0 || (entry.value.albumsOwned ?: 0) > 0
                } ?: emptyMap()
                _state.value = _state.value.copy(
                    results = resp.results,
                    loading = false,
                    inLibrary = inLibrary,
                )
                // keep check result indirectly by storing search results; UI can call libraryCheck lazily later
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Search failed")
            }
        }
    }
}
