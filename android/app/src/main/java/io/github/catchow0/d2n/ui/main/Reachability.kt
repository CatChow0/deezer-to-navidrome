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
 *
 * A call reports when it started ([now]): one sent before the server answered
 * again (waiting out its connection timeout meanwhile) is old news, and does
 * not turn the banner back on.
 */
class Reachability(
    private val probe: suspend () -> Boolean,
    private val scope: CoroutineScope,
    private val everyMillis: Long = 30_000,
    private val clock: () -> Long = System::nanoTime,
) {
    private val _online = MutableStateFlow(true)
    val online: StateFlow<Boolean> = _online
    private var checking: Job? = null

    @Volatile
    private var answeredAt = Long.MIN_VALUE

    /** The time to give [reportFailure] for a call starting now. */
    fun now(): Long = clock()

    // Called from OkHttp's threads too: two failures at once must start one check.
    @Synchronized
    fun reportFailure(startedAt: Long = now()) {
        if (startedAt < answeredAt) return
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
        probe().also { if (it) answeredAt = clock() }
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        false
    }
}
