package io.github.catchow0.d2n.ui.activity

import io.github.catchow0.d2n.data.TaskList
import io.github.catchow0.d2n.data.TaskSummary
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.ui.main.Reachability
import java.io.IOException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

class ActivityViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val scope = CoroutineScope(SupervisorJob() + main.dispatcher)
    private val reachability = Reachability({ false }, scope)
    private val api = FakeD2nApi()

    @After
    fun tearDown() = scope.cancel()

    @Test
    fun `tasks are listed newest first`() {
        api.onTasks = {
            TaskList(listOf(TaskSummary("a", "Old", createdAt = 1.0), TaskSummary("b", "New", createdAt = 3.0), TaskSummary("c", "Middle", createdAt = 2.0)))
        }
        val vm = ActivityViewModel({ api }, reachability)
        vm.refresh()
        assertEquals(listOf("b", "c", "a"), vm.state.value.tasks.map { it.id })
        assertFalse(vm.state.value.loading)
    }

    @Test
    fun `a lost server is reported`() {
        api.onTasks = { throw Unreachable(IOException("timeout")) }
        val vm = ActivityViewModel({ api }, reachability)
        vm.refresh()
        assertFalse(reachability.online.value)
        assertFalse(vm.state.value.loading)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun `it follows the server only while it is on screen`() = runTest(main.dispatcher) {
        var asked = 0
        api.onTasks = {
            asked++
            TaskList(emptyList())
        }
        val vm = ActivityViewModel({ api }, reachability)
        vm.start()
        runCurrent()
        assertEquals(1, asked)
        advanceTimeBy(5_000)
        runCurrent()
        assertEquals(2, asked)
        vm.stop()
        advanceTimeBy(60_000)
        runCurrent()
        assertEquals(2, asked)
        vm.start()
        runCurrent()
        assertEquals(3, asked)
        vm.stop()
    }
}
