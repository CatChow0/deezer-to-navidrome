package io.github.catchow0.d2n.data

import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Phase 8: releases, stats, settings, New and Help, against answers shaped as the server writes them. */
class MoreScreensApiTest {
    private val server = MockWebServer()
    private lateinit var cacheDir: File
    private lateinit var api: D2nApi

    @Before
    fun setUp() {
        server.start()
        cacheDir = Files.createTempDirectory("d2n-cache").toFile()
        val base = server.url("/d2n/")
        api = ApiProvider(buildHttpClient(cacheDir, { RequestHeaders("d2n_x", "nd1", base) }, "D2N/test (Android 0)")).forServer(base)
    }

    @After
    fun tearDown() {
        server.close()
        cacheDir.deleteRecursively()
    }

    private fun fixture(name: String) = javaClass.getResource("/api/$name")!!.readText()

    private fun answer(body: String, code: Int = 200) =
        server.enqueue(MockResponse.Builder().code(code).body(body).addHeader("Content-Type", "application/json").build())

    private fun sent(): Pair<String, String> {
        val request = server.takeRequest()
        val query = request.url.encodedQuery?.let { "?$it" }.orEmpty()
        return "${request.method} ${request.url.encodedPath}$query" to (request.body?.utf8() ?: "")
    }

    @Test
    fun `the release feed and muting an artist`() = runBlocking {
        answer(fixture("releases.json"))
        answer("""{"muted":{}}""")
        val feed = apiCall { api.releases() }
        assertEquals(listOf("700001", "700002", "700003"), feed.releases.map { it.id })
        assertEquals(mapOf("27" to "Daft Punk"), feed.muted)
        assertEquals("1464", feed.releases[1].followed.single().id)
        assertEquals(2, feed.followedArtists[1].releases)
        sent()
        apiCall { api.muteArtist(MuteRequest("27", "Daft Punk", false)) }
        assertEquals("POST /d2n/api/v1/releases/mute" to """{"artist_id":"27","name":"Daft Punk","muted":false}""", sent())
    }

    @Test
    fun `the stats overview, a recap and the plays`() = runBlocking {
        answer(fixture("stats_overview.json"))
        answer(fixture("stats_recap.json"))
        answer("""{"plays":[{"id":9,"listened_at":1731200000.25,"source":"navidrome","track_id":3,"title":"One More Time","artist":"Daft Punk","album":null,"duration":320}],"total":1,"page":1,"pages":1}""")
        val overview = apiCall { api.statsOverview("month", "2026-11", "Europe/Paris") }
        assertEquals("GET /d2n/api/v1/stats/overview?period=month&key=2026-11&tz=Europe%2FParis", sent().first)
        assertEquals(25_200L, overview.totals.seconds)
        assertEquals("3135556", overview.top.tracks.single().deezerTrackId)
        assertNull(overview.top.albums.single().image)
        assertEquals(9, overview.habits.heatmap[6][23])
        assertEquals(5, overview.habits.longestStreak.days)
        val recap = apiCall { api.recap("month", "2026-10", "Europe/Paris") }
        sent()
        assertEquals(listOf("intro", "top_artist", "a_new_kind_of_slide", "outro"), recap.story.slides.map { it.type })
        assertEquals(248.85, recap.story.slides.first().track!!.duration, 0.01)
        assertEquals(8, recap.story.loyalty?.oneIn)
        assertNull(recap.story.obsession)
        assertEquals(19, recap.story.clock?.peakHour)
        assertEquals(6, recap.story.movers?.rise?.delta)
        assertTrue(recap.top.tracks.single().isNew)
        val plays = apiCall { api.plays("one more", 1) }
        assertEquals("GET /d2n/api/v1/stats/plays?q=one%20more&page=1", sent().first)
        assertEquals(3L, plays.plays.single().trackId)
    }

    @Test
    fun `settings are read whole and saved field by field`() = runBlocking {
        answer(fixture("settings.json"))
        answer(fixture("settings.json"))
        val settings = apiCall { api.settings() }
        assertEquals(listOf("/music/library", "/music/deezer-dl"), settings.settings.scanDirs)
        assertEquals(PathMapping("/music/library", "/music"), settings.settings.mappings.single())
        assertNull(settings.settings.previewStateFile)
        assertEquals(listOf(6, 12, 24, 48, 168, 0), settings.choices["release_refresh_hours"])
        assertTrue(settings.downloadsFolder.writable)
        sent()
        apiCall { api.saveSettings(SettingsChange(scanDirs = listOf("/music"), mappings = emptyList(), downloadWorkers = 2)) }
        // Lists stay lists, numbers stay whole numbers, and what did not change is left out.
        assertEquals("PUT /d2n/api/v1/settings" to """{"scan_dirs":["/music"],"host_to_navidrome_roots":[],"download_workers":2}""", sent())
    }

