package io.github.catchow0.d2n.ui.signin

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.ForgotRequest
import io.github.catchow0.d2n.data.NewPassword
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.Brand
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.components.rememberCopy
import io.github.catchow0.d2n.ui.theme.D2nColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

const val RECOVERY_HINT = "Keep this recovery code somewhere safe: with it, you choose a new password if you forget yours. " +
    "It is shown only now; Settings → Sign-in and other apps makes you a new one."

/** A recovery code, shown once, with a way to copy it before going on. */
@Composable
fun ColumnScope.RecoveryCode(code: String, lead: String? = null, continueLabel: String = "Continue", onContinue: () -> Unit) {
    val copy = rememberCopy()
    Text("Your recovery code", style = MaterialTheme.typography.headlineSmall)
    Text((lead?.let { "$it " } ?: "") + RECOVERY_HINT, style = MaterialTheme.typography.bodyMedium, color = D2nColors.Muted)
    Text(code, Modifier.align(Alignment.CenterHorizontally), style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Monospace)
    D2nButton("Copy", { copy("Recovery code", code, true) }, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost)
    D2nButton(continueLabel, onContinue, Modifier.fillMaxWidth())
}

/** What the two screens below share: fields, a busy flag, an error, and the code once it came. */
data class RecoveryState(
    val username: String = "",
    val code: String = "",
    val password: String = "",
    val confirm: String = "",
    val busy: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
    /** The next recovery code, shown once the password is changed. */
    val recoveryCode: String? = null,
)

/** An account made by an Admin, signed in with its temporary password: its user
 * chooses their own before anything else. The server signs every device out and
 * gives this one a new token. */
class FirstPasswordViewModel(
    private val api: () -> D2nApi,
    private val store: SettingsStore,
    private val defaultDevice: String,
) : ViewModel() {
    private val _state = MutableStateFlow(RecoveryState())
    val state: StateFlow<RecoveryState> = _state

    fun onPassword(text: String) = _state.update { it.copy(password = text) }
    fun onConfirm(text: String) = _state.update { it.copy(confirm = text) }

    fun submit() {
        val current = _state.value
        if (current.busy || current.password.isEmpty()) return
        if (current.password != current.confirm) return _state.update { it.copy(error = PASSWORDS_DIFFER) }
        _state.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            try {
                val device = store.state.value.deviceName ?: defaultDevice
                val signed = apiCall { api().firstPassword(NewPassword(current.password, device)) }
                store.setToken(signed.token)
                _state.update { it.copy(busy = false, password = "", confirm = "", recoveryCode = signed.recoveryCode.orEmpty()) }
            } catch (e: ApiFailure) {
                _state.update { it.copy(busy = false, error = e.describe()) }
            }
        }
    }
}

/** Forgot password: the username, the account's recovery code and a new
 * password. The Super-Admin can also have a one-time code written on the server. */
class ForgotViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(RecoveryState())
    val state: StateFlow<RecoveryState> = _state

    fun onUsername(text: String) = _state.update { it.copy(username = text) }
    fun onCode(text: String) = _state.update { it.copy(code = text) }
    fun onPassword(text: String) = _state.update { it.copy(password = text) }

    fun submit() {
        val s = _state.value
        if (s.busy || s.username.isBlank() || s.code.isBlank() || s.password.isEmpty()) return
        _state.update { it.copy(busy = true, error = null, notice = null) }
        viewModelScope.launch {
            try {
                val answer = apiCall { api().forgot(ForgotRequest(s.username.trim(), s.code.trim(), s.password)) }
                _state.update { it.copy(busy = false, password = "", code = "", recoveryCode = answer.recoveryCode) }
            } catch (e: ApiFailure) {
                _state.update { it.copy(busy = false, error = e.describe()) }
            }
        }
    }

    fun writeSuperAdminCode() {
        _state.update { it.copy(busy = true, error = null, notice = null) }
        viewModelScope.launch {
            try {
                val written = apiCall { api().forgotSuperAdmin() }
                _state.update {
                    it.copy(busy = false, notice = "A one-time code is in ${written.file}, in the app's data folder on the server, for ${written.minutes} minutes. Enter it above as the recovery code.")
                }
            } catch (e: ApiFailure) {
                _state.update { it.copy(busy = false, error = e.describe()) }
            }
        }
    }
}

@Composable
fun FirstPasswordScreen(vm: FirstPasswordViewModel, onDone: () -> Unit, onSignOut: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    SignInFrame {
        Brand()
        val code = state.recoveryCode
        if (code != null) {
            RecoveryCode(code, lead = "Your password is saved.", onContinue = onDone)
            return@SignInFrame
        }
        Text("Choose your password", style = MaterialTheme.typography.headlineSmall)
        Text("Your account was made with a temporary password: choose your own.", style = MaterialTheme.typography.bodyMedium, color = D2nColors.Muted)
        D2nTextField(state.password, vm::onPassword, "New password", supporting = "At least 8 characters.", password = true, enabled = !state.busy)
        D2nTextField(state.confirm, vm::onConfirm, "Confirm the password", password = true, imeAction = ImeAction.Go, onIme = vm::submit, enabled = !state.busy)
        state.error?.let { Banner(it, BannerTone.Error) }
        D2nButton(if (state.busy) "Saving…" else "Save my password", vm::submit, Modifier.fillMaxWidth(), enabled = !state.busy && state.password.isNotEmpty())
        D2nButton("Sign out", onSignOut, Modifier.align(Alignment.CenterHorizontally), kind = ButtonKind.Link)
    }
}

@Composable
fun ForgotScreen(vm: ForgotViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    SignInFrame {
        Brand()
        val code = state.recoveryCode
        if (code != null) {
            RecoveryCode(code, lead = "Your password is changed.", continueLabel = "Sign in", onContinue = onBack)
            return@SignInFrame
        }
        Text("Forgot your password", style = MaterialTheme.typography.headlineSmall)
        Text("Enter your username, your recovery code and a new password. Lost your code? An Admin makes you a new one.", style = MaterialTheme.typography.bodyMedium, color = D2nColors.Muted)
        D2nTextField(state.username, vm::onUsername, "Username", enabled = !state.busy)
        D2nTextField(state.code, vm::onCode, "Recovery code", enabled = !state.busy)
        D2nTextField(state.password, vm::onPassword, "New password", supporting = "At least 8 characters.", password = true, imeAction = ImeAction.Go, onIme = vm::submit, enabled = !state.busy)
        state.error?.let { Banner(it, BannerTone.Error) }
        state.notice?.let { Banner(it, BannerTone.Info) }
        D2nButton(if (state.busy) "Changing…" else "Change my password", vm::submit, Modifier.fillMaxWidth(), enabled = !state.busy)
        Text("The Super-Admin without its code can get a one-time code in the app's data folder on the server.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
        D2nButton("Write a code on the server", vm::writeSuperAdminCode, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost, enabled = !state.busy)
        D2nButton("Back to sign-in", onBack, Modifier.align(Alignment.CenterHorizontally), kind = ButtonKind.Link)
    }
}
