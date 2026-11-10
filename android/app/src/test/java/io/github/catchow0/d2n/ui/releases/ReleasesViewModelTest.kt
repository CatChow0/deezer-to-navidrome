package io.github.catchow0.d2n.ui.releases

import io.github.catchow0.d2n.data.ReleasesResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ReleasesViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `load reads the release feed`() {
        val api = FakeD2nApi().apply {
            onReleases = { ReleasesResponse(connected = true, releases = emptyList()) }
        }
        val vm = ReleasesViewModel({ api })
        vm.load()
        assertEquals(0, vm.state.value.releases.size)
        org.junit.Assert.assertTrue(vm.state.value.connected)
    }
}