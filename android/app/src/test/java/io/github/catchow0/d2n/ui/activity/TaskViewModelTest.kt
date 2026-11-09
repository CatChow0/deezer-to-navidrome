package io.github.catchow0.d2n.ui.activity

import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.CancelAnswer
import io.github.catchow0.d2n.data.TaskEnvelope
import io.github.catchow0.d2n.data.TaskEvent
import io.github.catchow0.d2n.data.TaskSummary
import io.github.catchow0.d2n.tasks.TaskUpdate
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class TaskViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val base = "https://music.example/".toHttpUrl()
    private val api = FakeD2nApi().apply { onTask = { TaskEnvelope(TaskSummary(id = it, title = "Scan: Rap", cancellable = true)) } }

    private fun status(index: Int, message: String, progress: Double? = null, done: Boolean = false) =
        TaskUpdate.Event(TaskEvent(index = index, type = "status", message = message, progress = progress, done = done))

    private fun row(index: Int) = TaskUpdate.Event(TaskEvent(index = index, type = "row_update"))

    @Test
    fun `events pile up and the end is shown`() {
        val followed = mutableListOf<String>()
        val updates = flowOf(status(0, "Matching tracks", 40.0), status(1, "Done", 100.0, done = true), TaskUpdate.Ended(false, "Done"))
        val vm = TaskViewModel({ url, id, after -> followed += "$url $id $after"; updates }, { api }, base, "t1")
        val state = vm.state.value
        assertEquals("Scan: Rap", state.summary?.title)
        assertEquals(listOf(0, 1), state.events.map { it.index })
        assertEquals(TaskUpdate.Ended(false, "Done"), state.ended)
        assertEquals(listOf("https://music.example/ t1 -1"), followed)
    }

    @Test
    fun `scan rows are not shown as events`() {
        // A scan sends one row per track, for the playlist's table; the web's Activity never shows them.
        val updates = flowOf(status(0, "Matching", 10.0), row(1), row(2), status(3, "Half way", 50.0), row(4))
        val vm = TaskViewModel({ _, _, _ -> updates }, { api }, base, "t1")
        assertEquals(listOf(0, 3), vm.state.value.events.map { it.index })
        assertEquals("Half way", vm.state.value.events.last().message)
    }

    @Test
    fun `the stream stops in the background and resumes after the last event`() {
        val afters = mutableListOf<Int>()
        val vm = TaskViewModel({ _, _, after ->
            afters += after
            flow {
                if (after < 0) {
                    emit(status(0, "Matching", 10.0))
                    emit(row(1))
                } else {
                    emit(status(after + 1, "Later", 60.0))
                }
                awaitCancellation()
            }
        }, { api }, base, "t1")
        vm.pause()
        vm.resume()
        assertEquals(listOf(-1, 1), afters)
        assertEquals(listOf(0, 2), vm.state.value.events.map { it.index })
        // Following already: a second resume asks nothing.
        vm.resume()
        assertEquals(2, afters.size)
    }

    @Test
    fun `a follower that fails ends the screen instead of the app`() {
        val vm = TaskViewModel({ _, _, _ -> flow<TaskUpdate> { throw IllegalStateException("unexpected answer") } }, { api }, base, "t1")
        val ended = vm.state.value.ended
        assertTrue(ended?.error == true)
    }

    @Test
    fun `a task that cannot be stopped says so`() {
        api.onCancel = { throw ApiError(409, "not_cancellable", "This task cannot be stopped.", null) }
        val vm = TaskViewModel({ _, _, _ -> emptyFlow() }, { api }, base, "t1")
        assertNull(vm.state.value.notice)
        vm.cancel()
        assertEquals(NOT_CANCELLABLE, vm.state.value.notice)
        // Asked to stop, it says so too.
        api.onCancel = { CancelAnswer(it) }
        vm.cancel()
        assertEquals(STOPPING, vm.state.value.notice)
    }

    @Test
    fun `only the last 200 events are kept`() {
        val many = (0 until 250).map { status(it, "step $it") }
        val vm = TaskViewModel({ _, _, _ -> flowOf(*many.toTypedArray()) }, { api }, base, "t1")
        val events = vm.state.value.events
        assertEquals(200, events.size)
        assertEquals(50, events.first().index)
        assertEquals(249, events.last().index)
    }
}
