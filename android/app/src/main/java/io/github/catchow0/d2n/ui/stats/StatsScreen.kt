package io.github.catchow0.d2n.ui.stats

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.audio.PreviewPlayer
import io.github.catchow0.d2n.data.RankRow
import io.github.catchow0.d2n.data.RecapEntry
import io.github.catchow0.d2n.data.StatsGenre
import io.github.catchow0.d2n.data.StatsHabits
import io.github.catchow0.d2n.data.StatsOverview
import io.github.catchow0.d2n.ui.common.RefreshOnReturn
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.PlayButton
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SearchField
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.SegmentedTabs
import io.github.catchow0.d2n.ui.components.Skeleton
import io.github.catchow0.d2n.ui.components.StatTile
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes
import java.text.DateFormat
import java.text.NumberFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Date

private val DAYS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
private val numbers: NumberFormat = NumberFormat.getIntegerInstance()

fun count(value: Number): String = numbers.format(value)

fun day(iso: String): String = runCatching { LocalDate.parse(iso).format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)) }.getOrDefault(iso)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun StatsScreen(
    vm: StatsViewModel,
    player: PreviewPlayer,
    onEntity: (kind: String, id: Long) -> Unit,
    onRecap: (kind: String, key: String) -> Unit,
    onSettings: () -> Unit,
) {
    val choice by vm.choice.collectAsStateWithLifecycle()
    val overview by vm.overview.collectAsStateWithLifecycle()
    val index by vm.index.collectAsStateWithLifecycle()
    val hero by vm.hero.collectAsStateWithLifecycle()
    // The field's text stays here: going through the ViewModel's flow, fast typing
    // would come back out of order.
    var query by rememberSaveable { mutableStateOf(vm.query.value) }
    val plays by vm.plays.collectAsStateWithLifecycle()
    val now by player.now.collectAsStateWithLifecycle()

    RefreshOnReturn(vm, vm::refresh)
    ScreenScaffold(title = "Stats", refreshing = overview.refreshing || index.refreshing, onRefresh = vm::refresh) {
        remote(index, onRetry = vm::refresh, skeletons = 1, skeletonHeight = 160.dp) { recaps ->
            if (recaps.months.isEmpty()) {
                item(key = "empty") {
                    EmptyState(
                        "No plays yet. Your listening history fills up as you play music in Navidrome, or import it in Settings → Listening stats.",
                        actionLabel = "Open Settings",
                        onAction = onSettings,
                    )
                }
                return@remote
            }
            item(key = "hero") {
                val recap = hero
                GlassCard(Modifier.fillMaxWidth()) {
                    if (recap == null) {
                        val first = recaps.months.first()
                        Text(first.label, style = MaterialTheme.typography.headlineSmall)
                        Text("Your first month is still going: ${plural(first.plays, "play")} so far.", color = D2nColors.TextSoft)
                        D2nButton("Play your recap so far", { onRecap("month", first.key) }, icon = R.drawable.ic_play)
                    } else {
                        val top = recap.top.artists.firstOrNull()
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            recap.top.albums.take(3).forEach { Cover(it.image, it.label, size = 64.dp, shape = D2nShapes.Tile) }
                        }
                        Text(recap.label, style = MaterialTheme.typography.headlineSmall)
                        Text(
                            "${plural(recap.totals.plays, "play")} and about ${listening(recap.totals.seconds)} of music" +
                                (top?.let { ", with ${it.label} on top" } ?: "") + ".",
                            color = D2nColors.TextSoft,
                        )
                        D2nButton("Play your recap", { onRecap("month", recap.key) }, icon = R.drawable.ic_play)
                    }
                }
            }
            val shelf = recaps.months.filter { it.key != hero?.key }.map { it to "month" } + recaps.years.map { it to "year" }
            if (shelf.isNotEmpty()) {
                item(key = "shelf") {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(shelf, key = { "${it.second}-${it.first.key}" }) { (entry, kind) -> ShelfCard(entry, kind) { onRecap(kind, entry.key) } }
                    }
                }
            }
            item(key = "period") {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    SegmentedTabs(Period.entries.map { it to it.label }, choice.period, vm::setPeriod)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconAction(R.drawable.ic_back, "Previous ${choice.period.label.lowercase()}", { vm.step(-1) }, enabled = vm.canStep(-1))
                        Text(
                            overview.value?.takeIf { it.period == choice.period.api && it.key == choice.key }?.label ?: "…",
                            Modifier.weight(1f),
                            style = MaterialTheme.typography.titleMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        // The back arrow, turned to point forward.
                        Box(Modifier.graphicsLayer(scaleX = -1f)) {
                            IconAction(R.drawable.ic_back, "Next ${choice.period.label.lowercase()}", { vm.step(1) }, enabled = vm.canStep(1))
                        }
                    }
                }
            }
            val shown = overview.value
            when {
                shown == null && overview.loading -> item(key = "overview-loading") { Skeleton(Modifier.fillMaxWidth().height(220.dp)) }
                shown == null -> item(key = "overview-error") {
                    Banner(overview.error ?: "These stats could not be loaded.", BannerTone.Error, actionLabel = "Retry", onAction = vm::refresh)
                }
                else -> overviewItems(shown, now?.id, player, onEntity)
            }
            item(key = "plays-head") { SectionHeader("Recent plays") }
            item(key = "plays-search") {
            SearchField(query, { text ->
                query = text
                vm.search(text)
            }, "Search title, artist or album")
        }
            val page = plays.value
            when {
                page == null && plays.loading -> items(4) { Skeleton(Modifier.fillMaxWidth().height(56.dp)) }
                page == null -> item(key = "plays-error") { Banner(plays.error ?: "Your plays could not be loaded.", BannerTone.Error, actionLabel = "Retry", onAction = { vm.page(1) }) }
                page.plays.isEmpty() -> item(key = "plays-none") { EmptyState(if (query.isNotBlank()) "No plays match this search." else "No plays yet.") }
                else -> {
                    items(page.plays, key = { "play-${it.id}" }) { play ->
                        ListRow(
                            title = play.title,
                            subtitle = listOf(play.artist, play.album.orEmpty()).filter(String::isNotBlank).joinToString(" · "),
                            chips = {
                                Text(
                                    DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date((play.listenedAt * 1000).toLong())),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = D2nColors.Faint,
                                )
                            },
                            onClick = { onEntity("track", play.trackId) },
                            clickLabel = "Open the track",
                        )
                    }
                    item(key = "pager") {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                "Page ${count(page.page)} of ${count(page.pages)}, ${plural(page.total, "play")}",
                                Modifier.weight(1f),
                                style = MaterialTheme.typography.bodySmall,
                                color = D2nColors.Muted,
                            )
                            D2nButton("Newer", { vm.page(page.page - 1) }, kind = ButtonKind.Ghost, small = true, enabled = page.page > 1)
                            D2nButton("Older", { vm.page(page.page + 1) }, kind = ButtonKind.Ghost, small = true, enabled = page.page < page.pages)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ShelfCard(entry: RecapEntry, kind: String, onOpen: () -> Unit) {
    val tags = listOfNotNull("so far".takeIf { entry.soFar }, "partial".takeIf { entry.partial })
    Column(
        Modifier
            .width(if (kind == "year") 150.dp else 130.dp)
            .heightIn(min = 72.dp)
            .clip(D2nShapes.Tile)
            .background(if (kind == "year") D2nColors.Violet.copy(alpha = 0.3f) else D2nColors.GlassRaised)
            .border(1.dp, D2nColors.Line, D2nShapes.Tile)
            .clickable(role = Role.Button, onClickLabel = "Play the recap", onClick = onOpen)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(entry.label, style = MaterialTheme.typography.titleSmall, maxLines = 2)
        Text(if (tags.isEmpty()) plural(entry.plays, "play") else tags.joinToString(", "), style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
    }
}

@OptIn(ExperimentalLayoutApi::class)
private fun androidx.compose.foundation.lazy.LazyListScope.overviewItems(
    data: StatsOverview,
    playing: String?,
    player: PreviewPlayer,
    onEntity: (String, Long) -> Unit,
) {
    item(key = "totals") {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                StatTile(listening(data.totals.seconds), "Estimated listening")
                StatTile(count(data.totals.plays), "Plays")
                StatTile(count(data.totals.artists), "Artists")
                StatTile(count(data.totals.albums), "Albums")
                StatTile(count(data.totals.tracks), "Tracks")
            }
            if (data.coverage.lengthPct < 100) {
                Text(
                    "Track lengths are known for ${data.coverage.lengthPct}% of these plays, so the real time is higher.",
                    style = MaterialTheme.typography.bodySmall,
                    color = D2nColors.Muted,
                )
            }
        }
    }
    listOf(Triple("Top artists", "artist", data.top.artists), Triple("Top albums", "album", data.top.albums), Triple("Top tracks", "track", data.top.tracks))
        .forEach { (title, kind, rows) ->
            item(key = "head-$kind") { SectionHeader(title) }
            if (rows.isEmpty()) item(key = "none-$kind") { EmptyState("No plays in this period.") }
            val max = rows.firstOrNull()?.plays?.coerceAtLeast(1) ?: 1
            items(rows, key = { "$kind-${it.id}" }) { row ->
                val rank = rows.indexOf(row) + 1
                RankLine(rank, kind, row, max, playing, player) { onEntity(kind, row.id) }
            }
        }
    item(key = "genres-head") {
        SectionHeader(
            "Genres",
            subtitle = if (data.totals.plays > 0 && data.coverage.genrePct < 100) "Known for ${data.coverage.genrePct}% of plays, and filling in as Deezer is checked." else null,
        )
    }
    item(key = "genres") { Genres(data.genres) }
    item(key = "habits-head") { SectionHeader("When you listen") }
    item(key = "habits") { Habits(data.habits) }
}

