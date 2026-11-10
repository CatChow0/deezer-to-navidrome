package io.github.catchow0.d2n.ui.activity

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.data.TaskSummary
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import io.github.catchow0.d2n.ui.components.Skeleton
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** A task's state, as the web's Activity chips say it. */
fun stateOf(task: TaskSummary): Pair<String, ChipTone> = when {
    task.cancelled -> "Cancelled" to ChipTone.Idle
    task.done && task.error -> "Failed" to ChipTone.Miss
    task.done -> "Done" to ChipTone.Ok
    task.cancelRequested -> "Stopping" to ChipTone.Partial
    else -> "Running" to ChipTone.Info
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActivityScreen(vm: ActivityViewModel, onBack: (() -> Unit)? = null, onOpen: (String) -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    // The list follows the server while it is on screen, not in the background.
    LifecycleStartEffect(vm) {
        vm.start()
        onStopOrDispose { vm.stop() }
    }
    PullToRefreshBox(isRefreshing = state.refreshing, onRefresh = { vm.refresh(pulled = true) }, modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (onBack != null) IconAction(R.drawable.ic_back, "Back", onBack)
                    Text("Activity", Modifier.semantics { heading() }, style = MaterialTheme.typography.headlineSmall)
                }
            }
            state.error?.let { error -> item { Banner(error, BannerTone.Error) } }
            when {
                state.loading -> items(4) { Skeleton(Modifier.fillMaxWidth().height(88.dp)) }
                state.tasks.isEmpty() -> item {
                    GlassCard(Modifier.fillMaxWidth()) {
                        Text("Nothing running. Scans, downloads and rebuilds show up here.", color = D2nColors.Muted)
                    }
                }
                else -> items(state.tasks, key = { it.id }) { task -> TaskCard(task) { onOpen(task.id) } }
            }
        }
    }
}

@Composable
private fun TaskCard(task: TaskSummary, onClick: () -> Unit) {
    val (label, tone) = stateOf(task)
    GlassCard(Modifier.fillMaxWidth().clip(D2nShapes.Tile).clickable(onClick = onClick), shape = D2nShapes.Tile) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                task.title.ifBlank { task.kind ?: "Task" }, Modifier.weight(1f),
                style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis,
            )
            Chip(label, tone = tone)
        }
        (task.message ?: task.stage)?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        val progress = task.progress
        if (!task.done && progress != null) {
            LinearProgressIndicator(
                progress = { (progress / 100).toFloat().coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth(),
                color = D2nColors.Violet,
                trackColor = D2nColors.GlassHover,
            )
        }
    }
}
