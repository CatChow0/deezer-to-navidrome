package io.github.catchow0.d2n.ui.signin

import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.Credentials
import io.github.catchow0.d2n.data.DeviceInfo
import io.github.catchow0.d2n.data.SignedIn
import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SignInViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val api = FakeD2nApi()
    private val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://music.example/"))

    private fun model() = SignInViewModel({ api }, store, defaultDevice = "Pixel 8").apply {
        onUsername("admin")
        onPassword("long-test-password")
    }

    @Test
    fun `signing in stores the token and the device name`() {
        api.onLogin = { SignedIn("d2n_token", DeviceInfo("d1", it.device), "admin") }
        val vm = model()
        assertEquals("Pixel 8", vm.state.value.device)
        vm.onDevice("Anthony's Pixel")
        vm.submit()
        assertEquals(Credentials("admin", "long-test-password", "Anthony's Pixel"), api.sent.single())
        assertEquals("d2n_token", store.state.value.token)
        assertEquals("Anthony's Pixel", store.state.value.deviceName)
        assertEquals(SignInViewModel.Next.Main, vm.state.value.next)
    }

    @Test
    fun `a wrong password is said and nothing is stored`() {
        api.onLogin = { throw ApiError(401, "wrong_credentials", "Wrong username or password.", null) }
        val vm = model()
        vm.submit()
        assertEquals("Wrong username or password.", vm.state.value.error)
        assertNull(store.state.value.token)
        assertNull(vm.state.value.next)
        assertFalse(vm.state.value.busy)
    }

    @Test
    fun `too many attempts counts down then lets you try again`() = runTest(main.dispatcher) {
        api.onLogin = { throw ApiError(429, "too_many_attempts", "Too many attempts, try again in 30 s.", 30) }
        val vm = model()
        vm.submit()
        runCurrent()
        assertEquals(30, vm.state.value.waitSeconds)
        assertEquals("Too many attempts. Try again in 30 s.", vm.state.value.error)
        assertFalse(vm.state.value.canSubmit)
        advanceTimeBy(10_000)
        runCurrent()
        assertEquals(20, vm.state.value.waitSeconds)
        advanceTimeBy(20_000)
        runCurrent()
        assertEquals(0, vm.state.value.waitSeconds)
        assertTrue(vm.state.value.canSubmit)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `a server with no account leads to setup`() {
        api.onLogin = { throw ApiError(409, "setup_needed", "This server has no account yet: create it first.", null) }
        val vm = model()
        vm.submit()
        assertEquals(SignInViewModel.Next.Setup, vm.state.value.next)
    }
}