@Composable
private fun RankLine(rank: Int, kind: String, row: RankRow, max: Int, playing: String?, player: PreviewPlayer, onOpen: () -> Unit) {
    ListRow(
        title = row.label,
        subtitle = row.artist,
        leading = {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("$rank", Modifier.width(22.dp), style = MaterialTheme.typography.labelMedium, color = D2nColors.Faint)
                Cover(row.image, row.label, size = 44.dp, shape = if (kind == "artist") androidx.compose.foundation.shape.CircleShape else D2nShapes.Control)
            }
        },
        chips = {
            Box(Modifier.fillMaxWidth().height(14.dp), contentAlignment = Alignment.CenterStart) {
                Box(
                    Modifier.fillMaxWidth((row.plays.toFloat() / max).coerceIn(0.02f, 1f)).height(4.dp).clip(D2nShapes.Chip)
                        .background(androidx.compose.ui.graphics.Brush.horizontalGradient(listOf(D2nColors.Violet, D2nColors.Cyan))),
                )
            }
        },
        trailing = {
            Text(count(row.plays), style = MaterialTheme.typography.labelLarge, color = D2nColors.TextSoft, modifier = Modifier.padding(end = 6.dp))
            val deezer = row.deezerTrackId?.takeIf { it.isNotBlank() }
            if (deezer != null) PlayButton(playing == deezer, "Play a preview of ${row.label}", { player.playDeezer(deezer, row.label, row.artist.orEmpty(), null) })
        },
        onClick = onOpen,
        clickLabel = "Details",
    )
}

