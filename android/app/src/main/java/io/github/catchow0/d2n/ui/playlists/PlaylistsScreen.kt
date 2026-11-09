package io.github.catchow0.d2n.ui.playlists

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import io.github.catchow0.d2n.data.PlaylistTile

@Composable
fun PlaylistsScreen(viewModel: PlaylistsViewModel, onOpenPlaylist: (String) -> Unit = {}) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) {
            val name = uri.lastPathSegment ?: "playlist.csv"
            val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: byteArrayOf()
            viewModel.importCsv(name, bytes)
        }
    }
    LaunchedEffect(Unit) { viewModel.load() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = state.addLink,
                onValueChange = viewModel::onAddLink,
                label = { Text("Add playlist link") },
                modifier = Modifier.weight(1f),
            )
            Button(onClick = viewModel::add) { Text("Add") }
        }
        Button(onClick = { launcher.launch(arrayOf("text/*", "text/csv", "application/csv")) }) { Text("Import CSV") }
        if (state.loading) {
            androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(state.playlists, key = { it.id }) { tile ->
                PlaylistTileRow(tile, onDelete = { viewModel.delete(tile.id) }, onClick = { onOpenPlaylist(tile.id) })
            }
            if (state.navidrome.isNotEmpty()) {
                item { Text("In Navidrome", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 12.dp)) }
                items(state.navidrome, key = { it.id }) { tile ->
                    PlaylistTileRow(tile, onDelete = null)
                }
            }
        }
    }
}

@Composable
private fun PlaylistTileRow(tile: PlaylistTile, onDelete: (() -> Unit)?, onClick: () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        AsyncImage(model = tile.cover, contentDescription = tile.title, modifier = Modifier.size(56.dp), contentScale = ContentScale.Crop)
        Column(Modifier.weight(1f)) {
            Text(tile.title.ifBlank { tile.deezerTitle }, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(tile.subtitle.ifBlank { tile.source }, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodySmall)
            Text(tile.accounts.joinToString(", "), style = MaterialTheme.typography.labelSmall)
        }
        if (onDelete != null) TextButton(onClick = onDelete) { Text("Delete") }
    }
}