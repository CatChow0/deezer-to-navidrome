package io.github.catchow0.d2n.ui.about

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.main.SessionViewModel
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.update.UpdateViewModel

@Composable
private fun InfoRow(label: String, value: String?) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, Modifier.weight(0.35f), color = D2nColors.Muted, style = MaterialTheme.typography.bodyMedium)
        Text(value ?: "—", Modifier.weight(0.65f), style = MaterialTheme.typography.bodyMedium)
    }
}

/** More: this build, the server, updates, and signing out. */
@Composable
fun AboutScreen(
    vm: AboutViewModel,
    updates: UpdateViewModel,
    session: SessionViewModel.UiState,
    onSignedOut: () -> Unit,
    onOtherServer: () -> Unit,
    onOpenNotes: () -> Unit = {},
    onOpenHelp: () -> Unit = {},
    onOpenSettings: () -> Unit = {},
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val update by updates.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.signedOut) { if (state.signedOut) onSignedOut() }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("More", style = MaterialTheme.typography.headlineSmall)
        GlassCard(Modifier.fillMaxWidth()) {
            Text("This app", style = MaterialTheme.typography.titleSmall)
            InfoRow("Version", "${state.appVersion} (${state.commit})")
            InfoRow("Built", state.builtAt)
        }
        GlassCard(Modifier.fillMaxWidth()) {
            Text("Server", style = MaterialTheme.typography.titleSmall)
            InfoRow("Address", state.server)
            InfoRow("Version", session.serverVersion)
            InfoRow("API", session.apiVersion?.toString())
        }
        GlassCard(Modifier.fillMaxWidth()) {
            Text("Updates", style = MaterialTheme.typography.titleSmall)
            Text("The app updates itself from your server.", color = D2nColors.Muted, style = MaterialTheme.typography.bodyMedium)
            D2nButton(if (update.checking) "Checking…" else "Check for updates", { updates.check(force = true) }, kind = ButtonKind.Ghost, enabled = !update.checking)
            update.checked?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
        D2nButton("Settings", onOpenSettings, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost)
        D2nButton("What's new", onOpenNotes, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost)
        D2nButton("Help", onOpenHelp, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost)
        if (state.signedIn) {
            D2nButton("Sign out", vm::signOut, Modifier.fillMaxWidth(), kind = ButtonKind.Danger)
        } else {
            D2nButton("Use another server", onOtherServer, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost)
        }
        Text(
            "Fonts: Unbounded and Instrument Sans, under the SIL Open Font License.",
            color = D2nColors.Faint,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
