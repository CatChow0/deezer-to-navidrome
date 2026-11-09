package io.github.catchow0.d2n.ui.signin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ServerAddress
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.isCleartext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.HttpUrl

const val HTTP_WARNING =
    "This address is not encrypted: your password and data travel in clear. Use it only on your local network or Tailscale."
const val NOT_THIS_SERVER =
    "This address does not answer as Deezer → Navidrome. If a login page (Authelia) protects it, let /api/v1/ through, as the README shows."
const val UNREACHABLE = "The server cannot be reached. Check the address and your connection."
const val TOO_OLD = "This server does not have the app's API yet. Update Deezer → Navidrome to 1.17.0 or later."
const val BAD_ADDRESS = "Enter the address of your server, such as https://music.example.com."

/** The server's address: checked before anything is saved. */
class ServerViewModel(
    private val probe: suspend (HttpUrl) -> ServerProbe,
    private val store: SettingsStore,
) : ViewModel() {
    enum class Next { SignIn, Setup, Main }

    data class UiState(
        val input: String = "",
        val cleartext: Boolean = false,
        val checking: Boolean = false,
        val error: String? = null,
        val next: Next? = null,
    )

    private val _state = MutableStateFlow(UiState().withInput(store.state.value.serverUrl.orEmpty()))
    val state: StateFlow<UiState> = _state

    private fun UiState.withInput(text: String) =
        copy(input = text, cleartext = ServerAddress.normalize(text)?.isCleartext == true, error = null)

    fun onInput(text: String) = _state.update { it.withInput(text) }

    fun submit() {
        if (_state.value.checking) return
        val url = ServerAddress.normalize(_state.value.input) ?: return _state.update { it.copy(error = BAD_ADDRESS) }
        _state.update { it.copy(checking = true, error = null) }
        viewModelScope.launch {
            val next = when (val answer = probe(url)) {
                ServerProbe.Required -> Next.SignIn.also { store.setServer(url.toString(), authDisabled = false) }
                ServerProbe.Setup -> Next.Setup.also { store.setServer(url.toString(), authDisabled = false) }
                ServerProbe.Disabled -> Next.Main.also {
                    store.setServer(url.toString(), authDisabled = true)
                    store.setToken(null)
                }
                ServerProbe.TooOld -> return@launch fail(TOO_OLD)
                is ServerProbe.NotThisServer -> return@launch fail(NOT_THIS_SERVER)
                is ServerProbe.Unreachable -> return@launch fail(UNREACHABLE)
            }
            _state.update { it.copy(checking = false, next = next) }
        }
    }

    private fun fail(message: String) = _state.update { it.copy(checking = false, error = message) }

    /** The screen moved on. */
    fun consumed() = _state.update { it.copy(next = null) }
}