@Composable
private fun Genres(genres: List<StatsGenre>) {
    GlassCard(Modifier.fillMaxWidth()) {
        if (genres.isEmpty()) {
            Text("No genres known for this period yet.", color = D2nColors.Muted)
            return@GlassCard
        }
        val max = genres.first().plays.coerceAtLeast(1)
        genres.take(8).forEach { genre ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row {
                    Text(genre.name, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    Text("${(genre.share * 100).toInt()}%, ${listening(genre.seconds)}", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
                }
                Box(
                    Modifier.fillMaxWidth((genre.plays.toFloat() / max).coerceIn(0.02f, 1f)).height(6.dp).clip(D2nShapes.Chip)
                        .background(androidx.compose.ui.graphics.Brush.horizontalGradient(listOf(D2nColors.Magenta, D2nColors.Violet))),
                )
            }
        }
    }
}

/** Plays by weekday and hour, as the web's heatmap. */
@Composable
private fun Habits(habits: StatsHabits) {
    val max = habits.heatmap.flatten().maxOrNull() ?: 0
    GlassCard(Modifier.fillMaxWidth()) {
        if (max == 0) {
            Text("No plays in this period.", color = D2nColors.Muted)
            return@GlassCard
        }
        var peakDay = 0
        var peakHour = 0
        habits.heatmap.forEachIndexed { d, hours -> hours.forEachIndexed { h, plays -> if (plays > habits.heatmap[peakDay][peakHour]) { peakDay = d; peakHour = h } } }
        val description = "Plays by weekday and hour. Most plays: ${DAYS[peakDay]} at %02d:00, ${plural(habits.heatmap[peakDay][peakHour], "play")}.".format(peakHour)
        Row(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(end = 6.dp), verticalArrangement = Arrangement.spacedBy(0.dp)) {
                DAYS.forEach { Text(it, Modifier.height(18.dp), style = MaterialTheme.typography.labelSmall, color = D2nColors.Muted) }
            }
            Canvas(Modifier.weight(1f).height((18 * 7).dp).semantics { contentDescription = description }) {
                val cell = size.width / 24f
                val row = size.height / 7f
                habits.heatmap.forEachIndexed { d, hours ->
                    hours.forEachIndexed { h, plays ->
                        val level = if (plays == 0) 0f else 0.15f + plays.toFloat() / max * 0.85f
                        drawRoundRect(
                            color = if (plays == 0) D2nColors.GlassHover else D2nColors.Cyan.copy(alpha = level),
                            topLeft = Offset(h * cell + 1f, d * row + 1f),
                            size = Size(cell - 2f, row - 2f),
                            cornerRadius = CornerRadius(3f, 3f),
                        )
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(start = 30.dp)) {
            listOf("00h", "06h", "12h", "18h").forEach { Text(it, Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = D2nColors.Faint) }
        }
        val parts = mutableListOf("Busiest day: ${day(habits.busiestDay.date)}, ${plural(habits.busiestDay.plays, "play")}.")
        if (habits.longestStreak.days > 1) parts += "Longest streak: ${count(habits.longestStreak.days)} days in a row."
        Text(parts.joinToString(" "), style = MaterialTheme.typography.bodySmall, color = D2nColors.TextSoft)
    }
}
