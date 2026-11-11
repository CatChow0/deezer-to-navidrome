package io.github.catchow0.d2n.ui.signin

import io.github.catchow0.d2n.data.AppUser
import io.github.catchow0.d2n.data.DeviceInfo
import io.github.catchow0.d2n.data.ForgotAnswer
import io.github.catchow0.d2n.data.ForgotRequest
import io.github.catchow0.d2n.data.NewPassword
import io.github.catchow0.d2n.data.SignedIn
import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.data.SuperAdminCode
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/** An account with a temporary password, and a forgotten one. */
class AccountRecoveryTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val api = FakeD2nApi()
    private val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://music.example/", token = "d2n_temporary", deviceName = "Pixel 8"))

    @Test
    fun `a temporary password sends the account to choose its own`() {
        api.onLogin = { SignedIn("d2n_token", DeviceInfo("d1", it.device), "alice", AppUser("u2", "alice", mustChange = true)) }
        val vm = SignInViewModel({ api }, store, defaultDevice = "Pixel 8").apply {
            onUsername("alice")
            onPassword("temporary-pass")
        }
        vm.submit()
        assertEquals(SignInViewModel.Next.FirstPassword, vm.state.value.next)
    }

    @Test
    fun `choosing the password keeps this phone signed in and shows the recovery code`() {
        api.replies["firstPassword"] = { SignedIn("d2n_new", DeviceInfo("d2", "Pixel 8"), "alice", recoveryCode = "CODE-1") }
        val vm = FirstPasswordViewModel({ api }, store, defaultDevice = "Phone")
        vm.onPassword("alices-own-password")
        vm.onConfirm("alices-own-password")
        vm.submit()
        assertEquals(NewPassword("alices-own-password", "Pixel 8"), api.calls.single().second.single())
        assertEquals("d2n_new", store.state.value.token)
        assertEquals("CODE-1", vm.state.value.recoveryCode)
    }

    @Test
    fun `two different passwords are refused before asking the server`() {
        val vm = FirstPasswordViewModel({ api }, store, defaultDevice = "Phone")
        vm.onPassword("alices-own-password")
        vm.onConfirm("alices-own-passw0rd")
        vm.submit()
        assertEquals(PASSWORDS_DIFFER, vm.state.value.error)
        assertTrue(api.calls.isEmpty())
    }

    @Test
    fun `a recovery code changes the password and gives the next code`() {
        api.replies["forgot"] = { ForgotAnswer("CODE-2") }
        val vm = ForgotViewModel { api }
        vm.onUsername(" alice ")
        vm.onCode("CODE-1")
        vm.onPassword("a-new-long-password")
        vm.submit()
        assertEquals(ForgotRequest("alice", "CODE-1", "a-new-long-password"), api.calls.single().second.single())
        assertEquals("CODE-2", vm.state.value.recoveryCode)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `the Super-Admin is told where the one-time code was written`() {
        api.replies["forgotSuperAdmin"] = { SuperAdminCode("recovery-code.txt", 15) }
        val vm = ForgotViewModel { api }
        vm.writeSuperAdminCode()
        assertTrue(vm.state.value.notice.orEmpty().contains("recovery-code.txt"))
    }
}
