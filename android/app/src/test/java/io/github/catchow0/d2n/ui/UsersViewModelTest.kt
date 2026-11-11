package io.github.catchow0.d2n.ui

import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.CodeAnswer
import io.github.catchow0.d2n.data.D2nJson
import io.github.catchow0.d2n.data.DeezerProfilesAnswer
import io.github.catchow0.d2n.data.HeirRequest
import io.github.catchow0.d2n.data.NewPassword
import io.github.catchow0.d2n.data.NewUser
import io.github.catchow0.d2n.data.ProfilesCleared
import io.github.catchow0.d2n.data.ServerInfo
import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.data.UserChange
import io.github.catchow0.d2n.data.UsersAnswer
import io.github.catchow0.d2n.data.UsersRequest
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.FakeSettingsStore
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.testutil.TestDeps
import io.github.catchow0.d2n.ui.main.SessionViewModel
import io.github.catchow0.d2n.ui.settings.DeezerAccountsViewModel
import io.github.catchow0.d2n.ui.settings.MaintenanceViewModel
import io.github.catchow0.d2n.ui.settings.SettingsPage
import io.github.catchow0.d2n.ui.settings.UsersViewModel
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/** The accounts of the app as the phone sees them: Settings → Users, sharing a
 * Deezer account, the clears of your profiles, and who is signed in. */
class UsersViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val answer = D2nJson.decodeFromString(
        UsersAnswer.serializer(),
        """{"ok": true, "me": "u1", "users": [
            {"id": "u1", "username": "root", "role": "superadmin", "navidrome_accounts": 2, "deezer_accounts": 1,
             "can": {"edit": true, "delete": false, "promote": false, "demote": false}},
            {"id": "u2", "username": "alice", "role": "standard", "must_change": true,
             "can": {"edit": true, "delete": true, "promote": true, "demote": false}}]}""",
    )

    @Test
    fun `an account reads with what the asker may do to it`() {
        val alice = answer.users[1]
        assertEquals("Standard", alice.roleLabel)
        assertTrue(alice.mustChange && alice.can.promote && !alice.can.demote)
        assertFalse(answer.users[0].can.delete)
    }

    @Test
    fun `adding, editing and removing an account send what the server expects`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        listOf("users", "createUser", "updateUser", "setUserPassword", "deleteUser").forEach { t.reply(it, answer) }
        t.reply("newUserRecoveryCode", CodeAnswer("CODE-9"))
        val vm = UsersViewModel(t.deps)
        val alice = answer.users[1]
        vm.create(" carol ", "temporary-pass", "standard")
        vm.save(alice, "alice", "admin", "another-temp")
        vm.newRecoveryCode(alice)
        vm.delete(alice, "u1")
        val sent = t.api.calls.associate { it.first to it.second }
        assertEquals(NewUser("carol", "temporary-pass", "standard"), sent["createUser"]!!.single())
        assertEquals(listOf("u2", NewPassword("another-temp")), sent["setUserPassword"])
        assertEquals(listOf("u2", UserChange(null, "admin")), sent["updateUser"])
        assertEquals("alice" to "CODE-9", vm.code.value)
        assertEquals(listOf("u2", HeirRequest("u1")), sent["deleteUser"])
    }

    @Test
    fun `a Deezer account is shared with the accounts chosen`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("deezerProfiles", DeezerProfilesAnswer())
        t.reply("shareDeezerProfile", DeezerProfilesAnswer())
        DeezerAccountsViewModel(t.deps).share("dz1", listOf("u2"))
        assertEquals(listOf("dz1", UsersRequest(listOf("u2"))), t.api.calls.first { it.first == "shareDeezerProfile" }.second)
    }

    @Test
    fun `clearing your profiles says how many playlists`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("clearProfiles", ProfilesCleared(3, "matches"))
        MaintenanceViewModel(t.deps).clearProfiles("matches")
        assertEquals("3 playlists cleared", t.notices.single().message)
    }

    @Test
    fun `General, Users and Reset are for the Admins`() {
        assertEquals(setOf(SettingsPage.Music, SettingsPage.Users, SettingsPage.Reset), SettingsPage.entries.filter { it.adminOnly }.toSet())
    }

    @Test
    fun `the session knows the Admin, and a temporary password still to change`() {
        val api = FakeD2nApi()
        val store = FakeSettingsStore(StoredSession(ready = true, serverUrl = "https://music.example/", token = "t"))
        api.onInfo = { D2nJson.decodeFromString(ServerInfo.serializer(), """{"version": "1.20.0", "api": 1, "is_admin": true, "user": {"id": "u1", "username": "root", "role": "superadmin"}}""") }
        val session = SessionViewModel({ api }, store)
        session.refresh()
        assertTrue(session.state.value.isAdmin)
        assertEquals("Super-Admin", session.state.value.user?.roleLabel)
        api.onInfo = { throw ApiError(403, "password_change_needed", "Choose your own password first.", null) }
        session.refresh()
        assertTrue(session.state.value.mustChange)
    }
}
