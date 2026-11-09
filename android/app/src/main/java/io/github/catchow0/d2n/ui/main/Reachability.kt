package io.github.catchow0.d2n.ui.main

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * Whether the server answers. A call that cannot reach it reports it: the app
 * shows its banner, checks again at once, then every [everyMillis], until the
 * server answers.
 */
class Reachability(
    private val probe: suspend () -> Boolean,
    private val scope: CoroutineScope,
    private val everyMillis: Long = 30_000,
) {
    private val _online = MutableStateFlow(true)
    val online: StateFlow<Boolean> = _online
    private var checking: Job? = null

    fun reportFailure() {
        _online.value = false
        if (checking?.isActive == true) return
        checking = scope.launch {
            while (true) {
                if (answers()) {
                    _online.value = true
                    return@launch
                }
                delay(everyMillis)
            }
        }
    }

    fun retryNow() {
        scope.launch { if (answers()) _online.value = true }
    }

    private suspend fun answers(): Boolean = try {
        probe()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        false
    }
}
