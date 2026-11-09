package io.github.catchow0.d2n.ui.signin

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.Brand
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.theme.D2nColors

@Composable
fun ServerScreen(vm: ServerViewModel, onNext: (ServerViewModel.Next) -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.next) {
        state.next?.let {
            vm.consumed()
            onNext(it)
        }
    }
    SignInFrame {
        Brand()
        Text("Your server", style = MaterialTheme.typography.headlineSmall)
        Text(
            "The address of Deezer → Navidrome, as you open it in a browser.",
            style = MaterialTheme.typography.bodyMedium,
            color = D2nColors.Muted,
        )
        D2nTextField(
            state.input, vm::onInput, "Server address",
            placeholder = "https://music.example.com",
            keyboardType = KeyboardType.Uri,
            imeAction = ImeAction.Go,
            onIme = vm::submit,
            enabled = !state.checking,
        )
        if (state.cleartext) Banner(HTTP_WARNING, BannerTone.Warn)
        state.error?.let { Banner(it, BannerTone.Error) }
        D2nButton(
            if (state.checking) "Checking…" else "Continue",
            vm::submit,
            Modifier.fillMaxWidth(),
            enabled = !state.checking && state.input.isNotBlank(),
        )
    }
}
