package io.github.catchow0.d2n.ui.content

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.text.HtmlCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun NotesScreen(viewModel: ContentViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) {
        viewModel.loadNotes()
        viewModel.markSeen()
    }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.loading) { CircularProgressIndicator() }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        state.notes?.let { n ->
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f, fill = false)) {
                items(n.notes, key = { it.version }) { note ->
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("${note.version} - ${note.title}", style = MaterialTheme.typography.titleSmall)
                            if (note.date.isNotBlank()) Text(note.date, style = MaterialTheme.typography.bodySmall)
                            val plain = remember(note.html) { HtmlCompat.fromHtml(note.html, HtmlCompat.FROM_HTML_MODE_COMPACT).toString() }
                            Text(plain)
                        }
                    }
                }
            }
        }
    }
}