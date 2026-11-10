package io.github.catchow0.d2n.testutil

import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.StoredSession
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

/** The session in memory, with DataStoreSettingsStore's rules: a new server
 * forgets the token and the profile. */
class FakeSettingsStore(initial: StoredSession = StoredSession(ready = true)) : SettingsStore {
    private val flow = MutableStateFlow(initial)
    override val state: StateFlow<StoredSession> = flow

    override suspend fun setServer(url: String, authDisabled: Boolean) = flow.update {
        if (it.serverUrl == url) it.copy(authDisabled = authDisabled)
        else it.copy(serverUrl = url, authDisabled = authDisabled, token = null, profile = null)
    }

    override suspend fun setToken(token: String?) = flow.update { it.copy(token = token) }
    override suspend fun setProfile(id: String?) = flow.update { it.copy(profile = id) }
    override suspend fun setDeviceName(name: String) = flow.update { it.copy(deviceName = name) }
    override suspend fun setLastUpdateCheck(epochMillis: Long) = flow.update { it.copy(lastUpdateCheck = epochMillis) }
}
