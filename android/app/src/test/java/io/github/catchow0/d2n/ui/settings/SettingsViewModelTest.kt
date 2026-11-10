package io.github.catchow0.d2n.ui.settings

import io.github.catchow0.d2n.data.SettingsResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class SettingsViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `load and clear`() {
        val api = FakeD2nApi().apply {
            onSettings = { SettingsResponse(settings = JsonObject(emptyMap())) }
            onClearSettings = { io.github.catchow0.d2n.data.ClearSettingsResponse(cleared = it, message = "ok") }
        }
        val vm = SettingsViewModel({ api })
        vm.load()
        assertEquals(JsonObject(emptyMap()), vm.state.value.settings)
        vm.clear("all")
        assertEquals("ok", vm.state.value.message)
    }
}
