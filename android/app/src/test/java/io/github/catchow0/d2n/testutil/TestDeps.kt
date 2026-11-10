package io.github.catchow0.d2n.testutil

import io.github.catchow0.d2n.ui.common.AppEvents
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.main.Reachability
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

/** What a screen's ViewModel gets, with the messages it posts in [notices].
 * [scope] must start its coroutines at once (an unconfined test dispatcher). */
class TestDeps(scope: CoroutineScope, val api: FakeD2nApi = FakeD2nApi()) {
    val profile = MutableStateFlow<String?>("nd1")
    val events = AppEvents()
    val reachability = Reachability({ false }, scope, everyMillis = Long.MAX_VALUE)
    val notices = mutableListOf<Notice>()
    val deps = ScreenDeps({ api }, profile, reachability, events)

    init {
        scope.launch { events.notices.collect { notices += it } }
    }

    /** Answers [name] with [value], whatever it is sent. */
    fun reply(name: String, value: Any?) {
        api.replies[name] = { value }
    }
}
