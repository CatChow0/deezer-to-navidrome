package io.github.catchow0.d2n.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.AppUser
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.Profile
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

const val SIGNED_OUT = "This phone was signed out: sign in again."

/** The profiles this server has, the one this phone shows, and whether the
 * phone is still signed in. */
class SessionViewModel(
    private val api: () -> D2nApi,
    private val store: SettingsStore,
) : ViewModel() {
    data class UiState(
        val profiles: List<Profile> = emptyList(),
        val selected: Profile? = null,
        val serverVersion: String? = null,
        val apiVersion: Int? = null,
        val loading: Boolean = true,
        val error: String? = null,
        val signedOutMessage: String? = null,
        /** The account signed in, and whether it is an Admin (Settings → Users). */
        val user: AppUser? = null,
        val isAdmin: Boolean = false,
        /** Its password is a temporary one: the server answers nothing else until it is changed. */
        val mustChange: Boolean = false,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    fun refresh() {
        _state.update { it.copy(loading = true) }
        viewModelScope.launch {
            try {
                val info = apiCall { api().info() }
                val stored = store.state.value.profile
                // A profile deleted on the web: back to the one the server chose.
                val chosen = info.profiles.firstOrNull { it.id == stored }
                    ?: info.profiles.firstOrNull { it.id == info.profile }
                    ?: info.profiles.firstOrNull()
                if (chosen?.id != stored) store.setProfile(chosen?.id)
                _state.update {
                    it.copy(
                        profiles = info.profiles, selected = chosen, serverVersion = info.version,
                        apiVersion = info.api, loading = false, error = null, user = info.user, isAdmin = info.isAdmin,
                    )
                }
            } catch (e: ApiError) {
                // A 401 is handled by onUnauthorized, from the client itself.
                val mustChange = e.code == "password_change_needed"
                _state.update { it.copy(loading = false, error = if (e.status == 401 || mustChange) null else e.message, mustChange = mustChange) }
            } catch (e: ApiFailure) {
                _state.update { it.copy(loading = false, error = e.message) }
            }
        }
    }

    /** Back in front: profiles may have been added or deleted on the web. */
    fun onStart() = refresh()

    private var wasOnline = true

    /** The server answers again: what could not be read can be now. */
    fun onOnline(online: Boolean) {
        if (online && !wasOnline) refresh()
        wasOnline = online
    }

    fun select(id: String) {
        val profile = _state.value.profiles.firstOrNull { it.id == id } ?: return
        _state.update { it.copy(selected = profile) }
        viewModelScope.launch {
            store.setProfile(id)
            refresh()
        }
    }

    /** The server refused this phone's token: it was signed out from the web,
     * or the password changed. */
    fun onUnauthorized() {
        _state.update { it.copy(signedOutMessage = SIGNED_OUT) }
        viewModelScope.launch { store.setToken(null) }
    }
}
