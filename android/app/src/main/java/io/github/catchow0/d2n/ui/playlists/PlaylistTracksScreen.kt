package io.github.catchow0.d2n.ui.playlists

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.data.PlaylistRow

@Composable
fun PlaylistTracksScreen(viewModel: PlaylistTracksViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { viewModel.scan(true) }) { Text("Quick scan") }
            Button(onClick = { viewModel.scan(false) }) { Text("Full scan") }
            Button(onClick = viewModel::downloadMissing) { Text("Download missing") }
            Button(onClick = viewModel::publish) { Text("Publish") }
            Button(onClick = viewModel::openSettings) { Text("Settings") }
        }
        if (state.loading || state.scanning) {
            androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
        if (state.showSettings) {
            AlertDialog(
                onDismissRequest = viewModel::closeSettings,
                title = { Text("Playlist settings") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Target Navidrome accounts", style = MaterialTheme.typography.labelLarge)
                        state.accounts.forEach { acc ->
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Checkbox(checked = acc.id in state.selectedAccounts, onCheckedChange = { viewModel.toggleAccount(acc.id) })
                                Text(acc.label.ifBlank { acc.username.ifBlank { acc.id } })
                            }
                        }
                        Text("Automation", style = MaterialTheme.typography.labelLarge)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = state.autoScan, onCheckedChange = viewModel::setAutoScan)
                            Text("Auto scan")
                        }
                        if (state.autoScan) {
                            OutlinedTextField(value = state.autoInterval, onValueChange = viewModel::setAutoInterval, label = { Text("Interval (min)") })
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = state.autoDownload, onCheckedChange = viewModel::setAutoDownload)
                                Text("Download missing after scan")
                            }
                        }
                    }
                },
                confirmButton = { Button(onClick = viewModel::saveSettings, enabled = !state.settingsLoading) { Text("Save") } },
                dismissButton = { Button(onClick = viewModel::closeSettings) { Text("Cancel") } },
            )
        }
        state.preview?.let { p ->
            Text(p.playlistTitle, style = MaterialTheme.typography.titleMedium)
            Text("${p.matchedCount ?: 0} matched / ${p.unmatchedCount ?: 0} unmatched / ${p.uncheckedCount ?: 0} unchecked", style = MaterialTheme.typography.bodySmall)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(p.rows, key = { "${it.number}" }) { row ->
                    PlaylistRowView(row) { mode -> row.trackId?.let { viewModel.mark(it, mode) } }
                }
            }
        }
    }
}

@Composable
private fun PlaylistRowView(row: PlaylistRow, onMark: (String) -> Unit = {}) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(row.deezerName.ifBlank { "${row.deezerArtist} - ${row.deezerTitle}" })
        Text(
            when (row.matched) { true -> "Matched: ${row.sourceName}"; false -> "Unmatched"; null -> "Unchecked" },
            style = MaterialTheme.typography.bodySmall,
            color = if (row.matched == true) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (row.downloaded) Text("Downloaded", style = MaterialTheme.typography.labelSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            if (row.matched != false) Button(onClick = { onMark("missing") }) { Text("Missing") }
            if (row.matched != null) Button(onClick = { onMark("auto") }) { Text("Auto") }
        }
    }
}