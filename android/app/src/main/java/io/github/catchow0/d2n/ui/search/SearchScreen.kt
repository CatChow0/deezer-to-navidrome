package io.github.catchow0.d2n.ui.search

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.audio.PreviewPlayer
import io.github.catchow0.d2n.data.Owned
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.ui.components.ActionSheet
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.ExplicitMark
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.PlayButton
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SearchField
import io.github.catchow0.d2n.ui.components.SegmentedTabs
import io.github.catchow0.d2n.ui.components.SheetAction
import io.github.catchow0.d2n.ui.components.formatDuration
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** Opens a Deezer page in the Deezer app or the browser. */
@Composable
fun rememberOpenLink(): (String) -> Unit {
    val context = LocalContext.current
    return remember(context) {
        { link -> runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, link.toUri())) } }
    }
}

/** A track found on Deezer: preview, download, open. */
@Composable
fun DeezerTrackSheet(title: String, artist: String, trackId: String, online: Boolean, onPlay: () -> Unit, onDownload: () -> Unit, onDismiss: () -> Unit) {
    val open = rememberOpenLink()
    ActionSheet(
        title = title,
        subtitle = artist,
        actions = listOf(
            SheetAction("Play the preview", R.drawable.ic_play, onClick = onPlay),
            SheetAction("Download", R.drawable.ic_download, enabled = online, onClick = onDownload),
            SheetAction("Open in Deezer", R.drawable.ic_open) { open("https://www.deezer.com/track/$trackId") },
        ),
        onDismiss = onDismiss,
    )
}

@Composable
fun SearchScreen(
    vm: SearchViewModel,
    player: PreviewPlayer,
    onBack: () -> Unit,
    onAlbum: (id: String, title: String) -> Unit,
    onArtist: (id: String, name: String) -> Unit,
) {
    val kind by vm.kind.collectAsStateWithLifecycle()
    val results by vm.results.collectAsStateWithLifecycle()
    val now by player.now.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var query by rememberSaveable { mutableStateOf("") }
    var track by remember { mutableStateOf<SearchResult?>(null) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { if (results == null) runCatching { focus.requestFocus() } }

    ScreenScaffold(title = "Search", onBack = onBack) {
        item(key = "field") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SearchField(
                    query,
                    { query = it },
                    "Track, album or artist",
                    Modifier.focusRequester(focus),
                    onSearch = { vm.search(query) },
                    onClear = vm::clear,
                )
                SegmentedTabs(SearchKind.entries.map { it to it.label }, kind, { vm.setKind(it) })
            }
        }
        val shown = results
        if (shown == null) {
            item(key = "hint") { EmptyState("Tracks you already own are marked, so you only download what is missing.") }
        } else {
            remote(shown, onRetry = { vm.search(query) }, skeletons = 6, skeletonHeight = 64.dp) { found ->
                if (found.items.isEmpty()) item(key = "none") { EmptyState("Nothing on Deezer for “${found.query}”.") }
                items(found.items, key = { "${found.kind}-${it.id}" }) { result ->
                    val owned = ownedLabel(found.kind, found.owned[result.id], if (found.kind == SearchKind.Artist) result.nbAlbum else result.trackCount)
                    when (found.kind) {
                        SearchKind.Track -> ListRow(
                            title = result.title,
                            subtitle = listOf(result.artist, result.album, formatDuration(result.duration)).filter(String::isNotBlank).joinToString(" · "),
                            leading = { Cover(result.cover, result.title) },
                            chips = if (owned != null || result.explicit) ({
                                if (result.explicit) ExplicitMark()
                                if (owned != null) Chip(owned, tone = ChipTone.Ok)
                            }) else null,
                            trailing = {
                                PlayButton(now?.id == result.id && now?.playing == true, "Play a preview of ${result.artist} - ${result.title}", {
                                    player.playDeezer(result.id, result.title, result.artist, result.cover)
                                })
                            },
                            onClick = { track = result },
                            clickLabel = "Actions",
                        )
                        SearchKind.Album -> ListRow(
                            title = result.title,
                            subtitle = listOfNotNull(result.artist.ifBlank { result.subtitle }, result.trackCount?.let { plural(it, "track") }).joinToString(" · "),
                            leading = { Cover(result.cover, result.title) },
                            chips = if (owned != null || result.explicit) ({
                                if (result.explicit) ExplicitMark()
                                if (owned != null) Chip(owned, tone = if (owned == "In library") ChipTone.Ok else ChipTone.Partial)
                            }) else null,
                            onClick = { onAlbum(result.id, result.title) },
                            clickLabel = "Open the album",
                        )
                        SearchKind.Artist -> ListRow(
                            title = result.title,
                            subtitle = result.subtitle,
                            leading = { Cover(result.cover, result.title, shape = androidx.compose.foundation.shape.CircleShape) },
                            chips = if (owned != null) ({ Chip(owned, tone = ChipTone.Partial) }) else null,
                            onClick = { onArtist(result.id, result.title) },
                            clickLabel = "Open the artist",
                        )
                    }
                }
            }
        }
    }

    track?.let { picked ->
        DeezerTrackSheet(
            title = picked.title,
            artist = picked.artist,
            trackId = picked.id,
            online = online,
            onPlay = { player.playDeezer(picked.id, picked.title, picked.artist, picked.cover) },
            onDownload = { vm.download("track", picked.id, "${picked.artist} - ${picked.title}") },
            onDismiss = { track = null },
        )
    }
}

