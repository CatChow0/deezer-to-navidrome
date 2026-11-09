package io.github.catchow0.d2n.ui.signin

import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ServerProbeTest {
    private val server = MockWebServer()
    private val client = OkHttpClient()

    @Before
    fun setUp() = server.start()

    @After
    fun tearDown() = server.close()

    private fun probe(response: MockResponse): ServerProbe {
        server.enqueue(response)
        return runBlocking { probeServer(client, server.url("/d2n/")) }
    }

    private fun json(code: Int, body: String) =
        MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    @Test
    fun `this app's status is recognised`() {
        assertEquals(ServerProbe.Required, probe(json(200, """{"service":"deezer-to-navidrome","api":1,"auth":"required"}""")))
        assertEquals(ServerProbe.Setup, probe(json(200, """{"service":"deezer-to-navidrome","api":1,"auth":"setup"}""")))
        assertEquals(ServerProbe.Disabled, probe(json(200, """{"service":"deezer-to-navidrome","api":1,"auth":"disabled"}""")))
        assertEquals("/d2n/api/v1/auth/status", server.takeRequest().url.encodedPath)
    }

    @Test
    fun `a redirect elsewhere is a login page`() {
        val redirect = MockResponse.Builder().code(302).addHeader("Location", "https://auth.example/?rd=https://music.example/").build()
        assertTrue(probe(redirect) is ServerProbe.NotThisServer)
        // Not followed: the login page was never asked for.
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `an html answer is a login page`() {
        val page = MockResponse.Builder().code(200).addHeader("Content-Type", "text/html").body("<html><body>Sign in</body></html>").build()
        assertTrue(probe(page) is ServerProbe.NotThisServer)
    }

    @Test
    fun `another JSON service is not this app`() =
        assertTrue(probe(json(200, """{"service":"other"}""")) is ServerProbe.NotThisServer)

    @Test
    fun `an older server is told to update`() =
        assertEquals(ServerProbe.TooOld, probe(json(401, """{"ok":false,"error":"Sign in first"}""")))
}
