package io.github.catchow0.d2n.ui.common

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.ui.main.Reachability
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** A message for the snackbar. With [taskId], it offers to follow the task. */
data class Notice(val message: String, val taskId: String? = null, val error: Boolean = false)

/** What the screens tell the app's shell: messages, and tasks they started. */
class AppEvents {
    private val _notices = MutableSharedFlow<Notice>(extraBufferCapacity = 16)
    val notices: SharedFlow<Notice> = _notices

    fun post(notice: Notice) {
        _notices.tryEmit(notice)
    }

    /** The notes of a newer version are not read yet: a dot on More and on New. */
    val unseenNotes = MutableStateFlow(false)
}

/** What every screen's ViewModel gets from the app. */
class ScreenDeps(
    val api: () -> D2nApi,
    /** The profile this phone shows; a change reloads the screens. */
    val profile: StateFlow<String?>,
    val reachability: Reachability,
    val events: AppEvents,
)

/** Something read from the server. A refresh keeps [value] on screen; [error]
 * is what went wrong with the last read. */
data class Remote<out T>(val value: T? = null, val loading: Boolean = true, val error: String? = null) {
    val refreshing: Boolean get() = loading && value != null
}

abstract class D2nViewModel(protected val deps: ScreenDeps) : ViewModel() {
    private val _busy = MutableStateFlow<Set<String>>(emptySet())

    /** The actions running now, by their key: their button waits. */
    val busy: StateFlow<Set<String>> = _busy

    private var shown = false

    /**
     * The screen is in front again (back from a task, from another app): what
     * it shows may have changed on the server. The first time, its own read
     * is already running. The flag lives here because a screen's composition
     * is recreated each time it comes back.
     */
    fun onScreenResumed(refresh: () -> Unit) {
        if (shown) refresh() else shown = true
    }

    private var watching: Job? = null

    /**
     * While the screen is in front: when a task that was running ends (a scan,
     * a download, a generation, from here or from anywhere), [refresh] runs, as
     * the web's rows follow their task. The list is read every 3 s while
     * something runs, every 15 s otherwise.
     */
    fun watchTasks(refresh: () -> Unit) {
        if (watching?.isActive == true) return
        watching = viewModelScope.launch {
            var running = emptySet<String>()
            while (true) {
                val now = try {
                    call { tasks() }.tasks.filter { !it.done }.map { it.id }.toSet()
                } catch (e: ApiFailure) {
                    running
                }
                if ((running - now).isNotEmpty()) refresh()
                running = now
                delay(if (now.isEmpty()) IDLE_WATCH_MILLIS else BUSY_WATCH_MILLIS)
            }
        }
    }

    fun stopWatchingTasks() {
        watching?.cancel()
        watching = null
    }

    /** A task was just started here: look at once, not in 15 s. */
    protected fun taskStarted(refresh: () -> Unit) {
        if (watching == null) return
        stopWatchingTasks()
        watchTasks(refresh)
    }

    private companion object {
        const val BUSY_WATCH_MILLIS = 3_000L
        const val IDLE_WATCH_MILLIS = 15_000L
    }

    /** Reads again each time the profile changes, starting now. */
    protected fun followProfile(load: suspend () -> Unit) {
        viewModelScope.launch { deps.profile.collectLatest { load() } }
    }

    /** A call to the server. Unreachable also lights the app's banner. */
    protected suspend fun <T> call(block: suspend D2nApi.() -> T): T = try {
        apiCall { deps.api().block() }
    } catch (e: Unreachable) {
        deps.reachability.reportFailure()
        throw e
    }

    /** Fills a [Remote] from the server. */
    protected suspend fun <T> MutableStateFlow<Remote<T>>.fill(block: suspend D2nApi.() -> T) {
        update { it.copy(loading = true, error = null) }
        try {
            val read = call(block)
            value = Remote(read, loading = false)
        } catch (e: ApiFailure) {
            update { it.copy(loading = false, error = e.message) }
        }
    }

    /**
     * Something the user asked for. Its failure goes to the snackbar; [done]
     * says what to tell on success (a task ID offers to follow it).
     */
    protected fun <T> act(
        key: String,
        block: suspend D2nApi.() -> T,
        done: (T) -> Notice? = { null },
        after: suspend (T) -> Unit = {},
    ): Job? {
        if (key in _busy.value) return null
        _busy.update { it + key }
        return viewModelScope.launch {
            try {
                val result = call(block)
                done(result)?.let(deps.events::post)
                after(result)
            } catch (e: ApiFailure) {
                deps.events.post(Notice(e.message ?: "That did not work.", error = true))
            } finally {
                _busy.update { it - key }
            }
        }
    }

    protected fun notify(message: String, taskId: String? = null) = deps.events.post(Notice(message, taskId))
}
