package io.github.catchow0.d2n.ui.playlists

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
        }
        if (state.loading || state.scanning) {
            androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
        state.preview?.let { p ->
            Text(p.playlistTitle, style = MaterialTheme.typography.titleMedium)
            Text("${p.matchedCount ?: 0} matched / ${p.unmatchedCount ?: 0} unmatched / ${p.uncheckedCount ?: 0} unchecked", style = MaterialTheme.typography.bodySmall)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(p.rows, key = { "${it.number}" }) { row ->
                    PlaylistRowView(row)
                }
            }
        }
    }
}

@Composable
private fun PlaylistRowView(row: PlaylistRow) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(row.deezerName.ifBlank { "${row.deezerArtist} - ${row.deezerTitle}" })
        Text(
            when (row.matched) { true -> "Matched: ${row.sourceName}"; false -> "Unmatched"; null -> "Unchecked" },
            style = MaterialTheme.typography.bodySmall,
            color = if (row.matched == true) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (row.downloaded) Text("Downloaded", style = MaterialTheme.typography.labelSmall)
    }
}