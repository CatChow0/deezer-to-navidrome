package io.github.catchow0.d2n.ui.signin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.Credentials
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

const val PASSWORDS_DIFFER = "The two passwords differ."

/** A server with no account yet: create it from the phone, which is then signed in. */
class SetupViewModel(
    private val api: () -> D2nApi,
    private val store: SettingsStore,
    private val defaultDevice: String,
) : ViewModel() {
    enum class Next { Main }

    data class UiState(
        val username: String = "",
        val password: String = "",
        val confirm: String = "",
        val device: String = "",
        val busy: Boolean = false,
        val error: String? = null,
        val next: Next? = null,
    ) {
        val canSubmit: Boolean get() = !busy && username.isNotBlank() && password.isNotEmpty() && confirm.isNotEmpty()
    }

    private val _state = MutableStateFlow(UiState(device = store.state.value.deviceName ?: defaultDevice))
    val state: StateFlow<UiState> = _state

    fun onUsername(text: String) = _state.update { it.copy(username = text) }
    fun onPassword(text: String) = _state.update { it.copy(password = text) }
    fun onConfirm(text: String) = _state.update { it.copy(confirm = text) }
    fun onDevice(text: String) = _state.update { it.copy(device = text) }

    fun submit() {
        val current = _state.value
        if (!current.canSubmit) return
        if (current.password != current.confirm) return _state.update { it.copy(error = PASSWORDS_DIFFER) }
        val device = current.device.trim().ifEmpty { defaultDevice }
        _state.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            try {
                // The server checks the password's length, and says so.
                val signed = apiCall { api().setup(Credentials(current.username.trim(), current.password, device)) }
                store.setDeviceName(device)
                store.setToken(signed.token)
                _state.update { it.copy(busy = false, password = "", confirm = "", next = Next.Main) }
            } catch (e: ApiFailure) {
                _state.update { it.copy(busy = false, error = e.describe()) }
            }
        }
    }

    fun consumed() = _state.update { it.copy(next = null) }
}
