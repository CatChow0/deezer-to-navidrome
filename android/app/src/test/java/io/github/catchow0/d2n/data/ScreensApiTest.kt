package io.github.catchow0.d2n.data

import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * The calls of the screens against answers shaped as the server writes them
 * (src/test/resources/api), and the bodies the app sends: the server reads
 * them field by field, so their JSON is checked here, whole.
 */
class ScreensApiTest {
    private val server = MockWebServer()
    private lateinit var cacheDir: File
    private lateinit var api: D2nApi

    @Before
    fun setUp() {
        server.start()
        cacheDir = Files.createTempDirectory("d2n-cache").toFile()
        val base = server.url("/d2n/")
        val client = buildHttpClient(cacheDir, { RequestHeaders("d2n_x", "nd1", base) }, "D2N/test (Android 0)")
        api = ApiProvider(client).forServer(base)
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
        return "${request.method} ${request.url.encodedPath}" to (request.body?.utf8() ?: "")
    }

    @Test
    fun `the dashboard reads the playlists and those made in Navidrome`() = runBlocking {
        answer(fixture("playlists.json"))
        val answer = apiCall { api.playlists() }
        assertEquals(listOf("908622995", "xp-spotify-37i9dQZF1DXcBWIGoYBM5M", "auto-daily-1", "mix-flow-default"), answer.playlists.map { it.id })
        val chill = answer.playlists[0]
        assertEquals("Chill", chill.deezerTitle)
        assertEquals(TrackCounts(3, 1, 1, 1), chill.tracks)
        assertEquals(PlaylistAutomation(scan = true, intervalMinutes = 120, download = false), chill.automation)
        assertNull(answer.playlists[1].tracks)
        val made = answer.navidrome.single()
        assertEquals("Road trip", made.name)
        assertEquals(12, made.songCount)
        assertEquals("GET /d2n/api/v1/playlists", sent().first)
    }

    @Test
    fun `a playlist's rows read the numeric Deezer IDs as text`() = runBlocking {
        answer(fixture("playlist_tracks.json"))
        val answer = apiCall { api.playlistTracks("908622995") }
        val rows = answer.playlist.rows
        assertEquals(listOf("3135556", "916424", "src:sp:0VjIjW4GlUZAMYd2vXMi3b"), rows.map { it.trackId })
        assertEquals(listOf(true, false, null), rows.map { it.matched })
        assertEquals("uncertain", rows[2].xp?.status)
        assertEquals(200, rows[2].xp?.sourceDuration)
        assertTrue(answer.playlist.xp!!.truncated)
        val published = answer.navidrome!!.accounts
        assertEquals("Chill (mine)", published[0].publication?.customTitle)
        assertNull(published[1].publication)
        assertEquals("GET /d2n/api/v1/playlists/908622995/tracks", sent().first)
    }

    @Test
    fun `a preview's gain is a decimal`() = runBlocking {
        answer(fixture("preview.json"))
        val preview = apiCall { api.preview("3135556") }
        assertEquals(-10.7, preview.gain, 0.0)
        assertTrue(preview.preview.startsWith("https://cdnt-preview.dzcdn.net/"))
    }

    @Test
    fun `search, album, artist and the library check`() = runBlocking {
        answer(fixture("search_tracks.json"))
        answer(fixture("album.json"))
        answer(fixture("artist.json"))
        answer(fixture("library_check.json"))
        answer(fixture("library_stats.json"))
        assertEquals("One More Time", apiCall { api.search("one more time", "track") }.results.single().title)
        assertEquals("GET /d2n/api/v1/search", sent().first)
        assertEquals(listOf("3135556", "3135553"), apiCall { api.album("302127") }.album.tracks.map { it.trackId })
        sent()
        assertEquals(36, apiCall { api.artist("27") }.artist.nbAlbum)
        sent()
        val owned = apiCall {
            api.libraryCheck(LibraryCheckRequest(listOf(LibraryCheckItem("3135556", "track", title = "One More Time", artist = "Daft Punk", duration = 320))))
        }.results
        assertTrue(owned.getValue("3135556").owned)
        assertEquals(3, owned.getValue("302127").ownedCount)
        assertEquals(2, owned.getValue("27").albumsOwned)
        val (line, body) = sent()
        assertEquals("POST /d2n/api/v1/library/check", line)
        assertEquals("""{"items":[{"key":"3135556","type":"track","title":"One More Time","artist":"Daft Punk","duration":320}]}""", body)
        assertEquals(15234, apiCall { api.libraryStats() }.count)
    }

