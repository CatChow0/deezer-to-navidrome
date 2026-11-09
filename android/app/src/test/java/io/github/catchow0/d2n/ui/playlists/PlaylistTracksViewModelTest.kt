package io.github.catchow0.d2n.ui.playlists

import io.github.catchow0.d2n.data.NavidromeAccount
import io.github.catchow0.d2n.data.NavidromeAccountsResponse
import io.github.catchow0.d2n.data.PlaylistListResponse
import io.github.catchow0.d2n.data.PlaylistPreview
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.data.PlaylistTracksResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class PlaylistTracksViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `load keeps tracks and settings`() {
        val api = FakeD2nApi().apply {
            onPlaylistTracks = { _ -> PlaylistTracksResponse(playlist = PlaylistPreview(playlistTitle = "P", rows = emptyList())) }
            onNavidromeAccounts = { NavidromeAccountsResponse(accounts = listOf(NavidromeAccount(id = "a1", label = "A"))) }
            onPlaylists = { PlaylistListResponse(playlists = listOf(PlaylistTile(id = "p1", accounts = listOf("a1"), automation = io.github.catchow0.d2n.data.PlaylistAutomation(scan = true, intervalMinutes = 30, download = true)))) }
        }
        val vm = PlaylistTracksViewModel({ api }, "p1")
        vm.load()
        assertEquals("P", vm.state.value.preview?.playlistTitle)
        assertEquals(1, vm.state.value.accounts.size)
        assertTrue("a1" in vm.state.value.selectedAccounts)
        assertTrue(vm.state.value.autoScan)
    }
}