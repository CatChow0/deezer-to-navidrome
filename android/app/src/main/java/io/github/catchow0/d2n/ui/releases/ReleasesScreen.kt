package io.github.catchow0.d2n.ui.releases

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
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
import androidx.compose.foundation.layout.size
import coil.compose.AsyncImage

@Composable
fun ReleasesScreen(viewModel: ReleasesViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.loading) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator() }
        }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (!state.connected) Text("Connect a Deezer account in Settings to follow releases.")
        Text("Releases (${state.releases.size})", style = MaterialTheme.typography.titleSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f, fill = false)) {
            items(state.releases, key = { it.id }) { r ->
                Card(Modifier.fillMaxWidth()) { Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AsyncImage(model = r.cover, contentDescription = r.title, modifier = Modifier.size(48.dp))
                    Column(Modifier.weight(1f)) {
                        Text(r.title, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        Text(r.artist, style = MaterialTheme.typography.bodySmall, maxLines = 1)
                        Text("${r.recordType} - ${r.releaseDate}", style = MaterialTheme.typography.bodySmall, maxLines=1)
                    }
                    if (r.featured) Text("featured")
                }
                }
            }
        }
    }
}