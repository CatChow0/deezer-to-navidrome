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
import io.github.catchow0.d2n.data.AccountsRequest
import io.github.catchow0.d2n.data.AddPlaylistAnswer
import io.github.catchow0.d2n.data.AlbumAnswer
import io.github.catchow0.d2n.data.ArtistAnswer
import io.github.catchow0.d2n.data.AutomationAnswer
import io.github.catchow0.d2n.data.AutomationRequest
import io.github.catchow0.d2n.data.DeezerMixesAnswer
import io.github.catchow0.d2n.data.DeleteAnswer
import io.github.catchow0.d2n.data.DownloadRequest
import io.github.catchow0.d2n.data.FollowAnswer
import io.github.catchow0.d2n.data.FollowMixRequest
import io.github.catchow0.d2n.data.IdsRequest
import io.github.catchow0.d2n.data.ImportAnswer
import io.github.catchow0.d2n.data.LibraryCheckAnswer
import io.github.catchow0.d2n.data.LibraryCheckRequest
import io.github.catchow0.d2n.data.LibrarySearchAnswer
import io.github.catchow0.d2n.data.LibraryStats
import io.github.catchow0.d2n.data.LinkRequest
import io.github.catchow0.d2n.data.MatchRequest
import io.github.catchow0.d2n.data.MixSettingsChange
import io.github.catchow0.d2n.data.MixesAnswer
import io.github.catchow0.d2n.data.NavidromeAccountsAnswer
import io.github.catchow0.d2n.data.NavidromeAnswer
import io.github.catchow0.d2n.data.NavidromePlaylistAnswer
import io.github.catchow0.d2n.data.PlaylistTracksAnswer
import io.github.catchow0.d2n.data.PlaylistsAnswer
import io.github.catchow0.d2n.data.Preview
import io.github.catchow0.d2n.data.RowAnswer
import io.github.catchow0.d2n.data.ScanRequest
import io.github.catchow0.d2n.data.SearchAnswer
import io.github.catchow0.d2n.data.SourceMatchRequest
import io.github.catchow0.d2n.data.TaskStarted
import io.github.catchow0.d2n.data.TrackDownloadRequest
import okhttp3.MultipartBody

/** A D2nApi whose answers each test sets; a call nobody set fails the test.
 * It records the credentials it was sent, and the other calls in [calls]: the
 * screens' calls are answered by [replies], by method name. */
class FakeD2nApi : D2nApi {
    var onLogin: suspend (Credentials) -> SignedIn = { error("login was not expected") }
    var onSetup: suspend (Credentials) -> SignedIn = { error("setup was not expected") }
    var onInfo: suspend () -> ServerInfo = { error("info was not expected") }
    var onTasks: suspend () -> TaskList = { error("tasks was not expected") }
    var onCancel: suspend (String) -> CancelAnswer = { error("cancel was not expected") }
    var onLogout: suspend () -> SignedOut = { SignedOut(true) }
    var onApp: suspend () -> AppInfo = { error("app was not expected") }
    var onTask: suspend (String) -> TaskEnvelope = { error("task was not expected") }
    val sent = mutableListOf<Credentials>()
    val calls = mutableListOf<Pair<String, List<Any?>>>()
    val replies = mutableMapOf<String, suspend (List<Any?>) -> Any?>()

    @Suppress("UNCHECKED_CAST")
    private suspend fun <T> reply(name: String, vararg args: Any?): T {
        calls += name to args.toList()
        val handler = replies[name] ?: error("$name was not expected")
        return handler(args.toList()) as T
    }

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

    override suspend fun playlists(): PlaylistsAnswer = reply("playlists")
    override suspend fun addPlaylist(body: LinkRequest): AddPlaylistAnswer = reply("addPlaylist", body)
    override suspend fun importPlaylist(file: MultipartBody.Part): ImportAnswer = reply("importPlaylist", file)
    override suspend fun deletePlaylist(id: String): DeleteAnswer = reply("deletePlaylist", id)
    override suspend fun playlistTracks(id: String): PlaylistTracksAnswer = reply("playlistTracks", id)
    override suspend fun playlistNavidrome(id: String): NavidromeAnswer = reply("playlistNavidrome", id)
    override suspend fun playlistAccounts(id: String, body: AccountsRequest): NavidromeAnswer = reply("playlistAccounts", id, body)
    override suspend fun playlistAutomation(id: String, body: AutomationRequest): AutomationAnswer = reply("playlistAutomation", id, body)
    override suspend fun scanPlaylist(id: String, body: ScanRequest): TaskStarted = reply("scanPlaylist", id, body)
    override suspend fun downloadMissing(id: String): TaskStarted = reply("downloadMissing", id)
    override suspend fun matchTrack(id: String, body: MatchRequest): RowAnswer = reply("matchTrack", id, body)
    override suspend fun sourceMatch(id: String, body: SourceMatchRequest): RowAnswer = reply("sourceMatch", id, body)
    override suspend fun publishPlaylist(id: String): NavidromeAnswer = reply("publishPlaylist", id)
    override suspend fun navidromePlaylist(account: String, id: String): NavidromePlaylistAnswer = reply("navidromePlaylist", account, id)
    override suspend fun navidromeAccounts(): NavidromeAccountsAnswer = reply("navidromeAccounts")
    override suspend fun search(query: String, type: String): SearchAnswer = reply("search", query, type)
    override suspend fun album(id: String): AlbumAnswer = reply("album", id)
    override suspend fun artist(id: String): ArtistAnswer = reply("artist", id)
    override suspend fun preview(trackId: String): Preview = reply("preview", trackId)
    override suspend fun download(body: DownloadRequest): TaskStarted = reply("download", body)
    override suspend fun downloadTrack(trackId: String, body: TrackDownloadRequest): TaskStarted = reply("downloadTrack", trackId, body)
    override suspend fun libraryStats(): LibraryStats = reply("libraryStats")
    override suspend fun librarySearch(query: String): LibrarySearchAnswer = reply("librarySearch", query)
    override suspend fun libraryCheck(body: LibraryCheckRequest): LibraryCheckAnswer = reply("libraryCheck", body)
    override suspend fun refreshLibrary(): TaskStarted = reply("refreshLibrary")
    override suspend fun mixes(): MixesAnswer = reply("mixes")
    override suspend fun mixSettings(body: MixSettingsChange): MixesAnswer = reply("mixSettings", body)
    override suspend fun generateMixes(): TaskStarted = reply("generateMixes")
    override suspend fun keepTrack(deezerId: String): MixesAnswer = reply("keepTrack", deezerId)
    override suspend fun removeTrack(deezerId: String): MixesAnswer = reply("removeTrack", deezerId)
    override suspend fun restoreTrack(deezerId: String): MixesAnswer = reply("restoreTrack", deezerId)
    override suspend fun keepPending(body: IdsRequest): MixesAnswer = reply("keepPending", body)
    override suspend fun emptyTrash(): MixesAnswer = reply("emptyTrash")
    override suspend fun fixMetadata(): TaskStarted = reply("fixMetadata")
    override suspend fun undoMetadata(): TaskStarted = reply("undoMetadata")
    override suspend fun deezerMixes(): DeezerMixesAnswer = reply("deezerMixes")
    override suspend fun followMix(body: FollowMixRequest): FollowAnswer = reply("followMix", body)
}