    @Test
    fun `the bodies sent for a playlist`() = runBlocking {
        repeat(7) { answer("""{"task_id":"t1","row":{"number":2},"navidrome":{"accounts":[]}}""") }
        apiCall { api.scanPlaylist("908622995", ScanRequest("quick")) }
        assertEquals("POST /d2n/api/v1/playlists/908622995/scan" to """{"mode":"quick"}""", sent())
        apiCall { api.matchTrack("908622995", MatchRequest("916424", "missing")) }
        assertEquals("POST /d2n/api/v1/playlists/908622995/match" to """{"track_id":"916424","mode":"missing"}""", sent())
        apiCall { api.matchTrack("908622995", MatchRequest("916424", "file", "/music/a.flac")) }
        assertEquals("""{"track_id":"916424","mode":"file","path":"/music/a.flac"}""", sent().second)
        apiCall { api.sourceMatch("xp-spotify-1", SourceMatchRequest("sp:1", null)) }
        // No deezer_id: the server reads it as "not on Deezer".
        assertEquals("""{"key":"sp:1"}""", sent().second)
        apiCall { api.playlistAutomation("908622995", AutomationRequest(scan = false, intervalMinutes = 60, download = false)) }
        assertEquals(
            "PUT /d2n/api/v1/playlists/908622995/automation" to """{"auto_scan_enabled":false,"auto_scan_interval_minutes":60,"auto_download_after_scan":false}""",
            sent(),
        )
        apiCall { api.playlistAccounts("908622995", AccountsRequest(listOf("nd1", "nd2"))) }
        assertEquals("PUT /d2n/api/v1/playlists/908622995/accounts" to """{"accounts":["nd1","nd2"]}""", sent())
        apiCall { api.downloadTrack("916424", TrackDownloadRequest("Air - La femme d'argent", "908622995")) }
        assertEquals(
            "POST /d2n/api/v1/downloads/track/916424" to """{"label":"Air - La femme d'argent","playlist_id":"908622995"}""",
            sent(),
        )
    }

    @Test
    fun `a playlist made in Navidrome is read as its user`() = runBlocking {
        answer(
            """{"playlist":{"id":"5f1c9a2e","name":"Road trip","owner":"me","comment":"","song_count":2,"duration":431,
            "tracks":[{"title":"Genesis","artist":"Justice","album":"Cross","duration":234},{"title":"Phantom","artist":"Justice","album":"Cross","duration":197}]}}""",
        )
        val made = apiCall { api.navidromePlaylist("nd1", "5f1c9a2e") }.playlist
        assertEquals("Road trip", made.name)
        assertEquals(listOf("Genesis", "Phantom"), made.tracks.map { it.title })
        assertEquals("GET /d2n/api/v1/navidrome/playlists/nd1/5f1c9a2e", sent().first)
    }

