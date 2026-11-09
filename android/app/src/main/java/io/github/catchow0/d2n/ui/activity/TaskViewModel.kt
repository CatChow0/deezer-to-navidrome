package io.github.catchow0.d2n.ui.activity

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.TaskEvent
import io.github.catchow0.d2n.data.TaskSummary
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.tasks.TaskUpdate
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.HttpUrl

const val NOT_CANCELLABLE = "This task cannot be stopped."
const val STOPPING = "Stopping the task…"
private const val KEPT_EVENTS = 200

/**
 * One task, live: its status as it changes, and how it ended. Only status
 * events are shown: a scan's row updates are for the playlist's table, as on
 * the web. The stream follows the screen: paused in the background, it
 * resumes after the last event seen.
 */
class TaskViewModel(
    private val follow: (HttpUrl, String, Int) -> Flow<TaskUpdate>,
    private val api: () -> D2nApi,
    private val base: HttpUrl,
    private val taskId: String,
) : ViewModel() {
    data class UiState(
        val summary: TaskSummary? = null,
        val events: List<TaskEvent> = emptyList(),
        val ended: TaskUpdate.Ended? = null,
        val notice: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    // Declared before init, which starts following: Kotlin initializes in order.
    private var following: Job? = null
    private var lastSeen = -1

    init {
        viewModelScope.launch {
            try {
                val summary = apiCall { api().task(taskId) }.task
                _state.update { it.copy(summary = summary) }
            } catch (e: ApiFailure) {
                // The events still come; the title waits for them.
            }
        }
        resume()
    }

    fun resume() {
        if (following?.isActive == true || _state.value.ended != null) return
        following = viewModelScope.launch {
            follow(base, taskId, lastSeen)
                .catch { e ->
                    if (e is CancellationException) throw e
                    emit(TaskUpdate.Ended(true, e.message ?: "The task could not be followed."))
                }
                .collect { update ->
                    when (update) {
                        is TaskUpdate.Event -> {
                            lastSeen = maxOf(lastSeen, update.event.index)
                            if (update.event.type == "status") {
                                _state.update { it.copy(events = (it.events + update.event).takeLast(KEPT_EVENTS)) }
                            }
                        }
                        is TaskUpdate.Ended -> _state.update { it.copy(ended = update) }
                    }
                }
        }
    }

    fun pause() {
        following?.cancel()
        following = null
    }

    fun cancel() {
        viewModelScope.launch {
            val notice = try {
                apiCall { api().cancelTask(taskId) }
                STOPPING
            } catch (e: ApiError) {
                if (e.code == "not_cancellable") NOT_CANCELLABLE else e.message
            } catch (e: ApiFailure) {
                e.message
            }
            _state.update { it.copy(notice = notice) }
        }
    }
}
