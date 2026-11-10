package io.github.catchow0.d2n.ui

import androidx.compose.ui.text.AnnotatedString
import io.github.catchow0.d2n.data.D2nJson
import io.github.catchow0.d2n.data.DuplicateApply
import io.github.catchow0.d2n.data.DuplicateApplyAnswer
import io.github.catchow0.d2n.data.DuplicateOutcome
import io.github.catchow0.d2n.data.DuplicateReportAnswer
import io.github.catchow0.d2n.data.ImportPreview
import io.github.catchow0.d2n.data.LibraryCheckAnswer
import io.github.catchow0.d2n.data.MutedAnswer
import io.github.catchow0.d2n.data.Owned
import io.github.catchow0.d2n.data.PathMapping
import io.github.catchow0.d2n.data.PlaysPage
import io.github.catchow0.d2n.data.Recap
import io.github.catchow0.d2n.data.RecapIndex
import io.github.catchow0.d2n.data.ReleasesAnswer
import io.github.catchow0.d2n.data.SettingsAnswer
import io.github.catchow0.d2n.data.SettingsChange
import io.github.catchow0.d2n.data.StatsOverview
import io.github.catchow0.d2n.data.StatsStatus
import io.github.catchow0.d2n.data.TaskStarted
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.testutil.TestDeps
import io.github.catchow0.d2n.ui.content.HtmlBlock
import io.github.catchow0.d2n.ui.content.decodeEntities
import io.github.catchow0.d2n.ui.content.parseHtml
import io.github.catchow0.d2n.ui.releases.Ownership
import io.github.catchow0.d2n.ui.releases.ReleaseFilters
import io.github.catchow0.d2n.ui.releases.ReleaseType
import io.github.catchow0.d2n.ui.releases.ReleasesViewModel
import io.github.catchow0.d2n.ui.releases.feedLine
import io.github.catchow0.d2n.ui.releases.ownership
import io.github.catchow0.d2n.ui.releases.releaseGroup
import io.github.catchow0.d2n.ui.releases.visible
import io.github.catchow0.d2n.ui.settings.DuplicatesViewModel
import io.github.catchow0.d2n.ui.settings.ListeningStatsViewModel
import io.github.catchow0.d2n.ui.settings.MusicSettingsViewModel
import io.github.catchow0.d2n.ui.settings.droppedCount
import io.github.catchow0.d2n.ui.stats.Period
import io.github.catchow0.d2n.ui.stats.PeriodKeys
import io.github.catchow0.d2n.ui.stats.StatsViewModel
import io.github.catchow0.d2n.ui.stats.StoryWords
import io.github.catchow0.d2n.ui.stats.listening
import io.github.catchow0.d2n.ui.stats.paletteFor
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class MoreScreensViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private fun fixture(name: String) = javaClass.getResource("/api/$name")!!.readText()

    private val feed by lazy { D2nJson.decodeFromString(ReleasesAnswer.serializer(), fixture("releases.json")) }
    private val recap by lazy { D2nJson.decodeFromString(Recap.serializer(), fixture("stats_recap.json")) }

    @Test
    fun `iso weeks, months and years step as the web's keys`() {
        assertEquals("2026-W01", PeriodKeys.of(Period.Week, LocalDate.of(2025, 12, 29)))
        assertEquals("2026-W53", PeriodKeys.of(Period.Week, LocalDate.of(2026, 12, 31)))
        assertEquals(LocalDate.of(2025, 12, 29), PeriodKeys.dateOf(Period.Week, "2026-W01"))
        assertEquals("2025-W52", PeriodKeys.step(Period.Week, "2026-W01", -1))
        assertEquals("2026-01", PeriodKeys.step(Period.Month, "2025-12", 1))
        assertEquals("2025", PeriodKeys.step(Period.Year, "2026", -1))
        assertEquals("2024", PeriodKeys.earliest(Period.Year, "2024-03"))
        assertEquals("2024-W09", PeriodKeys.earliest(Period.Week, "2024-03"))
        assertNull(PeriodKeys.dateOf(Period.Month, "nonsense"))
    }

    @Test
    fun `listening time reads as the web's`() {
        assertEquals("45 min", listening(2_700))
        assertEquals("7 h", listening(25_200))
        assertEquals("1 h 5 min", listening(3_900))
    }

    @Test
    fun `stats never step past now, nor before the first play`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("recaps", RecapIndex(months = listOf(io.github.catchow0.d2n.data.RecapEntry("2026-11"), io.github.catchow0.d2n.data.RecapEntry("2026-09"))))
        t.reply("statsOverview", StatsOverview())
        t.reply("plays", PlaysPage())
        val vm = StatsViewModel(t.deps) { LocalDate.of(2026, 11, 10) }
        assertFalse(vm.canStep(1))
        assertTrue(vm.canStep(-1))
        vm.step(-1)
        vm.step(-1)
        assertEquals("2026-09", vm.choice.value.key)
        assertFalse(vm.canStep(-1))
        vm.setPeriod(Period.All)
        assertFalse(vm.canStep(-1))
        assertEquals(listOf("month", "month", "month", "all"), t.api.calls.filter { it.first == "statsOverview" }.map { it.second[0] })
    }

    @Test
    fun `the plays search waits for the typing to stop`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("recaps", RecapIndex())
        t.reply("statsOverview", StatsOverview())
        t.reply("plays", PlaysPage())
        val vm = StatsViewModel(t.deps) { LocalDate.of(2026, 11, 10) }
        vm.search("d")
        vm.search("da")
        vm.search("daft")
        testScheduler.advanceTimeBy(350)
        assertEquals(listOf("", "daft"), t.api.calls.filter { it.first == "plays" }.map { it.second[0] })
    }

    @Test
    fun `the release feed filters as the web's`() {
        val owned = mapOf("700003" to Owned(ownedCount = 13, total = 13))
        // Daft Punk is muted: its release is gone.
        assertEquals(listOf("700001", "700002"), feed.visible(owned, ReleaseFilters()).map { it.id })
        assertEquals(listOf("700001"), feed.visible(owned, ReleaseFilters(type = ReleaseType.Albums)).map { it.id })
        assertEquals(listOf("700002"), feed.visible(owned, ReleaseFilters(type = ReleaseType.Short)).map { it.id })
        assertEquals(listOf("700001"), feed.visible(owned, ReleaseFilters(hideFeatures = true)).map { it.id })
        val unmuted = feed.copy(muted = emptyMap())
        assertEquals(listOf("700001", "700002"), unmuted.visible(owned, ReleaseFilters(hideOwned = true)).map { it.id })
        assertEquals(Ownership.Full, ownership(owned["700003"], feed.releases[2]))
        assertEquals(Ownership.Partial, ownership(Owned(ownedCount = 2), feed.releases[2]))
        assertEquals(Ownership.None, ownership(Owned(), feed.releases[2]))
        val today = LocalDate.of(2026, 11, 10)
        assertEquals("Upcoming", releaseGroup(feed.releases[0], today))
        assertEquals("October 2026", releaseGroup(feed.releases[1], today))
        assertEquals(
            "42 favorite artists of Me, releases from the last 60 days. Updated 2 h ago; refreshed every day.",
            feedLine(feed, now = (1_731_200_000L + 7_200) * 1000),
        )
    }

    @Test
    fun `muting keeps the feed and takes the server's list`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("releases", feed)
        t.reply("libraryCheck", LibraryCheckAnswer(mapOf("700001" to Owned(ownedCount = 13, total = 13))))
        t.reply("muteArtist", MutedAnswer(emptyMap()))
        val vm = ReleasesViewModel(t.deps)
        assertEquals(13, vm.owned.value.getValue("700001").ownedCount)
        vm.setMuted("27", "Daft Punk", false)
        assertEquals(emptyMap<String, String>(), vm.feed.value.value?.muted)
        assertEquals("Daft Punk is back in the feed", t.notices.single().message)
    }

    @Test
    fun `a recap's words say what changed`() {
        val words = StoryWords(recap)
        assertEquals("October", words.name)
        assertEquals("September", words.previous)
        assertEquals("+10 plays vs September", words.change(recap.top.artists.single()))
        assertEquals("New this month", words.change(recap.top.tracks.single()))
        // A recap always looks the same, and the top artist slide is black on white.
        assertEquals(paletteFor(recap.key, 2, "intro"), paletteFor(recap.key, 2, "intro"))
        assertEquals(androidx.compose.ui.graphics.Color.Black, paletteFor(recap.key, 1, "top_artist").first)
    }

    @Test
    fun `notes and help keep their structure`() {
        val blocks = parseHtml(
            """<p>The app: <b>playlists</b> &amp; <code>search</code>.</p>
            <ul class="help-list"><li><strong>Update.</strong> From your server.</li><li>Second</li></ul>
            <h4 class="help-h">After</h4><ol><li>One</li></ol>
            <table><tr><th>Key</th><th>What</th></tr><tr><td>A</td><td>B</td></tr></table>
            <pre class="help-code">docker run \
  -p 8080:8080</pre><p>See <a href="https://example.com">this</a>.</p>""",
        )
        val types = blocks.map { it::class.simpleName }
        assertEquals(listOf("Paragraph", "Item", "Item", "Heading", "Item", "Table", "Code", "Paragraph"), types)
        assertEquals("The app: playlists & search.", (blocks[0] as HtmlBlock.Paragraph).text.text)
        assertEquals("•", (blocks[1] as HtmlBlock.Item).marker)
        assertEquals("1.", (blocks[4] as HtmlBlock.Item).marker)
        assertEquals(listOf(listOf("Key", "What"), listOf("A", "B")), (blocks[5] as HtmlBlock.Table).rows.map { row -> row.map(AnnotatedString::text) })
        assertTrue((blocks[6] as HtmlBlock.Code).text.contains("-p 8080:8080"))
        assertEquals("Settings → Accounts", decodeEntities("Settings &rarr; Accounts"))
    }

    @Test
    fun `settings save the form, without empty rows`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        val settings = D2nJson.decodeFromString(SettingsAnswer.serializer(), fixture("settings.json"))
        t.reply("settings", settings)
        t.reply("saveSettings", settings)
        val vm = MusicSettingsViewModel(t.deps)
        vm.edit { it.copy(scanDirs = it.scanDirs + "  ", mappings = it.mappings + PathMapping("/x", ""), downloadWorkers = 2) }
        assertTrue(vm.dirty)
        vm.save()
        val change = t.api.calls.first { it.first == "saveSettings" }.second.single() as SettingsChange
        assertEquals(listOf("/music/library", "/music/deezer-dl"), change.scanDirs)
        assertEquals(listOf(PathMapping("/music/library", "/music")), change.mappings)
        assertEquals(2, change.downloadWorkers)
        assertEquals("Settings saved", t.notices.single().message)
    }

    @Test
    fun `start clean asks with what it would lose`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("statsStatus", D2nJson.decodeFromString(StatsStatus.serializer(), fixture("stats_status.json")))
        t.reply("previewStatsImport", ImportPreview(removed = 12))
        val vm = ListeningStatsViewModel(t.deps)
        vm.askClean()
        assertEquals(12, vm.cleanLoses.value)
        assertTrue(t.api.calls.none { it.first == "importStats" })
        vm.cancelClean()
        assertNull(vm.cleanLoses.value)
    }

    @Test
    fun `duplicates keep the earlier choices, else the best copy`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("duplicates", D2nJson.decodeFromString(DuplicateReportAnswer.serializer(), fixture("dedup_report.json")))
        t.reply(
            "applyDuplicates",
            DuplicateApplyAnswer(3, listOf(DuplicateOutcome("/a", "moved"), DuplicateOutcome("/b", "moved"), DuplicateOutcome("/c", "missing"))),
        )
        val vm = DuplicatesViewModel(t.deps)
        val groups = vm.report.value.value!!.groups
        assertFalse(vm.none.value)
        assertEquals(setOf("/music/a/Genesis.flac"), vm.keep.value["g1"])
        assertEquals(setOf("/music/b/Phantom.mp3"), vm.keep.value["g2"])
        assertEquals(3, droppedCount(groups, vm.keep.value))
        vm.toggle("g2", "/music/a/Phantom.flac")
        assertEquals(2, droppedCount(groups, vm.keep.value))
        vm.keepAll()
        assertEquals(0, droppedCount(groups, vm.keep.value))
        vm.keepBest()
        vm.apply("quarantine")
        val sent = t.api.calls.first { it.first == "applyDuplicates" }.second.single() as DuplicateApply
        assertEquals("quarantine", sent.mode)
        assertEquals(setOf("g1", "g2"), sent.decisions.map { it.groupId }.toSet())
        // What the server did, not what was asked: one file was already gone.
        assertEquals("2 files moved to quarantine, 1 file already gone", t.notices.single().message)
    }

    @Test
    fun `no duplicate report yet is not an error, and the scan can start from there`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.api.replies["duplicates"] = { throw HttpException(Response.error<Any>(404, "{}".toResponseBody())) }
        t.reply("scanDuplicates", TaskStarted("t1"))
        val vm = DuplicatesViewModel(t.deps)
        assertTrue(vm.none.value)
        assertNull(vm.report.value.error)
        vm.scan()
        assertEquals("t1", t.notices.single().taskId)
    }
}
