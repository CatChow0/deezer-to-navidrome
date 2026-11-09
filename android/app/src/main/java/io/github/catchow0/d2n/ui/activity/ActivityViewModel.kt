package io.github.catchow0.d2n.ui.activity

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.TaskSummary
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.ui.main.Reachability
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The tasks the web's Activity lists: scans, downloads, rebuilds. */
class ActivityViewModel(
    private val api: () -> D2nApi,
    private val reachability: Reachability,
) : ViewModel() {
    data class UiState(
        val tasks: List<TaskSummary> = emptyList(),
        val loading: Boolean = true,
        val refreshing: Boolean = false,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    private var polling: Job? = null

    /** On screen: the list, then again every 5 s, until [stop]. */
    fun start() {
        if (polling?.isActive == true) return
        polling = viewModelScope.launch {
            while (true) {
                load()
                delay(POLL_MILLIS)
            }
        }
    }

    fun stop() {
        polling?.cancel()
        polling = null
    }

    /** [pulled]: the user pulled the list, which shows the spinner. */
    fun refresh(pulled: Boolean = false) {
        if (pulled) _state.update { it.copy(refreshing = true) }
        viewModelScope.launch { load() }
    }

    private suspend fun load() {
        try {
            val tasks = apiCall { api().tasks() }.tasks.sortedByDescending { it.createdAt ?: 0.0 }
            _state.update { it.copy(tasks = tasks, loading = false, refreshing = false, error = null) }
        } catch (e: Unreachable) {
            reachability.reportFailure()
            _state.update { it.copy(loading = false, refreshing = false) }
        } catch (e: ApiFailure) {
            _state.update { it.copy(loading = false, refreshing = false, error = e.message) }
        }
    }

    private companion object {
        const val POLL_MILLIS = 5_000L
    }
}
