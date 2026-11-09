package io.github.catchow0.d2n.ui.madeforyou

import io.github.catchow0.d2n.data.MixTrack
import io.github.catchow0.d2n.data.MixesResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class MixesViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val track = MixTrack(id = "t1", artist = "A", title = "Song", album = "Album")

    @Test
    fun `load populates the three lists`() {
        val api = FakeD2nApi().apply {
            onMixes = { MixesResponse(onTrial = listOf(track), pending = emptyList(), trash = emptyList()) }
        }
        val vm = MixesViewModel({ api })
        vm.load()
        assertEquals(1, vm.state.value.onTrial.size)
        assertEquals("t1", vm.state.value.onTrial.first().id)
    }

    @Test
    fun `keep moves a track out of trial`() {
        val remaining = emptyList<MixTrack>()
        val api = FakeD2nApi().apply {
            onMixes = { MixesResponse(onTrial = listOf(track)) }
            onMixKeep = { MixesResponse(onTrial = remaining, pending = listOf(track), trash = emptyList()) }
        }
        val vm = MixesViewModel({ api })
        vm.load()
        vm.keep("t1")
        assertTrue(vm.state.value.onTrial.isEmpty())
        assertEquals(1, vm.state.value.pending.size)
    }
}