    @Test
    fun `a CSV goes as csv_file, in multipart`() = runBlocking {
        answer("""{"id":"xp-csv-1","task_id":"t2","message":"Playlist imported"}""", code = 201)
        val part = MultipartBody.Part.createFormData("csv_file", "my list.csv", "Track Name,Artist\nGenesis,Justice\n".toRequestBody("text/csv".toMediaType()))
        val imported = apiCall { api.importPlaylist(part) }
        assertEquals("t2", imported.taskId)
        val request = server.takeRequest()
        assertEquals("/d2n/api/v1/playlists/import", request.url.encodedPath)
        assertTrue(request.headers["Content-Type"]!!.startsWith("multipart/form-data"))
        val body = request.body!!.utf8()
        assertTrue(body.contains("""name="csv_file"; filename="my list.csv""""))
        assertTrue(body.contains("Genesis,Justice"))
    }

    @Test
    fun `Made for you reads its whole state and sends only what changes`() = runBlocking {
        answer(fixture("mixes.json"))
        answer(fixture("mixes.json"))
        answer(fixture("mixes.json"))
        answer("""{"id":"mix-stl-4519372","added":true}""")
        answer(fixture("deezer_mixes.json"))
        val state = apiCall { api.mixes() }
        assertEquals("blend", state.settings.mixMode)
        assertEquals(3_221_225_472L, state.usage.bytes)
        assertEquals(listOf("Bob"), state.onTrial.single().sharedWith)
        assertEquals(listOf("Discover found only 12 new tracks."), state.lastRun?.notes)
        sent()
        apiCall { api.mixSettings(MixSettingsChange(mixMode = "daily")) }
        assertEquals("POST /d2n/api/v1/mixes/settings" to """{"mix_mode":"daily"}""", sent())
        apiCall { api.keepPending(IdsRequest(listOf("1109732"))) }
        assertEquals("POST /d2n/api/v1/mixes/trial/keep-pending" to """{"ids":["1109732"]}""", sent())
        apiCall { api.followMix(FollowMixRequest("stl", "4519372", "Chill Mix")) }
        assertEquals("""{"kind":"stl","source_id":"4519372","title":"Chill Mix"}""", sent().second)
        val found = apiCall { api.deezerMixes() }
        assertEquals("4519372", found.mixes[1].sourceId)
        assertEquals("Electro Hits", found.playlists.single().title)
    }

    @Test
    fun `an error answer keeps the server's message`() {
        answer("""{"error":{"code":"invalid","message":"Scan this playlist first"}}""", code = 400)
        val failure = runCatching { runBlocking { apiCall { api.publishPlaylist("908622995") } } }.exceptionOrNull()
        assertTrue(failure is ApiError)
        assertEquals("Scan this playlist first", failure!!.message)
    }

    @Test
    fun `the server's media are read under its address, Deezer's as they are`() {
        val base = server.url("/d2n/")
        assertEquals(server.url("/d2n/api/v1/covers/908622995.jpg").toString(), base.media("/api/v1/covers/908622995.jpg"))
        assertEquals("https://cdn-images.dzcdn.net/x.jpg", base.media("https://cdn-images.dzcdn.net/x.jpg"))
        assertNull(base.media(""))
        assertNull(base.media(null))
    }

    @Test
    fun `the token and the profile never go to another host`() {
        val other = MockWebServer()
        other.start()
        try {
            val base = server.url("/d2n/")
            val client = buildHttpClient(null, { RequestHeaders("d2n_secret", "nd1", base) }, "D2N/test (Android 0)")
            other.enqueue(MockResponse.Builder().code(200).body("img").build())
            server.enqueue(MockResponse.Builder().code(200).body("img").build())
            client.newCall(Request.Builder().url(other.url("/cover.jpg")).build()).execute().close()
            client.newCall(Request.Builder().url(server.url("/d2n/api/v1/covers/a.jpg")).build()).execute().close()
            val elsewhere = other.takeRequest()
            assertNull(elsewhere.headers["Authorization"])
            assertNull(elsewhere.headers["X-Navidrome-Account"])
            val ours = server.takeRequest()
            assertEquals("Bearer d2n_secret", ours.headers["Authorization"])
            assertEquals("nd1", ours.headers["X-Navidrome-Account"])
        } finally {
            other.close()
        }
    }

    @Test
    fun `a 401 from another host signs nothing out`() {
        val other = MockWebServer()
        other.start()
        try {
            var signedOut = 0
            val client = buildHttpClient(null, { RequestHeaders("d2n_x", "nd1", server.url("/d2n/")) }, "D2N/test (Android 0)") { signedOut++ }
            other.enqueue(MockResponse.Builder().code(401).build())
            client.newCall(Request.Builder().url(other.url("/x.jpg")).build()).execute().close()
            assertEquals(0, signedOut)
            assertFalse(other.takeRequest().headers.names().contains("Authorization"))
        } finally {
            other.close()
        }
    }
}
