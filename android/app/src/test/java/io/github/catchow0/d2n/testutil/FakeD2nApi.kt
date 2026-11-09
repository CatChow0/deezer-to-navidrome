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
}
