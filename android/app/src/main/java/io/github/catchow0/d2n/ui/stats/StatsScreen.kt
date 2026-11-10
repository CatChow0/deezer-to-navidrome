package io.github.catchow0.d2n.ui.stats

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun StatsScreen(viewModel: StatsViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.loadPlays() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.loading) CircularProgressIndicator()
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("week", "month", "year", "all").forEach { p ->
                if (p == state.period) Button(onClick = { viewModel.setPeriod(p) }) { Text(p.replaceFirstChar { it.uppercase() }) }
                else OutlinedButton(onClick = { viewModel.setPeriod(p) }) { Text(p.replaceFirstChar { it.uppercase() }) }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = viewModel::prev, enabled = state.period != "all") { Text("Prev") }
            Text(state.overview?.label ?: state.key)
            OutlinedButton(onClick = viewModel::next, enabled = state.period != "all") { Text("Next") }
        }
        state.overview?.totals?.let { t ->
            Text("Estimated listening: ${formatDuration(t.seconds)}", style = MaterialTheme.typography.bodyMedium)
            Text("Plays: ${t.plays}, artists: ${t.artists}, albums: ${t.albums}, tracks: ${t.tracks}")
        }
        Text("Top artists", style = MaterialTheme.typography.titleSmall)
        state.overview?.top?.artists?.forEach { row -> Text("${row.name ?: row.title} - ${row.plays}") }
        Text("Top albums", style = MaterialTheme.typography.titleSmall)
        state.overview?.top?.albums?.forEach { row -> Text("${row.title ?: row.name}${row.artist?.let { " - $it" } ?: ""} - ${row.plays}") }
        Text("Top tracks", style = MaterialTheme.typography.titleSmall)
        state.overview?.top?.tracks?.forEach { row -> Text("${row.title ?: row.name}${row.artist?.let { " - $it" } ?: ""} - ${row.plays}") }
        state.overview?.genres?.forEach { g -> Text("${g.name}: ${g.plays} (${(g.share * 100).toInt()}%)") }
        state.overview?.habits?.busiestDay?.let { Text("Busiest day: ${it.date}, ${it.plays} plays") }
        OutlinedTextField(value = state.query, onValueChange = viewModel::setQuery, label = { Text("Search plays") }, modifier = Modifier.fillMaxWidth())
        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.weight(1f, fill = false)) {
            items(state.plays?.plays ?: emptyList(), key = { it.id ?: it.listenedAt.toInt() }) { p ->
                Text("${p.title} - ${p.artist} (${formatTime(p.listenedAt)})", maxLines = 1)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { viewModel.setPage(state.page - 1) }, enabled = state.page > 1) { Text("Newer") }
            Text("Page ${state.page} of ${state.plays?.pages ?: 1}")
            OutlinedButton(onClick = { viewModel.setPage(state.page + 1) }, enabled = state.page < (state.plays?.pages ?: 1)) { Text("Older") }
        }
    }
}

private fun formatDuration(seconds: Double): String {
    val m = (seconds / 60).toInt()
    val h = m / 60
    return if (h > 0) "$h h ${m % 60} min" else "$m min"
}

private fun formatTime(v: Double): String {
    val ms = (v * 1000).toLong()
    return java.text.SimpleDateFormat("dd MMM HH:mm", java.util.Locale.getDefault()).format(java.util.Date(ms))
}
