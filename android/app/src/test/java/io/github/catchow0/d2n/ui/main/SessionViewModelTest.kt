package io.github.catchow0.d2n.ui.main

import io.github.catchow0.d2n.data.ApiProvider
import io.github.catchow0.d2n.data.Profile
import io.github.catchow0.d2n.data.RequestHeaders
import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.data.buildHttpClient
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class SessionViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val server = MockWebServer()
    private val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://music.example/", token = "d2n_x"))
    private lateinit var vm: SessionViewModel

    @Before
    fun setUp() {
        server.start()
        val client = buildHttpClient(null, { store.state.value.let { RequestHeaders(it.token, it.profile) } }, "D2N/test") {
            vm.onUnauthorized()
        }
        val api = ApiProvider(client).forServer(server.url("/"))
        vm = SessionViewModel({ api }, store)
    }

    @After
    fun tearDown() = server.close()

    private fun info(profile: String = "nd1") = MockResponse.Builder().code(200).addHeader("Content-Type", "application/json").body(
        """{"service":"deezer-to-navidrome","api":1,"version":"1.18.0","username":"admin","auth_disabled":false,
        "profile":"$profile","profiles":[{"id":"nd1","label":"Me","is_default":true},{"id":"nd2","label":"Bob","is_default":false}]}""",
    ).build()

    private fun settled(check: (SessionViewModel.UiState) -> Boolean) = runBlocking { withTimeout(5_000) { vm.state.first(check) } }

    @Test
    fun `choosing a profile sends it with the next requests`() {
        server.enqueue(info())
        server.enqueue(info("nd2"))
        vm.refresh()
        settled { it.selected?.id == "nd1" }
        vm.select("nd2")
        assertEquals(Profile("nd2", "Bob", isDefault = false), settled { it.selected?.id == "nd2" && !it.loading }.selected)
        assertNull(server.takeRequest().headers["X-Navidrome-Account"])
        assertEquals("nd2", server.takeRequest().headers["X-Navidrome-Account"])
        assertEquals("nd2", store.state.value.profile)
    }

    @Test
    fun `a profile that no longer exists falls back to the default`() {
        runBlocking { store.setProfile("nd9") }
        server.enqueue(info())
        vm.refresh()
        val state = settled { !it.loading }
        assertEquals("nd1", state.selected?.id)
        assertEquals("nd1", store.state.value.profile)
        assertEquals("1.18.0", state.serverVersion)
    }

    @Test
    fun `a 401 signs the app out`() {
        server.enqueue(
            MockResponse.Builder().code(401).addHeader("Content-Type", "application/json")
                .body("""{"error":{"code":"unauthorized","message":"Sign in first: send this device's token."}}""").build(),
        )
        vm.refresh()
        assertEquals(SIGNED_OUT, settled { it.signedOutMessage != null }.signedOutMessage)
        runBlocking { withTimeout(5_000) { store.state.first { it.token == null } } }
    }

    @Test
    fun `returning to the app reads the profiles again`() {
        server.enqueue(info())
        server.enqueue(info())
        vm.onStart()
        settled { !it.loading && it.selected != null }
        vm.onStart()
        runBlocking { withTimeout(5_000) { while (server.requestCount < 2) kotlinx.coroutines.delay(20) } }
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `the server coming back reads the profiles again`() {
        vm.onOnline(true)
        assertEquals(0, server.requestCount)
        server.enqueue(info())
        vm.onOnline(false)
        vm.onOnline(true)
        assertEquals("nd1", settled { !it.loading && it.selected != null }.selected?.id)
        assertEquals(1, server.requestCount)
    }
}
