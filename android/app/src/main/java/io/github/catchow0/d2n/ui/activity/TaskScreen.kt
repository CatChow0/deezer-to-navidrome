package io.github.catchow0.d2n.ui.activity

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.data.TaskSummary
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.theme.D2nColors

/** One task live: where it is, its events newest first, and Cancel. */
@Composable
fun TaskScreen(vm: TaskViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    // The stream stops in the background, and resumes after the last event seen.
    LifecycleStartEffect(vm) {
        vm.resume()
        onStopOrDispose { vm.pause() }
    }
    val summary = state.summary
    val last = state.events.lastOrNull()
    val ended = state.ended
    val shown = (summary ?: TaskSummary(id = "", title = "Task")).let {
        if (ended != null) it.copy(done = true, error = ended.error, cancelled = it.cancelled || last?.cancelled == true) else it
    }
    val (label, tone) = stateOf(shown)
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { D2nButton("← Activity", onBack, kind = ButtonKind.Link) }
        item {
            GlassCard(Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(shown.title.ifBlank { "Task" }, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                    Chip(label, tone = tone)
                }
                val progress = last?.progress ?: summary?.progress
                if (ended == null && progress != null) {
                    LinearProgressIndicator(
                        progress = { (progress / 100).toFloat().coerceIn(0f, 1f) },
                        modifier = Modifier.fillMaxWidth(),
                        color = D2nColors.Violet,
                        trackColor = D2nColors.GlassHover,
                    )
                }
                (last?.message ?: summary?.message)?.let { Text(it, color = D2nColors.TextSoft) }
                if (summary?.cancellable == true && ended == null) {
                    D2nButton("Cancel", vm::cancel, kind = ButtonKind.Danger, enabled = LocalOnline.current)
                }
            }
        }
        state.notice?.let { notice -> item { Banner(notice, BannerTone.Warn) } }
        ended?.let { end ->
            item {
                Banner(
                    if (end.error) "It failed: ${end.message ?: "no reason given"}" else end.message ?: "Done",
                    if (end.error) BannerTone.Error else BannerTone.Info,
                )
            }
        }
        if (state.events.isNotEmpty()) item { Text("Events", style = MaterialTheme.typography.titleSmall) }
        items(state.events.asReversed(), key = { it.index }) { event ->
            Column {
                Text(event.message ?: event.stage ?: event.type, style = MaterialTheme.typography.bodyMedium)
                event.stage?.takeIf { event.message != null }?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = D2nColors.Faint)
                }
            }
        }
    }
}
