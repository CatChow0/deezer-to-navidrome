package io.github.catchow0.d2n.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun SettingsScreen(viewModel: SettingsViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.loading) CircularProgressIndicator()
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Text("Settings", style = MaterialTheme.typography.titleSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f, fill = false)) {
            state.settings.keys.sorted().forEach { key ->
                item(key) {
                    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column(Modifier.weight(1f)) {
                            Text(key)
                            Text(state.working[key]?.toString() ?: "—", style = MaterialTheme.typography.bodySmall)
                        }
                        if (state.choices?.containsKey(key) == true) {
                            Button(onClick = { viewModel.cycle(key) }) { Text("Cycle") }
                        }
                    }
                }
            }
            item("status") {
                Text("Clear data:", style = MaterialTheme.typography.titleSmall)
                listOf("library-cache", "preview-state", "playlists", "all", "dedup-report", "dedup-choices").forEach { what ->
                    OutlinedButton(onClick = { viewModel.clear(what) }, modifier = Modifier.fillMaxWidth()) { Text(what) }
                }
                state.message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
        }
    }
}