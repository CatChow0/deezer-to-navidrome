package io.github.catchow0.d2n.ui.signin

import io.github.catchow0.d2n.data.Credentials
import io.github.catchow0.d2n.data.DeviceInfo
import io.github.catchow0.d2n.data.SignedIn
import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class SetupViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val api = FakeD2nApi()
    private val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://music.example/"))

    @Test
    fun `creating the account signs this phone in and shows its recovery code first`() {
        api.onSetup = { SignedIn("d2n_first", DeviceInfo("d1", it.device), it.username, recoveryCode = "AAAA-BBBB") }
        val vm = SetupViewModel({ api }, store, defaultDevice = "Pixel 8")
        vm.onUsername("me")
        vm.onPassword("long-test-password")
        vm.onConfirm("long-test-password")
        vm.submit()
        assertEquals(Credentials("me", "long-test-password", "Pixel 8"), api.sent.single())
        assertEquals("d2n_first", store.state.value.token)
        assertEquals("AAAA-BBBB", vm.state.value.recoveryCode)
        assertNull(vm.state.value.next)
        vm.goIn()
        assertEquals(SetupViewModel.Next.Main, vm.state.value.next)
    }

    @Test
    fun `two different passwords are refused before asking the server`() {
        val vm = SetupViewModel({ api }, store, defaultDevice = "Pixel 8")
        vm.onUsername("me")
        vm.onPassword("long-test-password")
        vm.onConfirm("long-test-passw0rd")
        vm.submit()
        assertEquals(PASSWORDS_DIFFER, vm.state.value.error)
        assertTrue(api.sent.isEmpty())
        assertNull(store.state.value.token)
    }
}
