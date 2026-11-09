package io.github.catchow0.d2n.ui.signin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.Credentials
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.NotThisServer
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

const val TOO_MANY = "Too many attempts. Try again in %d s."

/** Signing this phone in with the app's account; the server gives it a token. */
class SignInViewModel(
    private val api: () -> D2nApi,
    private val store: SettingsStore,
    private val defaultDevice: String,
    private val ticker: suspend (Long) -> Unit = { delay(it) },
) : ViewModel() {
    enum class Next { Main, Setup }

    data class UiState(
        val username: String = "",
        val password: String = "",
        val device: String = "",
        val busy: Boolean = false,
        val error: String? = null,
        val waitSeconds: Int = 0,
        val next: Next? = null,
    ) {
        val canSubmit: Boolean get() = !busy && waitSeconds == 0 && username.isNotBlank() && password.isNotEmpty()
    }

    private val _state = MutableStateFlow(UiState(device = store.state.value.deviceName ?: defaultDevice))
    val state: StateFlow<UiState> = _state

    fun onUsername(text: String) = _state.update { it.copy(username = text) }
    fun onPassword(text: String) = _state.update { it.copy(password = text) }
    fun onDevice(text: String) = _state.update { it.copy(device = text) }

    fun submit() {
        val current = _state.value
        if (!current.canSubmit) return
        val device = current.device.trim().ifEmpty { defaultDevice }
        _state.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            try {
                val signed = apiCall { api().login(Credentials(current.username.trim(), current.password, device)) }
                store.setDeviceName(device)
                store.setToken(signed.token)
                _state.update { it.copy(busy = false, password = "", next = Next.Main) }
            } catch (e: ApiError) {
                _state.update { it.copy(busy = false) }
                when {
                    e.status == 429 -> countDown(e.retryAfterSeconds ?: 30)
                    e.code == "setup_needed" -> _state.update { it.copy(next = Next.Setup) }
                    else -> _state.update { it.copy(error = e.message) }
                }
            } catch (e: ApiFailure) {
                _state.update { it.copy(busy = false, error = e.describe()) }
            }
        }
    }

    private fun countDown(seconds: Int) {
        viewModelScope.launch {
            for (left in seconds downTo 1) {
                _state.update { it.copy(waitSeconds = left, error = TOO_MANY.format(left)) }
                ticker(1_000)
            }
            _state.update { it.copy(waitSeconds = 0, error = null) }
        }
    }

    fun consumed() = _state.update { it.copy(next = null) }
}

/** How a failure reads on the sign-in screens. */
internal fun ApiFailure.describe(): String = when (this) {
    is Unreachable -> UNREACHABLE
    is NotThisServer -> NOT_THIS_SERVER
    is ApiError -> message ?: UNREACHABLE
}
