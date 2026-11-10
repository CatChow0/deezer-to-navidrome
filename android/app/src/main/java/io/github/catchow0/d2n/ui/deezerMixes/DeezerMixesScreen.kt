package io.github.catchow0.d2n.ui.deezerMixes

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
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage

@Composable
fun DeezerMixesScreen(viewModel: DeezerMixesViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (state.loading) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator() }
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Text("Deezer mixes", style = MaterialTheme.typography.titleSmall)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f, fill = false)) {
            item { state.mixes.groupBy { it.group }.forEach { (group, mixes) ->
                Text(group, style = MaterialTheme.typography.titleSmall)
                mixes.forEach { mix ->
                    Card(Modifier.fillMaxWidth().padding(bottom = 4.dp)) {
                        Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Column(Modifier.weight(1f)) {
                                Text(mix.title)
                                if (mix.subtitle.isNotBlank()) Text(mix.subtitle, style = MaterialTheme.typography.bodySmall)
                            }
                            if (mix.followed) Text("Following") else Button(onClick = { viewModel.follow(mix) }) { Text("Follow") }
                        }
                    }
                }
            } }
        }
    }
}