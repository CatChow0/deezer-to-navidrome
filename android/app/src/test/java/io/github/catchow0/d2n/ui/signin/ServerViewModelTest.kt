package io.github.catchow0.d2n.ui.signin

import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import okhttp3.HttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class ServerViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://old.example/", token = "d2n_old"))
    private val asked = mutableListOf<HttpUrl>()

    private fun model(answer: ServerProbe) = ServerViewModel({ url -> asked += url; answer }, store)

    @Test
    fun `http shows the warning`() {
        val vm = model(ServerProbe.Required)
        vm.onInput("http://10.0.2.2:8097")
        assertTrue(vm.state.value.cleartext)
        vm.onInput("https://music.example")
        assertFalse(vm.state.value.cleartext)
    }

    @Test
    fun `a login page in front is explained`() {
        val vm = model(ServerProbe.NotThisServer("redirected"))
        vm.onInput("music.example")
        vm.submit()
        assertEquals(NOT_THIS_SERVER, vm.state.value.error)
        assertNull(vm.state.value.next)
        assertEquals("https://music.example/", asked.single().toString())
        // Nothing was saved: the old server stays.
        assertEquals("https://old.example/", store.state.value.serverUrl)
    }

    @Test
    fun `sign-in turned off goes straight in`() {
        val vm = model(ServerProbe.Disabled)
        vm.onInput("http://10.0.2.2:8097")
        vm.submit()
        val session = store.state.value
        assertEquals("http://10.0.2.2:8097/", session.serverUrl)
        assertTrue(session.authDisabled)
        assertNull(session.token)
        assertEquals(ServerViewModel.Next.Main, vm.state.value.next)
    }

    @Test
    fun `a new server leads to account creation`() {
        val vm = model(ServerProbe.Setup)
        vm.onInput("https://new.example")
        vm.submit()
        assertEquals(ServerViewModel.Next.Setup, vm.state.value.next)
        assertEquals("https://new.example/", store.state.value.serverUrl)
        assertNull(store.state.value.token)
    }

    @Test
    fun `an older server and an unreachable one say so`() {
        val old = model(ServerProbe.TooOld)
        old.onInput("https://music.example")
        old.submit()
        assertEquals(TOO_OLD, old.state.value.error)
        val gone = model(ServerProbe.Unreachable("timeout"))
        gone.onInput("https://music.example")
        gone.submit()
        assertEquals(UNREACHABLE, gone.state.value.error)
    }
}
