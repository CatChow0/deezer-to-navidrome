package io.github.catchow0.d2n.data

import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test

/**
 * Phase 9: when the server cannot be reached, a read it answered before comes
 * back from the cache, for the same profile only, and the app is told so.
 */
class OfflineCacheTest {
    private val server = MockWebServer()
    private var headers = RequestHeaders(token = "d2n_x", profile = "nd1")
    private var saved = 0
    private var offline = false
    private lateinit var cacheDir: File
    private lateinit var api: D2nApi

    @Before
    fun setUp() {
        server.start()
        cacheDir = Files.createTempDirectory("d2n-cache").toFile()
        val client = buildHttpClient(cacheDir, { headers }, "D2N/test (Android 0)", onSaved = { saved++ }, offline = { offline })
        api = ApiProvider(client).forServer(server.url("/d2n/"))
    }

    @After
    fun tearDown() {
        server.close()
        cacheDir.deleteRecursively()
    }

    /** As the server answers a read: its ETag, and one copy per profile. */
    private fun read(body: String) = MockResponse.Builder().code(200).body(body)
        .addHeader("Content-Type", "application/json")
        .addHeader("ETag", "\"${body.hashCode()}\"")
        .addHeader("Cache-Control", "private, max-age=0")
        .addHeader("Vary", "X-Navidrome-Account")
        .build()

    private val stats = """{"count":120,"albums":12,"artists":5,"generated_at":1731200000.5}"""

    @Test
    fun `a saved read stands in for the server, and the app is told`() = runBlocking {
        server.enqueue(read(stats))
        val live = apiCall { api.libraryStats() }
        assertEquals(0, saved)
        server.close()
        val offline = apiCall { api.libraryStats() }
        assertEquals(live, offline)
        assertEquals(1, saved)
    }

    @Test
    fun `once known offline, reads skip the wait and come from the cache`() = runBlocking {
        server.enqueue(read(stats))
        val live = apiCall { api.libraryStats() }
        offline = true
        // The server would answer, but is not asked: no connection timeout per screen.
        assertEquals(live, apiCall { api.libraryStats() })
        assertEquals(1, server.requestCount)
        // Nothing saved for this one: the server is asked after all.
        server.enqueue(read("""{"notes":[],"unseen":false}"""))
        apiCall { api.notes() }
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `another profile never gets the saved copy`() = runBlocking {
        server.enqueue(read(stats))
        apiCall { api.libraryStats() }
        server.close()
        headers = headers.copy(profile = "nd2")
        assertThrows(Unreachable::class.java) { runBlocking { apiCall { api.libraryStats() } } }
        assertEquals(0, saved)
    }

    @Test
    fun `nothing saved, a change, the tasks and the probe still fail`() = runBlocking {
        server.enqueue(read("""{"tasks":[]}"""))
        server.enqueue(read("""{"service":"deezer-to-navidrome","api":1,"auth":"required"}"""))
        apiCall { api.tasks() }
        apiCall { api.authStatus() }
        server.close()
        assertThrows(Unreachable::class.java) { runBlocking { apiCall { api.libraryStats() } } }
        assertThrows(Unreachable::class.java) { runBlocking { apiCall { api.refreshLibrary() } } }
        assertThrows(Unreachable::class.java) { runBlocking { apiCall { api.tasks() } } }
        assertThrows(Unreachable::class.java) { runBlocking { apiCall { api.authStatus() } } }
        assertEquals(0, saved)
    }
}
