package io.github.catchow0.d2n.ui.about

import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.update.BuildIdentity
import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class AboutViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val own = BuildIdentity(11800, "1.18.0", "abc1234", "2026-11-09T12:00:00Z")
    private val api = FakeD2nApi()
    private val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://music.example/", token = "d2n_x"))

    @Test
    fun `signing out forgets the token even when the server is gone`() {
        api.onLogout = { throw Unreachable(IOException("timeout")) }
        val vm = AboutViewModel({ api }, store, own)
        vm.signOut()
        assertNull(store.state.value.token)
        assertTrue(vm.state.value.signedOut)
        // The server address stays: signing in again starts there.
        assertEquals("https://music.example/", store.state.value.serverUrl)
    }

    @Test
    fun `it shows this build`() {
        val vm = AboutViewModel({ api }, store, own)
        assertEquals("1.18.0", vm.state.value.appVersion)
        assertEquals("abc1234", vm.state.value.commit)
        assertEquals("https://music.example/", vm.state.value.server)
    }
}