    @Test
    fun `accounts never carry a secret back, and send one only when typed`() = runBlocking {
        answer(fixture("navidrome_accounts.json"))
        answer(fixture("navidrome_accounts.json"))
        answer(fixture("deezer_accounts.json"))
        answer(fixture("deezer_accounts.json"))
        val navidrome = apiCall { api.navidromeProfiles() }
        assertEquals("m3u8", navidrome.accounts[0].publishMode)
        assertEquals(listOf("Old one"), navidrome.accounts[0].sync?.removed)
        assertEquals("Music", navidrome.accounts[0].lastTest?.libraries?.single()?.name)
        assertFalse(navidrome.accounts[1].hasSecret)
        sent()
        apiCall { api.updateNavidromeProfile("nd2", NavidromeProfileFields("Bob", "http://navidrome:4533", "bob", "password", null, "dz2")) }
        assertEquals(
            "PATCH /d2n/api/v1/navidrome/accounts/nd2" to """{"label":"Bob","url":"http://navidrome:4533","username":"bob","auth_type":"password","deezer_account":"dz2"}""",
            sent(),
        )
        val deezer = apiCall { api.deezerProfiles() }
        assertEquals("DEEZER_ARL", deezer.accounts[0].fromEnv)
        assertEquals("FLAC", deezer.downloads?.format)
        sent()
        apiCall { api.createDeezerProfile(DeezerProfileFields("Bob", "arl-value")) }
        assertEquals("POST /d2n/api/v1/deezer/accounts" to """{"label":"Bob","arl":"arl-value"}""", sent())
    }

    @Test
    fun `sign-in, devices and the listening stats`() = runBlocking {
        answer("""{"disabled":false,"username":"admin","account_from_env":false,"token":"api-token-1","token_from_env":false,"webhook_url":""}""")
        answer("{}")
        answer("""{"devices":[{"id":"a1","name":"Pixel","created_at":1730000000,"last_used_at":1731000000,"last_ip":"10.0.0.2","current":true}]}""")
        answer(fixture("stats_status.json"))
        answer("""{"removed":12,"added":0}""")
        assertEquals("api-token-1", apiCall { api.security() }.token)
        sent()
        apiCall { api.changePassword(PasswordRequest("old-password", "new-password")) }
        assertEquals("POST /d2n/api/v1/settings/password" to """{"current":"old-password","new":"new-password"}""", sent())
        assertTrue(apiCall { api.devices() }.devices.single().current)
        sent()
        val status = apiCall { api.statsStatus() }
        assertTrue(status.sources.canClean)
        assertEquals("me", status.sources.navidrome.user)
        assertEquals(4, status.enrich.pending)
        sent()
        assertEquals(12, apiCall { api.previewStatsImport() }.removed)
    }

    @Test
    fun `duplicates are applied with the paths kept`() = runBlocking {
        answer(fixture("dedup_report.json"))
        answer("""{"processed":2,"results":[]}""")
        val report = apiCall { api.duplicates() }.report
        assertEquals(listOf("g1", "g2"), report.groups.map { it.groupId })
        assertEquals(listOf("/music/b/Phantom.mp3"), report.keeperHints["g2"])
        assertEquals(31_000_000L, report.groups[0].entries[0].size)
        sent()
        apiCall { api.applyDuplicates(DuplicateApply(listOf(DuplicateDecision("g1", listOf("/music/a/Genesis.flac"))), "quarantine")) }
        assertEquals(
            "POST /d2n/api/v1/dedup/apply" to """{"decisions":[{"group_id":"g1","keep_paths":["/music/a/Genesis.flac"]}],"mode":"quarantine"}""",
            sent(),
        )
    }

    @Test
    fun `reset data names what it clears`() = runBlocking {
        answer("""{"cleared":"dedup-report","message":"dedup_report cleared"}""")
        assertEquals("dedup_report cleared", apiCall { api.clear("dedup-report") }.message)
        assertEquals("POST /d2n/api/v1/settings/clear/dedup-report", sent().first)
    }

    @Test
    fun `new and help`() = runBlocking {
        answer("""{"notes":[{"version":"1.18.1","date":"2026-11-10","title":"The app","html":"<p>Hello</p>"}],"unseen":true}""")
        answer("{}")
        answer("""{"sections":[{"id":"getting-started","title":"Getting started","html":"<h3>Start</h3>"}]}""")
        assertTrue(apiCall { api.notes() }.unseen)
        sent()
        apiCall { api.notesSeen() }
        assertEquals("POST /d2n/api/v1/content/notes/seen", sent().first)
        assertEquals("getting-started", apiCall { api.help() }.sections.single().id)
    }

    @Test
    fun `notes say what to change, since the version read last`() = runBlocking {
        answer(
            """{"notes":[{"version":"1.19.0","date":"2026-11-11","title":"Safer","html":"<p>x</p>",""" +
                """"highlights":["Nothing lost"],"actions":[{"level":"recommended","when":"Behind a proxy",""" +
                """"do":"Set it","lines":["TRUSTED_PROXIES=1"],"file":".env"}]}],"unseen":true,"since":"1.17.0",""" +
                """"pending_actions":[{"level":"required","when":"Authelia","do":"Bypass","lines":[],"file":"Authelia","version":"1.18.0"}]}""",
        )
        val notes = apiCall { api.notes() }
        assertEquals("1.17.0", notes.since)
        assertEquals("1.18.0", notes.pendingActions.single().version)
        val action = notes.notes.single().actions.single()
        assertEquals(listOf("TRUSTED_PROXIES=1"), action.lines)
        assertEquals("Behind a proxy", action.`when`)
        assertEquals(listOf("Nothing lost"), notes.notes.single().highlights)
    }
}
