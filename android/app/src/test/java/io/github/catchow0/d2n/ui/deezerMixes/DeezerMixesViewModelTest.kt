package io.github.catchow0.d2n.ui.deezerMixes

import io.github.catchow0.d2n.data.DeezerMixItem
import io.github.catchow0.d2n.data.DeezerMixesResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class DeezerMixesViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `load lists deezer mixes`() {
        val api = FakeD2nApi().apply {
            onDeezerMixes = { DeezerMixesResponse(mixes = listOf(DeezerMixItem(kind = "stl", sourceId = "1", title = "Mix"))) }
            onFollowDeezerMix = { io.github.catchow0.d2n.data.DeezerMixFollowResponse(id = "x", added = true) }
        }
        val vm = DeezerMixesViewModel({ api })
        vm.load()
        assertEquals(1, vm.state.value.mixes.size)
        vm.follow(vm.state.value.mixes.first())
        assertTrue(vm.state.value.mixes.first().followed)
    }
}