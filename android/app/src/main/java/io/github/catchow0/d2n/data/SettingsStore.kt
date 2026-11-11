package io.github.catchow0.d2n.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/** What the app remembers. `ready` turns true once it has been read. */
data class StoredSession(
    val ready: Boolean = false,
    val serverUrl: String? = null,
    val token: String? = null,
    val authDisabled: Boolean = false,
    val profile: String? = null,
    val deviceName: String? = null,
    val lastUpdateCheck: Long = 0,
)

interface SettingsStore {
    val state: StateFlow<StoredSession>

    /** A new address forgets the token and the profile: one server at a time. */
    suspend fun setServer(url: String, authDisabled: Boolean)
    suspend fun setToken(token: String?)
    suspend fun setProfile(id: String?)
    suspend fun setDeviceName(name: String)
    suspend fun setLastUpdateCheck(epochMillis: Long)
}

/** The session in a DataStore, the token sealed by [box]. A token that no
 * longer opens (the Keystore key is gone) reads as signed out. */
class DataStoreSettingsStore(
    private val dataStore: DataStore<Preferences>,
    private val box: SecretBox,
    scope: CoroutineScope,
) : SettingsStore {
    override val state: StateFlow<StoredSession> = dataStore.data
        .map { prefs ->
            StoredSession(
                ready = true,
                serverUrl = prefs[SERVER],
                token = prefs[TOKEN]?.let { runCatching { box.open(it) }.getOrNull() },
                authDisabled = prefs[AUTH_DISABLED] ?: false,
                profile = prefs[PROFILE],
                deviceName = prefs[DEVICE],
                lastUpdateCheck = prefs[LAST_UPDATE_CHECK] ?: 0L,
            )
        }
        .stateIn(scope, SharingStarted.Eagerly, StoredSession())

    /** A setter returns once [state] shows its value: the next request (its
     * headers read [state]) then carries it. */
    private suspend fun shown(check: (StoredSession) -> Boolean) {
        withTimeoutOrNull(2_000) { state.first { it.ready && check(it) } }
    }

    override suspend fun setServer(url: String, authDisabled: Boolean) {
        dataStore.edit { prefs ->
            if (prefs[SERVER] != url) {
                prefs.remove(TOKEN)
                prefs.remove(PROFILE)
            }
            prefs[SERVER] = url
            prefs[AUTH_DISABLED] = authDisabled
        }
        shown { it.serverUrl == url && it.authDisabled == authDisabled }
    }

    override suspend fun setToken(token: String?) {
        // The first seal makes the Keystore key: up to seconds, never on the main thread.
        val sealed = token?.let {
            withContext(Dispatchers.IO) {
                try {
                    box.seal(it)
                } catch (e: Exception) {
                    // A keyset moved from another phone: a new key, then the token.
                    box.reset()
                    box.seal(it)
                }
            }
        }
        dataStore.edit { prefs -> if (sealed == null) prefs.remove(TOKEN) else prefs[TOKEN] = sealed }
        shown { it.token == token }
    }

    override suspend fun setProfile(id: String?) {
        dataStore.edit { prefs -> if (id == null) prefs.remove(PROFILE) else prefs[PROFILE] = id }
        shown { it.profile == id }
    }

    override suspend fun setDeviceName(name: String) {
        dataStore.edit { prefs -> prefs[DEVICE] = name }
        shown { it.deviceName == name }
    }

    override suspend fun setLastUpdateCheck(epochMillis: Long) {
        dataStore.edit { prefs -> prefs[LAST_UPDATE_CHECK] = epochMillis }
        shown { it.lastUpdateCheck == epochMillis }
    }

    private companion object {
        val SERVER = stringPreferencesKey("server_url")
        val TOKEN = stringPreferencesKey("token_sealed")
        val AUTH_DISABLED = booleanPreferencesKey("auth_disabled")
        val PROFILE = stringPreferencesKey("profile")
        val DEVICE = stringPreferencesKey("device_name")
        val LAST_UPDATE_CHECK = longPreferencesKey("last_update_check")
    }
}
