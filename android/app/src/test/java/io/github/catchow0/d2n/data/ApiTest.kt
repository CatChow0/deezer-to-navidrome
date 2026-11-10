package io.github.catchow0.d2n.data

import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** The client against a fake server under a sub-path, as an install behind
 * https://host/d2n/ would be: every call must keep that path. */
class ApiTest {
    private val server = MockWebServer()
    private var headers = RequestHeaders(token = "d2n_x", profile = "nd2")
    private var unauthorized = 0
    private lateinit var cacheDir: File
    private lateinit var api: D2nApi

    @Before
    fun setUp() {
        server.start()
        cacheDir = Files.createTempDirectory("d2n-cache").toFile()
        val client = buildHttpClient(cacheDir, { headers }, "D2N/test (Android 0)") { unauthorized++ }
        api = ApiProvider(client).forServer(server.url("/d2n/"))
    }

    @After
    fun tearDown() {
        server.close()
        cacheDir.deleteRecursively()
    }

    private fun json(code: Int, body: String, vararg extra: Pair<String, String>): MockResponse {
        val builder = MockResponse.Builder().code(code).body(body).addHeader("Content-Type", "application/json")
        extra.forEach { (name, value) -> builder.addHeader(name, value) }
        return builder.build()
    }

    private val info = """{"service":"deezer-to-navidrome","api":1,"version":"1.18.0","username":"admin",
        "auth_disabled":false,"profile":"nd1","profiles":[{"id":"nd1","label":"Me","is_default":true},
        {"id":"nd2","label":"Bob","is_default":false}]}"""

    @Test
    fun `signing in returns the token and the device`() = runBlocking {
        server.enqueue(json(201, """{"token":"d2n_x","device":{"id":"d1","name":"Pixel"},"username":"admin"}"""))
        val signed = apiCall { api.login(Credentials("admin", "secret", "Pixel")) }
        assertEquals(SignedIn("d2n_x", DeviceInfo("d1", "Pixel"), "admin"), signed)
        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals("/d2n/api/v1/auth/login", recorded.url.encodedPath)
        assertTrue(recorded.body!!.utf8().contains("\"device\":\"Pixel\""))
    }

    @Test
    fun `a wrong password raises wrong_credentials`() {
        server.enqueue(json(401, """{"error":{"code":"wrong_credentials","message":"Wrong username or password."}}"""))
        val error = assertThrows(ApiError::class.java) {
            runBlocking { apiCall { api.login(Credentials("admin", "nope", "Pixel")) } }
        }
        assertEquals(401, error.status)
        assertEquals("wrong_credentials", error.code)
        assertEquals("Wrong username or password.", error.message)
        assertNull(error.retryAfterSeconds)
        // A wrong password is not a revoked token.
        assertEquals(0, unauthorized)
    }

    @Test
    fun `too many attempts carries the wait`() {
        // Without retry_after in the body, the header gives the wait.
        server.enqueue(json(429, """{"error":{"code":"too_many_attempts","message":"Too many attempts."}}""", "Retry-After" to "30"))
        val error = assertThrows(ApiError::class.java) {
            runBlocking { apiCall { api.login(Credentials("admin", "nope", "Pixel")) } }
        }
        assertEquals("too_many_attempts", error.code)
        assertEquals(30, error.retryAfterSeconds)
    }

    @Test
    fun `every request carries the token and the profile`() = runBlocking {
        server.enqueue(json(200, """{"service":"deezer-to-navidrome","api":1,"auth":"required"}"""))
        server.enqueue(json(200, info))
        server.enqueue(json(200, """{"service":"deezer-to-navidrome","api":1,"auth":"disabled"}"""))
        apiCall { api.authStatus() }
        apiCall { api.info() }
        headers = RequestHeaders(token = null, profile = null)
        apiCall { api.authStatus() }
        repeat(2) {
            val recorded = server.takeRequest()
            assertEquals("Bearer d2n_x", recorded.headers["Authorization"])
            assertEquals("nd2", recorded.headers["X-Navidrome-Account"])
            assertEquals("D2N/test (Android 0)", recorded.headers["User-Agent"])
        }
        val signedOut = server.takeRequest()
        assertNull(signedOut.headers["Authorization"])
        assertNull(signedOut.headers["X-Navidrome-Account"])
    }

    @Test
    fun `a read the server says is unchanged comes from the cache`() = runBlocking {
        server.enqueue(json(200, info, "ETag" to "\"abc\"", "Cache-Control" to "private, max-age=0"))
        server.enqueue(MockResponse.Builder().code(304).addHeader("ETag", "\"abc\"").build())
        val first = apiCall { api.info() }
        val second = apiCall { api.info() }
        assertEquals(first, second)
        assertEquals(2, second.profiles.size)
        server.takeRequest()
        assertEquals("\"abc\"", server.takeRequest().headers["If-None-Match"])
    }

    @Test
    fun `unknown fields are ignored`() = runBlocking {
        server.enqueue(json(200, info.replace("\"api\":1,", "\"api\":1,\"future\":{\"x\":[1,2]},")))
        val parsed = apiCall { api.info() }
        assertEquals("1.18.0", parsed.version)
        assertEquals(Profile("nd2", "Bob", isDefault = false), parsed.profiles[1])
        assertTrue(parsed.profiles[0].isDefault)
    }

    @Test
    fun `a server that is gone raises Unreachable`() {
        server.close()
        assertThrows(Unreachable::class.java) { runBlocking { apiCall { api.authStatus() } } }
    }

    @Test
    fun `a revoked token is reported, a refused sign-in is not`() = runBlocking {
        server.enqueue(json(401, """{"error":{"code":"unauthorized","message":"Sign in first: send this device's token."}}"""))
        server.enqueue(json(401, """{"error":{"code":"wrong_credentials","message":"Wrong username or password."}}"""))
        server.enqueue(json(401, """{"error":{"code":"unauthorized","message":"Sign in first."}}"""))
        runCatching { apiCall { api.info() } }
        assertEquals(1, unauthorized)
        runCatching { apiCall { api.login(Credentials("admin", "nope", "Pixel")) } }
        runCatching { apiCall { api.setup(Credentials("admin", "short", "Pixel")) } }
        assertEquals(1, unauthorized)
    }
}
