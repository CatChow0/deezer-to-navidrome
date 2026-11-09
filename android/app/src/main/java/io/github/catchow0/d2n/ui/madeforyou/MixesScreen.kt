package io.github.catchow0.d2n.ui.madeforyou

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
import io.github.catchow0.d2n.data.MixTrack
import coil.compose.AsyncImage
import androidx.compose.foundation.layout.size
import androidx.compose.ui.layout.ContentScale

@Composable
fun MixesScreen(viewModel: MixesViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.loading) { androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() } }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Text("On trial (${state.onTrial.size})", style = MaterialTheme.typography.titleSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f, fill = false)) {
            items(state.onTrial, key = { it.id }) { t -> MixTrackRow(t, onKeep = { viewModel.keep(t.id) }, onRemove = { viewModel.remove(t.id) }) }
        }
        Text("Pending (${state.pending.size})", style = MaterialTheme.typography.titleSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f, fill = false)) {
            items(state.pending, key = { it.id }) { t -> MixTrackRow(t, onKeep = { viewModel.keep(t.id) }, onRemove = { viewModel.remove(t.id) }) }
        }
        Text("Trash (${state.trash.size})", style = MaterialTheme.typography.titleSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f, fill = false)) {
            items(state.trash, key = { it.id }) { t -> MixTrackRow(t, onRestore = { viewModel.restore(t.id) }) }
        }
    }
}

@Composable
private fun MixTrackRow(track: MixTrack, onKeep: (() -> Unit)? = null, onRemove: (() -> Unit)? = null, onRestore: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        AsyncImage(model = track.cover, contentDescription = track.title, modifier = Modifier.size(48.dp), contentScale = ContentScale.Crop)
        Column(Modifier.weight(1f)) {
            Text("${track.artist} - ${track.title}", maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            Text(track.album, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
        }
        if (onKeep != null) Button(onClick = onKeep) { Text("Keep") }
        if (onRemove != null) Button(onClick = onRemove) { Text("Remove") }
        if (onRestore != null) Button(onClick = onRestore) { Text("Restore") }
    }
}