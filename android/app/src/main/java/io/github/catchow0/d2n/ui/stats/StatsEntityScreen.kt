package io.github.catchow0.d2n.ui.stats

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.audio.PreviewPlayer
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.PlayButton
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.StatTile
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes
import java.text.DateFormat
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Date
import java.util.Locale

private val KIND_LABEL = mapOf("artist" to "Artist", "album" to "Album", "track" to "Track")
private val MONTH = DateTimeFormatter.ofPattern("MMM yyyy", Locale.ENGLISH)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun StatsEntityScreen(vm: StatsEntityViewModel, player: PreviewPlayer, onBack: () -> Unit) {
    val entity by vm.entity.collectAsStateWithLifecycle()
    val now by player.now.collectAsStateWithLifecycle()
    val dateFormat = DateFormat.getDateInstance(DateFormat.MEDIUM)
    ScreenScaffold(title = entity.value?.name ?: "Details", onBack = onBack, refreshing = entity.refreshing, onRefresh = vm::refresh) {
        remote(entity, onRetry = vm::refresh, skeletons = 4, skeletonHeight = 96.dp) { data ->
            item(key = "head") {
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Cover(data.image, data.name, size = 96.dp, shape = if (data.kind == "artist") CircleShape else D2nShapes.Tile)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(KIND_LABEL[data.kind].orEmpty(), style = MaterialTheme.typography.labelMedium, color = D2nColors.Muted)
                            Text(data.name, style = MaterialTheme.typography.titleLarge)
                            data.artist?.takeIf { it.isNotBlank() }?.let { Text(it, color = D2nColors.TextSoft) }
                        }
                        val deezer = data.deezerTrackId.takeIf { data.kind == "track" && it.isNotBlank() }
                        if (deezer != null) PlayButton(now?.id == deezer && now?.playing == true, "Play a preview of ${data.name}", { player.playDeezer(deezer, data.name, data.artist.orEmpty(), null) })
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        StatTile(count(data.plays), "Plays")
                        StatTile(listening(data.seconds), "Estimated listening")
                        StatTile(data.firstPlay?.let { dateFormat.format(Date((it * 1000).toLong())) } ?: "-", "First listen")
                        StatTile(data.lastPlay?.let { dateFormat.format(Date((it * 1000).toLong())) } ?: "-", "Last listen")
                    }
                }
            }
            if (data.byMonth.isNotEmpty()) {
                item(key = "months-head") { SectionHeader("Plays by month") }
                item(key = "months") {
                    val max = data.byMonth.maxOf { it.plays }.coerceAtLeast(1)
                    GlassCard(Modifier.fillMaxWidth()) {
                        data.byMonth.forEach { month ->
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(
                                    runCatching { YearMonth.parse(month.key).format(MONTH) }.getOrDefault(month.key),
                                    Modifier.width(76.dp),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = D2nColors.Muted,
                                )
                                Box(Modifier.weight(1f).height(8.dp)) {
                                    Box(
                                        Modifier.fillMaxWidth((month.plays.toFloat() / max).coerceIn(0.02f, 1f)).height(8.dp).clip(D2nShapes.Chip)
                                            .background(Brush.horizontalGradient(listOf(D2nColors.Violet, D2nColors.Cyan))),
                                    )
                                }
                                Text(count(month.plays), Modifier.width(40.dp), style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                }
            }
            if (data.topTracks.isNotEmpty()) {
                item(key = "tracks-head") { SectionHeader("Top tracks") }
                itemsIndexed(data.topTracks) { index, track ->
                    ListRow(
                        title = track.title,
                        subtitle = if (data.kind == "artist") plural(track.plays, "play") else "${track.artist} · ${plural(track.plays, "play")}",
                        leading = { Text("${index + 1}", Modifier.width(24.dp), style = MaterialTheme.typography.labelMedium, color = D2nColors.Faint) },
                    )
                }
            }
        }
    }
}
