package io.github.catchow0.d2n.testutil

import io.github.catchow0.d2n.data.AppInfo
import io.github.catchow0.d2n.data.AuthStatus
import io.github.catchow0.d2n.data.CancelAnswer
import io.github.catchow0.d2n.data.Credentials
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.ServerInfo
import io.github.catchow0.d2n.data.SignedIn
import io.github.catchow0.d2n.data.SignedOut
import io.github.catchow0.d2n.data.TaskEnvelope
import io.github.catchow0.d2n.data.TaskEvents
import io.github.catchow0.d2n.data.TaskList

/** A D2nApi whose answers each test sets; a call nobody set fails the test.
 * It records the credentials it was sent. */
class FakeD2nApi : D2nApi {
    var onLogin: suspend (Credentials) -> SignedIn = { error("login was not expected") }
    var onSetup: suspend (Credentials) -> SignedIn = { error("setup was not expected") }
    var onInfo: suspend () -> ServerInfo = { error("info was not expected") }
    var onTasks: suspend () -> TaskList = { error("tasks was not expected") }
    var onCancel: suspend (String) -> CancelAnswer = { error("cancel was not expected") }
    var onLogout: suspend () -> SignedOut = { SignedOut(true) }
    var onApp: suspend () -> AppInfo = { error("app was not expected") }
    var onPlaylists: suspend () -> io.github.catchow0.d2n.data.PlaylistListResponse = { error("playlists was not expected") }
    var onPlaylistTracks: suspend (String) -> io.github.catchow0.d2n.data.PlaylistTracksResponse = { error("playlistTracks was not expected") }
    var onNavidromeAccounts: suspend () -> io.github.catchow0.d2n.data.NavidromeAccountsResponse = { error("navidromeAccounts was not expected") }
    var onSearch: suspend (String, String) -> io.github.catchow0.d2n.data.SearchResponse = { _, _ -> error("search was not expected") }
    var onLibraryCheck: suspend (io.github.catchow0.d2n.data.LibraryCheckRequest) -> io.github.catchow0.d2n.data.LibraryCheckResponse = { error("libraryCheck was not expected") }
    var onMixes: suspend () -> io.github.catchow0.d2n.data.MixesResponse = { error("mixes was not expected") }
    var onMixKeep: suspend (String) -> io.github.catchow0.d2n.data.MixesResponse = { error("mixKeep was not expected") }
    var onMixRemove: suspend (String) -> io.github.catchow0.d2n.data.MixesResponse = { error("mixRemove was not expected") }
    var onMixRestore: suspend (String) -> io.github.catchow0.d2n.data.MixesResponse = { error("mixRestore was not expected") }
    var onTask: suspend (String) -> TaskEnvelope = { error("task was not expected") }
    val sent = mutableListOf<Credentials>()

    override suspend fun authStatus(): AuthStatus = AuthStatus("deezer-to-navidrome", 1, "required")
    override suspend fun login(body: Credentials): SignedIn = onLogin(body.also(sent::add))
    override suspend fun setup(body: Credentials): SignedIn = onSetup(body.also(sent::add))
    override suspend fun logout(): SignedOut = onLogout()
    override suspend fun info(): ServerInfo = onInfo()
    override suspend fun tasks(changedSince: Double?): TaskList = onTasks()
    override suspend fun task(id: String): TaskEnvelope = onTask(id)
    override suspend fun taskEvents(id: String, after: Int, wait: Int): TaskEvents = error("taskEvents was not expected")
    override suspend fun cancelTask(id: String): CancelAnswer = onCancel(id)
    override suspend fun app(): AppInfo = onApp()
    override suspend fun search(query: String, type: String): io.github.catchow0.d2n.data.SearchResponse = onSearch(query, type)
    override suspend fun searchAlbum(albumId: String): io.github.catchow0.d2n.data.SearchAlbumResponse = error("searchAlbum was not expected")
    override suspend fun searchArtist(artistId: String): io.github.catchow0.d2n.data.SearchArtistResponse = error("searchArtist was not expected")
    override suspend fun preview(trackId: String): io.github.catchow0.d2n.data.Preview = error("preview was not expected")
    override suspend fun libraryCheck(body: io.github.catchow0.d2n.data.LibraryCheckRequest): io.github.catchow0.d2n.data.LibraryCheckResponse = onLibraryCheck(body)
    override suspend fun playlists(): io.github.catchow0.d2n.data.PlaylistListResponse = onPlaylists()
    override suspend fun addPlaylist(body: io.github.catchow0.d2n.data.LinkBody): io.github.catchow0.d2n.data.PlaylistAddResponse = error("addPlaylist was not expected")
    override suspend fun deletePlaylist(id: String): io.github.catchow0.d2n.data.PlaylistListResponse = error("deletePlaylist was not expected")
    override suspend fun importPlaylist(csvFile: okhttp3.MultipartBody.Part): io.github.catchow0.d2n.data.PlaylistImportResponse = error("importPlaylist was not expected")
    override suspend fun playlistTracks(id: String): io.github.catchow0.d2n.data.PlaylistTracksResponse = onPlaylistTracks(id)
    override suspend fun playlistScan(id: String, body: Map<String, Any?>): io.github.catchow0.d2n.data.TaskStartResponse = error("playlistScan was not expected")
    override suspend fun playlistDownloadMissing(id: String): io.github.catchow0.d2n.data.TaskStartResponse = error("playlistDownloadMissing was not expected")
    override suspend fun playlistMatch(id: String, body: Map<String, Any?>): kotlinx.serialization.json.JsonObject = error("playlistMatch was not expected")
    override suspend fun playlistAutomation(id: String, body: Map<String, Any?>): kotlinx.serialization.json.JsonObject = error("playlistAutomation was not expected")
    override suspend fun playlistAccounts(id: String, body: Map<String, Any?>): kotlinx.serialization.json.JsonObject = error("playlistAccounts was not expected")
    override suspend fun playlistPublish(id: String): kotlinx.serialization.json.JsonObject = error("playlistPublish was not expected")
    override suspend fun mixes(): io.github.catchow0.d2n.data.MixesResponse = onMixes()
    override suspend fun mixKeep(deezerId: String): io.github.catchow0.d2n.data.MixesResponse = onMixKeep(deezerId)
    override suspend fun mixRemove(deezerId: String): io.github.catchow0.d2n.data.MixesResponse = onMixRemove(deezerId)
    override suspend fun mixRestore(deezerId: String): io.github.catchow0.d2n.data.MixesResponse = onMixRestore(deezerId)
    override suspend fun navidromeAccounts(): io.github.catchow0.d2n.data.NavidromeAccountsResponse = onNavidromeAccounts()
}
