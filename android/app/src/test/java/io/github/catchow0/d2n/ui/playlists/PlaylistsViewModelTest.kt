package io.github.catchow0.d2n.ui.playlists

import io.github.catchow0.d2n.data.PlaylistListResponse
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class PlaylistsViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `load splits profile and navidrome playlists`() {
        val api = FakeD2nApi().apply {
            onPlaylists = {
                PlaylistListResponse(
                    playlists = listOf(PlaylistTile(id = "p1", title = "P1")),
                    navidrome = listOf(PlaylistTile(id = "n1", title = "N1")),
                )
            }
        }
        val vm = PlaylistsViewModel({ api })
        vm.load()
        assertEquals(1, vm.state.value.playlists.size)
        assertEquals(1, vm.state.value.navidrome.size)
    }
}