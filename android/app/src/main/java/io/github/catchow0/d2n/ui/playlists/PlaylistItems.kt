package io.github.catchow0.d2n.ui.playlists

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import io.github.catchow0.d2n.data.NavidromePlaylistTile
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.ui.common.formatInterval
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.plural

/** Where a playlist comes from, in a word. */
fun PlaylistTile.origin(): String = when (kind) {
    "xp" -> if (source == "spotify") "Spotify" else "CSV import"
    "mix" -> "Deezer mix"
    "auto" -> "Made for you"
    else -> "Deezer"
}

/** A playlist of the profile: its cover, where it comes from, how far matching got. */
@Composable
fun PlaylistListRow(tile: PlaylistTile, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val renamed = tile.deezerTitle.takeIf { it.isNotBlank() && it != tile.title }
    ListRow(
        title = tile.title.ifBlank { tile.id },
        modifier = modifier,
        subtitle = listOfNotNull(tile.origin(), renamed?.let { "“$it” on Deezer" }, tile.subtitle.ifBlank { null }).joinToString(" · "),
        leading = { Cover(tile.cover, tile.title) },
        chips = {
            val counts = tile.tracks
            if (counts == null) {
                Chip("Not scanned yet")
            } else {
                counts.matched?.takeIf { it > 0 }?.let { Chip("$it in library", tone = ChipTone.Ok) }
                counts.unmatched?.takeIf { it > 0 }?.let { Chip("$it missing", tone = ChipTone.Miss) }
                counts.unchecked?.takeIf { it > 0 }?.let { Chip("$it not checked") }
            }
            if (tile.automation.scan) Chip("Auto scan ${formatInterval(tile.automation.intervalMinutes)}", tone = ChipTone.Info)
        },
        onClick = onClick,
        clickLabel = "Open",
    )
}

/** A playlist made by hand in Navidrome: read-only here. */
@Composable
fun NavidromeListRow(tile: NavidromePlaylistTile, onClick: () -> Unit, modifier: Modifier = Modifier) {
    ListRow(
        title = tile.name,
        modifier = modifier,
        subtitle = "Navidrome · ${plural(tile.songCount, "track")}",
        leading = { Cover(tile.cover, tile.name) },
        onClick = onClick,
        clickLabel = "Open",
    )
}
