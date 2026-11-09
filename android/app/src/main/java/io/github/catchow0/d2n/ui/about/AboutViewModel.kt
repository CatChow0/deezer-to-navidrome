package io.github.catchow0.d2n.ui.about

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.update.BuildIdentity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** This build, the server it talks to, and signing out. The update check
 * lives in UpdateViewModel, so About and the banner always agree. */
class AboutViewModel(
    private val api: () -> D2nApi,
    private val store: SettingsStore,
    own: BuildIdentity,
) : ViewModel() {
    data class UiState(
        val appVersion: String,
        val commit: String,
        val builtAt: String,
        val server: String?,
        val signedIn: Boolean,
        val signedOut: Boolean = false,
    )

    private val _state = MutableStateFlow(
        UiState(
            appVersion = own.versionName, commit = own.commit, builtAt = own.builtAt,
            server = store.state.value.serverUrl, signedIn = store.state.value.token != null,
        ),
    )
    val state: StateFlow<UiState> = _state

    /** Revokes this phone's token on the server when it answers, and forgets
     * it here in any case. */
    fun signOut() {
        viewModelScope.launch {
            try {
                apiCall { api().logout() }
            } catch (e: ApiFailure) {
                // Unreachable or already revoked: the token goes anyway.
            }
            store.setToken(null)
            _state.update { it.copy(signedIn = false, signedOut = true) }
        }
    }
}
