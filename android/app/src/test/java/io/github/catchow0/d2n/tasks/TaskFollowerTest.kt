package io.github.catchow0.d2n.tasks

import io.github.catchow0.d2n.data.ApiProvider
import io.github.catchow0.d2n.data.RequestHeaders
import io.github.catchow0.d2n.data.buildHttpClient
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.HttpUrl
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class TaskFollowerTest {
    private val server = MockWebServer()
    private lateinit var base: HttpUrl
    private lateinit var follower: TaskFollower

    @Before
    fun setUp() {
        server.start()
        base = server.url("/")
        val client = buildHttpClient(null, { RequestHeaders("d2n_x", null) }, "D2N/test")
        val provider = ApiProvider(client)
        follower = TaskFollower(client, provider::forServer, pause = {})
    }

    @After
    fun tearDown() = server.close()

    private fun stream(body: String) =
        MockResponse.Builder().code(200).addHeader("Content-Type", "text/event-stream").body(body).build()

    private fun event(id: Int?, message: String, done: Boolean = false, error: Boolean = false): String {
        val data = """{"type":"status","message":"$message","progress":${if (done) 100 else 10},"done":$done,"error":$error}"""
        return (if (id != null) "id: $id\n" else "") + "data: $data\n\n"
    }

    private fun summary(updates: List<TaskUpdate>) = updates.map {
        when (it) {
            is TaskUpdate.Event -> "event ${it.event.index} ${it.event.message}"
            is TaskUpdate.Ended -> "ended error=${it.error} ${it.message}"
        }
    }

    @Test
    fun `events arrive in order and the flow ends with the task`() = runBlocking {
        server.enqueue(stream("retry: 1500\n\n" + event(0, "one") + event(1, "Finished", done = true)))
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        assertEquals(listOf("event 0 one", "event 1 Finished", "ended error=false Finished"), summary(updates))
        val request = server.takeRequest()
        assertEquals("/api/v1/tasks/t1/stream", request.url.encodedPath)
        assertNull(request.headers["Last-Event-ID"])
    }

    @Test
    fun `after a cut it resumes from the last event`() = runBlocking {
        // The first segment ends without the task being done, as the server's 45 s segments do.
        server.enqueue(stream("retry: 1500\n\n" + event(0, "one") + event(1, "two")))
        server.enqueue(stream(event(2, "Done", done = true)))
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        assertEquals(listOf("event 0 one", "event 1 two", "event 2 Done", "ended error=false Done"), summary(updates))
        server.takeRequest()
        assertEquals("1", server.takeRequest().headers["Last-Event-ID"])
    }

    @Test
    fun `keepalives and retry lines are ignored`() = runBlocking {
        server.enqueue(stream("retry: 1500\n\n: keepalive\n\n" + event(0, "one") + ": keepalive\n\n" + event(1, "Finished", done = true)))
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        assertEquals(listOf("event 0 one", "event 1 Finished", "ended error=false Finished"), summary(updates))
    }

    @Test
    fun `when the stream keeps failing it waits for events instead`() = runBlocking {
        repeat(3) { server.enqueue(MockResponse.Builder().code(503).build()) }
        server.enqueue(
            MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").body(
                """{"task":{"id":"t1","title":"Scan","done":true},"events":[
                {"index":0,"type":"status","message":"one","done":false},
                {"index":1,"type":"status","message":"Finished","done":true}],"after":1}""",
            ).build(),
        )
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        assertEquals(listOf("event 0 one", "event 1 Finished", "ended error=false Finished"), summary(updates))
        repeat(3) { assertEquals("/api/v1/tasks/t1/stream", server.takeRequest().url.encodedPath) }
        val poll = server.takeRequest().url
        assertEquals("/api/v1/tasks/t1/events", poll.encodedPath)
        assertEquals("-1", poll.queryParameter("after"))
        assertEquals("25", poll.queryParameter("wait"))
    }

    @Test
    fun `a task the server no longer knows ends the flow`() = runBlocking {
        server.enqueue(stream("retry: 1500\n\n" + event(null, "Task not found", done = true, error = true)))
        val updates = withTimeout(5_000) { follower.follow(base, "gone").toList() }
        assertEquals(listOf("ended error=true Task not found"), summary(updates))
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `stopping early does not wait for the stream to end`() = runBlocking {
        // The first event, then a body that trickles for a long time.
        server.enqueue(
            MockResponse.Builder().code(200).addHeader("Content-Type", "text/event-stream")
                .body(event(0, "one") + ": keepalive\n\n".repeat(200))
                .throttleBody(64, 1, TimeUnit.SECONDS)
                .build(),
        )
        val started = System.nanoTime()
        val first = withTimeout(5_000) { follower.follow(base, "t1").first() }
        assertEquals("event 0 one", summary(listOf(first)).single())
        assertTrue("took ${(System.nanoTime() - started) / 1_000_000} ms", System.nanoTime() - started < 4_000_000_000L)
    }

    @Test
    fun `empty answers count as failures and lead to waiting for events`() = runBlocking {
        repeat(3) { server.enqueue(stream("retry: 1500\n\n: keepalive\n\n")) }
        server.enqueue(
            MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").body(
                """{"task":{"id":"t1","done":true},"events":[{"index":0,"type":"status","message":"Finished","done":true}],"after":0}""",
            ).build(),
        )
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        assertEquals(listOf("event 0 Finished", "ended error=false Finished"), summary(updates))
        assertEquals(4, server.requestCount)
    }

    @Test
    fun `a login page in the way ends the flow instead of failing it`() = runBlocking {
        repeat(3) { server.enqueue(MockResponse.Builder().code(503).build()) }
        server.enqueue(MockResponse.Builder().code(200).addHeader("Content-Type", "text/html").body("<html>Sign in</html>").build())
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        val ended = updates.single() as TaskUpdate.Ended
        assertTrue(ended.error)
    }

    @Test
    fun `a task forgotten while waiting for events ends the flow`() = runBlocking {
        repeat(3) { server.enqueue(MockResponse.Builder().code(503).build()) }
        server.enqueue(
            MockResponse.Builder().code(404).addHeader("Content-Type", "application/json")
                .body("""{"error":{"code":"not_found","message":"No such task."}}""").build(),
        )
        val updates = withTimeout(5_000) { follower.follow(base, "t1").toList() }
        assertEquals(listOf("ended error=true No such task."), summary(updates))
    }
}
