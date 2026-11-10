package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.audio.NowPlaying
import io.github.catchow0.d2n.ui.theme.D2nColors

/** What plays, above the bottom bar: pause, resume or stop it. */
@Composable
fun MiniPlayer(now: NowPlaying, onToggle: () -> Unit, onStop: () -> Unit) {
    Column(Modifier.fillMaxWidth().background(D2nColors.GlassStrong)) {
        LinearProgressIndicator(
            progress = { now.progress },
            modifier = Modifier.fillMaxWidth().height(2.dp),
            color = D2nColors.Cyan,
            trackColor = D2nColors.Line,
            drawStopIndicator = {},
        )
        Row(
            Modifier.fillMaxWidth().padding(start = 12.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Cover(now.cover, now.title, size = 40.dp)
            Column(Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite }) {
                Text(now.title, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    if (now.loading) "Loading the preview…" else now.artist,
                    style = MaterialTheme.typography.bodySmall,
                    color = D2nColors.Muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            IconAction(if (now.playing) R.drawable.ic_pause else R.drawable.ic_play, if (now.playing) "Pause" else "Play", onToggle, enabled = !now.loading)
            IconAction(R.drawable.ic_close, "Stop", onStop)
        }
    }
}
