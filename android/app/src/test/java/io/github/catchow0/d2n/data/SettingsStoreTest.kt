package io.github.catchow0.d2n.data

import io.github.catchow0.d2n.testutil.MemoryDataStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SettingsStoreTest {
    /** Stands in for the Keystore: what it seals reads backwards. */
    private object ReversingBox : SecretBox {
        override fun seal(plain: String) = plain.reversed()
        override fun open(sealed: String) = sealed.reversed()
        override fun reset() = Unit
    }

    /** A keyset moved to another phone without its Keystore key: nothing seals
     * until it is reset. */
    private class MovedBox : SecretBox {
        var broken = true
        var resets = 0
        override fun seal(plain: String): String = if (broken) throw IllegalStateException("no master key") else plain.reversed()
        override fun open(sealed: String): String = if (broken) throw IllegalStateException("no master key") else sealed.reversed()
        override fun reset() {
            resets++
            broken = false
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val dataStore = MemoryDataStore()
    private val store = DataStoreSettingsStore(dataStore, ReversingBox, scope)

    @After
    fun tearDown() = scope.cancel()

    private suspend fun settled(check: (StoredSession) -> Boolean) = withTimeout(5_000) { store.state.first { it.ready && check(it) } }

    @Test
    fun `the token is stored sealed`() = runBlocking {
        store.setServer("https://host.example/", authDisabled = false)
        store.setToken("d2n_secret")
        assertEquals("d2n_secret", settled { it.token != null }.token)
        val raw = dataStore.data.first().asMap().values.map(Any::toString)
        assertFalse(raw.contains("d2n_secret"))
        assertTrue(raw.contains("terces_n2d"))
    }

    @Test
    fun `a new server forgets the token and the profile`() = runBlocking {
        store.setServer("https://a.example/", authDisabled = false)
        store.setToken("d2n_a")
        store.setProfile("nd2")
        store.setServer("https://b.example/", authDisabled = false)
        val moved = settled { it.serverUrl == "https://b.example/" }
        assertNull(moved.token)
        assertNull(moved.profile)
        // The same address again keeps the session.
        store.setToken("d2n_b")
        store.setServer("https://b.example/", authDisabled = true)
        val same = settled { it.authDisabled }
        assertEquals("d2n_b", same.token)
    }

    @Test
    fun `a key that no longer opens is replaced and the sign-in kept`() = runBlocking {
        val box = MovedBox()
        val moved = DataStoreSettingsStore(MemoryDataStore(), box, scope)
        moved.setToken("d2n_new")
        assertEquals(1, box.resets)
        assertEquals("d2n_new", withTimeout(5_000) { moved.state.first { it.token != null } }.token)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun `a setter returns once the session shows it`() = runTest {
        val waiting = DataStoreSettingsStore(MemoryDataStore(), ReversingBox, backgroundScope)
        waiting.setProfile("nd2")
        assertEquals("nd2", waiting.state.value.profile)
        waiting.setServer("https://music.example/", authDisabled = true)
        assertEquals("https://music.example/", waiting.state.value.serverUrl)
        assertTrue(waiting.state.value.authDisabled)
    }
}
