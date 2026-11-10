package io.github.catchow0.d2n.ui

import io.github.catchow0.d2n.data.AccountsRequest
import io.github.catchow0.d2n.data.AddPlaylistAnswer
import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.D2nJson
import io.github.catchow0.d2n.data.LibraryCheckAnswer
import io.github.catchow0.d2n.data.LibraryStats
import io.github.catchow0.d2n.data.LinkRequest
import io.github.catchow0.d2n.data.MatchRequest
import io.github.catchow0.d2n.data.MixesAnswer
import io.github.catchow0.d2n.data.Owned
import io.github.catchow0.d2n.data.PlaylistRow
import io.github.catchow0.d2n.data.PlaylistTracksAnswer
import io.github.catchow0.d2n.data.PlaylistsAnswer
import io.github.catchow0.d2n.data.RowAnswer
import io.github.catchow0.d2n.data.SearchAnswer
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.data.TaskStarted
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.testutil.TestDeps
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.dashboard.DashboardViewModel
import io.github.catchow0.d2n.ui.dashboard.own
import io.github.catchow0.d2n.ui.madeforyou.MadeForYouViewModel
import io.github.catchow0.d2n.ui.madeforyou.TrialList
import io.github.catchow0.d2n.ui.madeforyou.TrialSort
import io.github.catchow0.d2n.ui.madeforyou.detail
import io.github.catchow0.d2n.ui.madeforyou.shown
import io.github.catchow0.d2n.ui.madeforyou.trialFilters
import io.github.catchow0.d2n.ui.playlists.PlaylistViewModel
import io.github.catchow0.d2n.ui.playlists.TrackFilter
import io.github.catchow0.d2n.ui.playlists.deezerId
import io.github.catchow0.d2n.ui.playlists.needsReview
import io.github.catchow0.d2n.ui.playlists.shownBy
import io.github.catchow0.d2n.ui.search.SearchKind
import io.github.catchow0.d2n.ui.search.SearchViewModel
import io.github.catchow0.d2n.ui.search.ownedLabel
import java.io.IOException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class ScreensViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private fun fixture(name: String) = javaClass.getResource("/api/$name")!!.readText()

    private val playlists by lazy { D2nJson.decodeFromString(PlaylistsAnswer.serializer(), fixture("playlists.json")) }
    private val tracks by lazy { D2nJson.decodeFromString(PlaylistTracksAnswer.serializer(), fixture("playlist_tracks.json")) }
    private val mixes by lazy { D2nJson.decodeFromString(MixesAnswer.serializer(), fixture("mixes.json")) }

    @Test
    fun `the dashboard reads again when the profile changes`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlists", playlists)
        t.reply("libraryStats", LibraryStats(count = 10))
        val vm = DashboardViewModel(t.deps)
        assertEquals(4, vm.playlists.value.value?.playlists?.size)
        assertEquals(10, vm.library.value.value?.count)
        assertEquals(1, t.api.calls.count { it.first == "playlists" })
        t.profile.value = "nd2"
        assertEquals(2, t.api.calls.count { it.first == "playlists" })
    }

    @Test
    fun `a screen reads again when it comes back, not when it first opens`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlists", playlists)
        t.reply("libraryStats", LibraryStats())
        val vm = DashboardViewModel(t.deps)
        vm.onScreenResumed(vm::refresh)
        assertEquals(1, t.api.calls.count { it.first == "playlists" })
        vm.onScreenResumed(vm::refresh)
        assertEquals(2, t.api.calls.count { it.first == "playlists" })
    }

    @Test
    fun `a task that ends makes the screen read again`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlistTracks", tracks)
        t.reply("playlists", playlists)
        var running = listOf(io.github.catchow0.d2n.data.TaskSummary("t1", done = false))
        t.api.onTasks = { io.github.catchow0.d2n.data.TaskList(running) }
        val vm = PlaylistViewModel(t.deps, "908622995")
        vm.watchTasks(vm::refresh)
        assertEquals(1, t.api.calls.count { it.first == "playlistTracks" })
        running = listOf(io.github.catchow0.d2n.data.TaskSummary("t1", done = true))
        testScheduler.advanceTimeBy(3_100)
        assertEquals(2, t.api.calls.count { it.first == "playlistTracks" })
        // Nothing else ends: no more reads.
        testScheduler.advanceTimeBy(30_000)
        assertEquals(2, t.api.calls.count { it.first == "playlistTracks" })
        vm.stopWatchingTasks()
    }

    @Test
    fun `the dashboard keeps Made for you and Deezer's mixes for their tab`() {
        assertEquals(listOf("908622995", "xp-spotify-37i9dQZF1DXcBWIGoYBM5M"), playlists.own().map { it.id })
    }

    @Test
    fun `adding a playlist follows its task and opens it`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlists", playlists)
        t.reply("libraryStats", LibraryStats())
        t.reply("addPlaylist", AddPlaylistAnswer("xp-spotify-1", added = true, message = "Spotify playlist added", taskId = "t9"))
        val vm = DashboardViewModel(t.deps) { "https://open.spotify.com/playlist/1" }
        vm.add("  https://spotify.link/abc  ")
        assertEquals(LinkRequest("https://open.spotify.com/playlist/1"), t.api.calls.first { it.first == "addPlaylist" }.second.single())
        assertEquals(Notice("Spotify playlist added", "t9"), t.notices.single())
        assertEquals("xp-spotify-1", vm.opened.value)
        vm.onOpened()
        assertNull(vm.opened.value)
    }

    @Test
    fun `a refused action says why, and an unreachable server lights the banner`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlists", playlists)
        t.reply("libraryStats", LibraryStats())
        t.api.replies["addPlaylist"] = { throw ApiError(400, "invalid", "Invalid ID or URL", null) }
        t.api.replies["refreshLibrary"] = { throw Unreachable(IOException("timeout")) }
        val vm = DashboardViewModel(t.deps)
        vm.add("nope")
        assertEquals(Notice("Invalid ID or URL", error = true), t.notices.single())
        vm.startLibraryRefresh()
        assertFalse(t.reachability.online.value)
        assertTrue(vm.busy.value.isEmpty())
    }

    @Test
    fun `a CSV over 5 MB is not sent`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlists", playlists)
        t.reply("libraryStats", LibraryStats())
        DashboardViewModel(t.deps).importCsv("big.csv", ByteArray(5 * 1024 * 1024 + 1))
        assertTrue(t.api.calls.none { it.first == "importPlaylist" })
        assertTrue(t.notices.single().message.contains("5 MB"))
    }

    @Test
    fun `a playlist's filters, as on the web`() {
        val rows = tracks.playlist.rows
        assertEquals(listOf(2), rows.filter { it.shownBy(TrackFilter.Missing, "") }.map { it.number })
        assertEquals(listOf(1), rows.filter { it.shownBy(TrackFilter.Found, "") }.map { it.number })
        assertEquals(listOf(3), rows.filter { it.shownBy(TrackFilter.Unchecked, "") }.map { it.number })
        assertEquals(listOf(3), rows.filter { it.shownBy(TrackFilter.Review, "") }.map { it.number })
        assertEquals(listOf(2), rows.filter { it.shownBy(TrackFilter.All, "moon safari") }.map { it.number })
        assertEquals("3135556", rows[0].deezerId())
        assertNull(rows[2].deezerId())
        assertTrue(rows[2].needsReview())
    }

    @Test
    fun `fixing a match replaces the row and its counts`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlistTracks", tracks)
        t.reply("playlists", playlists)
        val fixed = tracks.playlist.rows[0].copy(matched = false, manual = true, sourceName = "")
        t.reply("matchTrack", RowAnswer(fixed))
        val vm = PlaylistViewModel(t.deps, "908622995")
        assertEquals("Chill (mine)", vm.tile.value?.title)
        vm.match(tracks.playlist.rows[0], "missing")
        assertEquals(MatchRequest("3135556", "missing"), t.api.calls.first { it.first == "matchTrack" }.second[1])
        val preview = vm.tracks.value.value!!.playlist
        assertEquals(false, preview.rows[0].matched)
        assertEquals(0, preview.matchedCount)
        assertEquals(2, preview.unmatchedCount)
    }

    @Test
    fun `a playlist keeps at least one account`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlistTracks", tracks)
        t.reply("playlists", playlists)
        t.reply("playlistAccounts", io.github.catchow0.d2n.data.NavidromeAnswer())
        val vm = PlaylistViewModel(t.deps, "908622995")
        vm.setAccounts(emptyList())
        assertTrue(t.api.calls.none { it.first == "playlistAccounts" })
        vm.setAccounts(listOf("nd1", "nd2"))
        assertEquals(AccountsRequest(listOf("nd1", "nd2")), t.api.calls.first { it.first == "playlistAccounts" }.second[1])
        assertEquals(listOf("nd1", "nd2"), vm.tile.value?.accounts)
    }

    @Test
    fun `a scan offers to follow its task`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("playlistTracks", tracks)
        t.reply("playlists", playlists)
        t.reply("scanPlaylist", TaskStarted("t3"))
        PlaylistViewModel(t.deps, "908622995").scan(quick = false)
        assertEquals(Notice("Full scan started", "t3"), t.notices.single())
    }

    @Test
    fun `search marks what the library has`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("search", SearchAnswer(listOf(SearchResult("3135556", title = "One More Time", artist = "Daft Punk"))))
        t.reply("libraryCheck", LibraryCheckAnswer(mapOf("3135556" to Owned(owned = true))))
        val vm = SearchViewModel(t.deps)
        vm.search("one more time")
        val results = vm.results.value!!.value!!
        assertTrue(results.owned.getValue("3135556").owned)
        vm.setKind(SearchKind.Album)
        assertEquals(listOf("track", "album"), t.api.calls.filter { it.first == "search" }.map { it.second[1] })
    }

    @Test
    fun `owned chips say what the web says`() {
        assertEquals("In library", ownedLabel(SearchKind.Track, Owned(owned = true), null))
        assertNull(ownedLabel(SearchKind.Track, Owned(owned = false), null))
        assertEquals("3/14 tracks owned", ownedLabel(SearchKind.Album, Owned(ownedCount = 3, total = 14), 14))
        assertEquals("In library", ownedLabel(SearchKind.Album, Owned(ownedCount = 14, total = 14), 14))
        assertEquals("2/36 albums owned", ownedLabel(SearchKind.Artist, Owned(albumsOwned = 2), 36))
    }

    @Test
    fun `the quarantine's lists sort and filter as on the web`() {
        val trial = mixes.onTrial + mixes.pending.map { it.copy(id = "x", plays = 5, source = "Discover") }
        assertEquals(listOf("x", "1109731"), trial.shown("", TrialSort.Plays, "all").map { it.id })
        assertEquals(listOf("1109731"), trial.shown("", TrialSort.Plays, "unplayed").map { it.id })
        assertEquals(listOf("x"), trial.shown("", TrialSort.Plays, "source:Discover").map { it.id })
        assertEquals(listOf("x"), trial.shown("phantom", TrialSort.Plays, "all").map { it.id })
        assertTrue(trialFilters(TrialList.Review, mixes.pending).any { it.first == "reason:Played 3 times" })
        assertEquals("Never played · 28 days left", TrialList.Trial.detail(mixes.onTrial.single()))
        assertEquals("Played 3 times", TrialList.Review.detail(mixes.pending.single()))
    }

    @Test
    fun `keeping a track shows the state the server answers`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("mixes", mixes)
        t.reply("playlists", playlists)
        t.reply("keepTrack", mixes.copy(pending = emptyList()))
        val vm = MadeForYouViewModel(t.deps)
        assertEquals(listOf("auto-daily-1", "mix-flow-default"), vm.playlists.value.map { it.id })
        vm.keep(mixes.pending.single())
        assertEquals(listOf("1109732"), t.api.calls.first { it.first == "keepTrack" }.second)
        assertTrue(vm.state.value.value!!.pending.isEmpty())
        assertEquals("Kept: Phantom", t.notices.single().message)
    }

    @Test
    fun `a row without a Deezer track has nothing to play`() {
        assertNull(PlaylistRow(trackId = "src:sp:1").deezerId())
        assertNull(PlaylistRow(trackId = null).deezerId())
    }
}
