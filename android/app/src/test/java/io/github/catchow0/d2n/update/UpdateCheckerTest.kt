package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.ApiProvider
import io.github.catchow0.d2n.data.RequestHeaders
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.data.buildHttpClient
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test

class UpdateCheckerTest {
    private val server = MockWebServer()
    private val store = FakeSettingsStore()
    private val own = BuildIdentity(11800, "1.18.0", "abc1234", "2026-11-09T12:00:00Z")
    private val start = 1_800_000_000_000L
    private var clock = start
    private lateinit var checker: UpdateChecker

    @Before
    fun setUp() {
        server.start()
        val api = ApiProvider(buildHttpClient(null, { RequestHeaders("d2n_x", null) }, "D2N/test")).forServer(server.url("/"))
        checker = UpdateChecker({ api }, store, own, { clock })
    }

    @After
    fun tearDown() = server.close()

    private fun newer() = MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").body(
        """{"available":true,"version":"1.18.1","version_code":11801,
        "build":{"commit":"def5678","built_at":"2026-11-10T09:00:00Z"},"size":8273680,"sha256":"ab"}""",
    ).build()

    @Test
    fun `a check within six hours is skipped`() = runBlocking {
        server.enqueue(newer())
        assertEquals(11801, checker.check()?.versionCode)
        clock = start + 5 * 3_600_000L
        assertNull(checker.check())
        assertEquals(1, server.requestCount)
        // Past six hours, it asks again.
        server.enqueue(newer())
        clock = start + 6 * 3_600_000L + 1
        assertNotNull(checker.check())
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `a forced check always asks`() = runBlocking {
        server.enqueue(newer())
        server.enqueue(newer())
        checker.check()
        clock = start + 60_000L
        assertEquals(11801, checker.check(force = true)?.versionCode)
        assertEquals(2, server.requestCount)
        assertEquals("/api/v1/app", server.takeRequest().url.encodedPath)
    }

    @Test
    fun `the time of the check is saved`() {
        runBlocking {
            server.enqueue(newer())
            checker.check()
            assertEquals(start, store.state.value.lastUpdateCheck)
        }
        // A check that did not reach the server leaves the next one free to try.
        server.close()
        clock = start + 7 * 3_600_000L
        assertThrows(Unreachable::class.java) { runBlocking { checker.check() } }
        assertEquals(start, store.state.value.lastUpdateCheck)
    }

    @Test
    fun `a server without app updates offers nothing`() = runBlocking {
        // A server older than 1.18.0 has no /api/v1/app.
        server.enqueue(
            MockResponse.Builder().code(404).addHeader("Content-Type", "application/json")
                .body("""{"error":{"code":"not_found","message":"No such resource."}}""").build(),
        )
        assertNull(checker.check())
        assertEquals(start, store.state.value.lastUpdateCheck)
    }
}
