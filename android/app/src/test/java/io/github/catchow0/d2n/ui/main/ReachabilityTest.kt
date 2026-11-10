package io.github.catchow0.d2n.ui.main

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ReachabilityTest {
    @Test
    fun `losing the server turns the banner on`() = runTest {
        val reachability = Reachability({ false }, backgroundScope)
        assertTrue(reachability.online.value)
        reachability.reportFailure()
        assertFalse(reachability.online.value)
    }

    @Test
    fun `Retry brings it back`() = runTest {
        var up = false
        val reachability = Reachability({ up }, backgroundScope)
        reachability.reportFailure()
        runCurrent()
        up = true
        reachability.retryNow()
        runCurrent()
        assertTrue(reachability.online.value)
    }

    @Test
    fun `a call sent before the server came back does not turn the banner on again`() = runTest {
        var up = false
        var time = 0L
        val reachability = Reachability({ up }, backgroundScope, clock = { time })
        reachability.reportFailure()
        runCurrent()
        // A call starts while the server is down, and waits on its connection.
        time = 10
        val slowCall = reachability.now()
        time = 20
        up = true
        reachability.retryNow()
        runCurrent()
        assertTrue(reachability.online.value)
        // Its failure arrives now: old news.
        time = 30
        reachability.reportFailure(slowCall)
        assertTrue(reachability.online.value)
        // A call sent after the server came back is news.
        reachability.reportFailure(reachability.now())
        assertFalse(reachability.online.value)
    }

    @Test
    fun `while offline it checks every 30 seconds`() = runTest {
        val answers = ArrayDeque(listOf(false, false, true))
        var probes = 0
        val reachability = Reachability({ probes++; answers.removeFirst() }, backgroundScope)
        reachability.reportFailure()
        advanceTimeBy(59_000)
        runCurrent()
        assertEquals(2, probes)
        assertFalse(reachability.online.value)
        advanceTimeBy(1_000)
        runCurrent()
        assertEquals(3, probes)
        assertTrue(reachability.online.value)
        // Back online: no more checks.
        advanceTimeBy(120_000)
        runCurrent()
        assertEquals(3, probes)
    }
}
