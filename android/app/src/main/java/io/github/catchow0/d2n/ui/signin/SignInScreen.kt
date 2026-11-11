package io.github.catchow0.d2n.ui.signin

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.Brand
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.theme.D2nColors

const val DEVICE_HINT = "Shown in Settings → Sign-in and other apps, where you can sign this phone out."

@Composable
fun SignInScreen(
    vm: SignInViewModel,
    server: String?,
    notice: String?,
    onNext: (SignInViewModel.Next) -> Unit,
    onOtherServer: () -> Unit,
    onForgot: () -> Unit,
) {
    val state by vm.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.next) {
        state.next?.let {
            vm.consumed()
            onNext(it)
        }
    }
    SignInFrame {
        Brand()
        Text("Sign in", style = MaterialTheme.typography.headlineSmall)
        server?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = D2nColors.Faint) }
        notice?.let { Banner(it, BannerTone.Info) }
        D2nTextField(state.username, vm::onUsername, "Username", enabled = !state.busy)
        D2nTextField(state.password, vm::onPassword, "Password", password = true, enabled = !state.busy)
        D2nTextField(
            state.device, vm::onDevice, "This phone's name",
            supporting = DEVICE_HINT,
            imeAction = ImeAction.Go,
            onIme = vm::submit,
            enabled = !state.busy,
        )
        state.error?.let { Banner(it, if (state.waitSeconds > 0) BannerTone.Warn else BannerTone.Error) }
        D2nButton(if (state.busy) "Signing in…" else "Sign in", vm::submit, Modifier.fillMaxWidth(), enabled = state.canSubmit)
        D2nButton("Forgot your password?", onForgot, Modifier.align(Alignment.CenterHorizontally), kind = ButtonKind.Link)
        D2nButton("Use another server", onOtherServer, Modifier.align(Alignment.CenterHorizontally), kind = ButtonKind.Link)
    }
}