@Composable
fun AlbumScreen(vm: AlbumViewModel, player: PreviewPlayer, title: String, onBack: () -> Unit) {
    val page by vm.page.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val now by player.now.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    val open = rememberOpenLink()
    var picked by remember { mutableStateOf<io.github.catchow0.d2n.data.AlbumTrack?>(null) }
    ScreenScaffold(title = page.value?.album?.title ?: title, onBack = onBack, refreshing = page.refreshing, onRefresh = vm::refresh) {
        remote(page, onRetry = vm::refresh, skeletons = 6, skeletonHeight = 60.dp) { shown ->
            val album = shown.album
            item(key = "head") {
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Cover(album.cover, album.title, size = 112.dp, shape = D2nShapes.Tile)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(album.artist, style = MaterialTheme.typography.bodyMedium, color = D2nColors.TextSoft)
                            Text(plural(album.trackCount, "track") + if (album.explicit) " · Explicit" else "", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
                            val owned = album.tracks.count { shown.owned[it.trackId]?.owned == true }
                            if (owned > 0) {
                                Chip(
                                    if (owned >= album.tracks.size && owned > 0) "In library" else "$owned/${album.tracks.size} tracks owned",
                                    tone = if (owned >= album.tracks.size && owned > 0) ChipTone.Ok else ChipTone.Partial,
                                )
                            }
                        }
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        D2nButton(
                            "Download album",
                            { vm.download("album", album.id, "${album.artist} - ${album.title}") },
                            small = true,
                            icon = R.drawable.ic_download,
                            enabled = online && "download-album-${album.id}" !in busy,
                        )
                        D2nButton("Open in Deezer", { open("https://www.deezer.com/album/${album.id}") }, kind = ButtonKind.Ghost, small = true, icon = R.drawable.ic_open)
                    }
                }
            }
            itemsIndexed(album.tracks, key = { _, t -> "t-${t.trackId}" }) { index, track ->
                ListRow(
                    title = track.title,
                    subtitle = listOf(track.artist, formatDuration(track.duration)).filter(String::isNotBlank).joinToString(" · "),
                    leading = { Text("${track.position.takeIf { it > 0 } ?: (index + 1)}", Modifier.width(28.dp), style = MaterialTheme.typography.labelMedium, color = D2nColors.Faint) },
                    chips = if (shown.owned[track.trackId]?.owned == true || track.explicit) ({
                        if (track.explicit) ExplicitMark()
                        if (shown.owned[track.trackId]?.owned == true) Chip("In library", tone = ChipTone.Ok)
                    }) else null,
                    trailing = {
                        PlayButton(now?.id == track.trackId && now?.playing == true, "Play a preview of ${track.title}", {
                            player.playDeezer(track.trackId, track.title, track.artist.ifBlank { album.artist }, album.cover)
                        })
                    },
                    onClick = { picked = track },
                    clickLabel = "Actions",
                )
            }
        }
    }
    picked?.let { track ->
        val artist = track.artist.ifBlank { page.value?.album?.artist.orEmpty() }
        DeezerTrackSheet(
            title = track.title,
            artist = artist,
            trackId = track.trackId,
            online = online,
            onPlay = { player.playDeezer(track.trackId, track.title, artist, page.value?.album?.cover) },
            onDownload = { vm.download("track", track.trackId, "$artist - ${track.title}") },
            onDismiss = { picked = null },
        )
    }
}

@Composable
fun ArtistScreen(vm: ArtistViewModel, name: String, onBack: () -> Unit, onAlbum: (id: String, title: String) -> Unit) {
    val page by vm.page.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    val open = rememberOpenLink()
    ScreenScaffold(title = page.value?.artist?.name ?: name, onBack = onBack, refreshing = page.refreshing, onRefresh = vm::refresh) {
        remote(page, onRetry = vm::refresh, skeletons = 6, skeletonHeight = 64.dp) { shown ->
            val artist = shown.artist
            item(key = "head") {
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Cover(artist.picture, artist.name, size = 96.dp, shape = androidx.compose.foundation.shape.CircleShape)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(plural(artist.nbAlbum, "album"), style = MaterialTheme.typography.bodyMedium, color = D2nColors.TextSoft)
                            ownedLabel(SearchKind.Artist, shown.summary, artist.nbAlbum)?.let { Chip(it, tone = ChipTone.Partial) }
                        }
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        D2nButton(
                            "Download discography",
                            { vm.download("artist", artist.id, "${artist.name} (discography)") },
                            small = true,
                            icon = R.drawable.ic_download,
                            enabled = online && "download-artist-${artist.id}" !in busy,
                        )
                        D2nButton("Open in Deezer", { open("https://www.deezer.com/artist/${artist.id}") }, kind = ButtonKind.Ghost, small = true, icon = R.drawable.ic_open)
                    }
                }
            }
            item(key = "releases") { io.github.catchow0.d2n.ui.components.SectionHeader("Releases") }
            if (artist.albums.isEmpty()) item(key = "none") { EmptyState("Deezer lists no release for this artist.") }
            items(artist.albums, key = { "a-${it.id}" }) { album ->
                val owned: Owned? = shown.owned[album.id]
                val label = ownedLabel(SearchKind.Album, owned, null)
                ListRow(
                    title = album.title,
                    subtitle = listOf(album.recordType.replaceFirstChar { it.uppercase() }, album.releaseDate.take(4)).filter(String::isNotBlank).joinToString(" · "),
                    leading = { Cover(album.cover, album.title) },
                    chips = if (label != null || album.explicit) ({
                        if (album.explicit) ExplicitMark()
                        if (label != null) Chip(label, tone = if (label == "In library") ChipTone.Ok else ChipTone.Partial)
                    }) else null,
                    onClick = { onAlbum(album.id, album.title) },
                    clickLabel = "Open the album",
                )
            }
        }
    }
}
