package io.github.catchow0.d2n.ui.search

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.ui.components.AudioPreview

@Composable
fun SearchScreen(viewModel: SearchViewModel, queryState: SearchState? = null) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val s = queryState ?: state
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = s.query,
            onValueChange = { viewModel.onQuery(it) },
            label = { Text("Search Deezer") },
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("track", "album", "artist").forEach { type ->
                FilterChip(
                    selected = s.type == type,
                    onClick = { viewModel.onType(type) },
                    label = { Text(type.replaceFirstChar { it.uppercase() }) },
                )
            }
            FilterChip(
                selected = false,
                onClick = { viewModel.submit() },
                label = { Text("Search") },
            )
        }
        if (s.loading) {
            BoxCenterProgress()
        }
        s.previewUrl?.let { url ->
            AudioPreview(url) { viewModel.closePreview() }
        }
        s.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(s.results, key = { "${it.type}:${it.id}" }) { item ->
                SearchResultRow(item, s.inLibrary["${item.type}:${item.id}"] == true)
            }
        }
    }
}

@Composable
private fun BoxCenterProgress() {
    androidx.compose.foundation.layout.Box(
        Modifier.fillMaxWidth().padding(24.dp),
        contentAlignment = Alignment.Center,
    ) { CircularProgressIndicator() }
}

@Composable
fun SearchResultRow(item: SearchResult, inLibrary: Boolean, onPreview: () -> Unit = {}) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        AsyncImage(
            model = item.cover,
            contentDescription = item.title,
            modifier = Modifier.size(56.dp),
            contentScale = ContentScale.Crop,
        )
        Column(Modifier.weight(1f)) {
            Text(item.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(item.artist ?: item.subtitle ?: item.album ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodySmall)
            if (inLibrary) Text("In library", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall)
            if (item.type == "track") androidx.compose.material3.TextButton(onClick = onPreview) { Text("Preview") }
        }
    }
}
