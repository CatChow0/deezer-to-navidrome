package io.github.catchow0.d2n.ui.playlists

import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.audio.PreviewPlayer
import io.github.catchow0.d2n.data.LibraryFile
import io.github.catchow0.d2n.data.NavidromeStatus
import io.github.catchow0.d2n.data.PlaylistAutomation
import io.github.catchow0.d2n.data.PlaylistPreview
import io.github.catchow0.d2n.data.PlaylistRow
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.data.PublishedIn
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.ui.common.RefreshOnReturn
import io.github.catchow0.d2n.ui.common.RefreshWhenTasksEnd
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ago
import io.github.catchow0.d2n.ui.components.ActionSheet
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.ChoiceField
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.ConfirmDialog
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.ExplicitMark
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.NumberField
import io.github.catchow0.d2n.ui.components.PlayButton
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SearchField
import io.github.catchow0.d2n.ui.components.SegmentedTabs
import io.github.catchow0.d2n.ui.components.SheetAction
import io.github.catchow0.d2n.ui.components.Skeleton
import io.github.catchow0.d2n.ui.components.ToggleRow
import io.github.catchow0.d2n.ui.components.formatDuration
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** The sheets this screen opens, one at a time. */
private sealed interface Sheet {
    data object Menu : Sheet
    data object Navidrome : Sheet
    data object Automation : Sheet
    data object Delete : Sheet
    data class Track(val row: PlaylistRow) : Sheet
    data class File(val row: PlaylistRow) : Sheet
    data class Deezer(val row: PlaylistRow) : Sheet
}

@Composable
fun PlaylistScreen(vm: PlaylistViewModel, player: PreviewPlayer, onBack: () -> Unit) {
    val tracks by vm.tracks.collectAsStateWithLifecycle()
    val tile by vm.tile.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val gone by vm.gone.collectAsStateWithLifecycle()
    val now by player.now.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var filter by rememberSaveable { mutableStateOf(TrackFilter.All) }
    var query by rememberSaveable { mutableStateOf("") }
    var sheet by remember { mutableStateOf<Sheet?>(null) }

    LaunchedEffect(gone) { if (gone) onBack() }
    // Back from a scan's task, or from another app: the rows may have changed.
    RefreshOnReturn(vm, vm::refresh)
    // A scan or a download that ends updates the rows, as on the web.
    RefreshWhenTasksEnd(vm, vm::refresh)

    val preview = tracks.value?.playlist
    val generated = tile?.kind == "auto"
    val imported = tile?.kind == "xp" || preview?.xp != null
    val title = tile?.title?.ifBlank { null } ?: preview?.playlistTitle?.ifBlank { null } ?: "Playlist"

    ScreenScaffold(
        title = title,
        onBack = onBack,
        actions = { IconAction(R.drawable.ic_more_vert, "More actions", { sheet = Sheet.Menu }) },
        refreshing = tracks.refreshing,
        onRefresh = vm::refresh,
    ) {
        item(key = "head") {
            Header(
                tile = tile,
                preview = preview,
                generated = generated,
                busy = busy,
                online = online,
                onScan = vm::scan,
                onDownloadMissing = vm::downloadMissing,
            )
        }
        remote(tracks, onRetry = vm::refresh, skeletons = 6, skeletonHeight = 60.dp) { answer ->
            val rows = answer.playlist.rows.sortedBy { it.number }
            if (!generated && rows.isNotEmpty()) {
                item(key = "filters") {
                    val filters = TrackFilter.entries.filter { it != TrackFilter.Review || imported }
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SegmentedTabs(filters.map { it to it.label }, filter, { filter = it })
                        if (rows.size > 12) SearchField(query, { query = it }, "Filter these tracks")
                    }
                }
            }
            val shown = rows.filter { it.shownBy(filter, query) }
            if (shown.isEmpty()) {
                item(key = "empty") { EmptyState(if (rows.isEmpty()) TrackFilter.All.empty else if (query.isNotBlank()) "No track matches." else filter.empty) }
            }
            items(shown, key = { "r-${it.number}" }) { row ->
                val trackId = row.deezerId()
                TrackLine(
                    row,
                    playing = trackId != null && now?.id == trackId && now?.playing == true,
                    onPlay = trackId?.let { { player.playDeezer(it, row.deezerTitle.ifBlank { row.deezerName }, row.deezerArtist) } },
                    onOpen = { sheet = Sheet.Track(row) },
                )
            }
        }
    }

    when (val open = sheet) {
        null -> Unit
        Sheet.Menu -> ActionSheet(
            title = title,
            actions = buildList {
                if (!generated) add(SheetAction("Automation", R.drawable.ic_tune, enabled = online) { sheet = Sheet.Automation })
                add(SheetAction("In Navidrome", R.drawable.ic_open) {
                    vm.loadAccounts()
                    sheet = Sheet.Navidrome
                })
                if (!generated) {
                    val shared = (tile?.accounts?.size ?: 0) > 1
                    add(SheetAction(if (shared) "Remove from this profile" else "Delete playlist", R.drawable.ic_delete, danger = true, enabled = online) { sheet = Sheet.Delete })
                }
            },
            onDismiss = { if (sheet == Sheet.Menu) sheet = null },
        )
        Sheet.Delete -> {
            val shared = (tile?.accounts?.size ?: 0) > 1
            ConfirmDialog(
                title = if (shared) "Remove from this profile?" else "Delete this playlist?",
                text = if (shared) "It stays for the other profiles it goes to." else "It is deleted from the app and from Navidrome. Its downloaded files stay.",
                confirmLabel = if (shared) "Remove" else "Delete",
                onConfirm = vm::delete,
                onDismiss = { sheet = null },
            )
        }
        Sheet.Navidrome -> NavidromeSheet(
            status = tracks.value?.navidrome,
            generated = generated,
            busy = "accounts" in busy || "publish" in busy,
            online = online,
            onAccounts = vm::setAccounts,
            onPublish = vm::publish,
            onDismiss = { sheet = null },
        )
        Sheet.Automation -> AutomationSheet(
            current = tile?.automation ?: PlaylistAutomation(),
            busy = "automation" in busy,
            onSave = {
                vm.setAutomation(it)
                sheet = null
            },
            onDismiss = { sheet = null },
        )
        is Sheet.Track -> TrackSheet(
            row = open.row,
            online = online,
            onPlay = open.row.deezerId()?.let { id -> { player.playDeezer(id, open.row.deezerTitle.ifBlank { open.row.deezerName }, open.row.deezerArtist) } },
            onDownload = { vm.downloadTrack(open.row) },
            onChooseFile = {
                vm.searchFiles(listOf(open.row.deezerArtist, open.row.deezerTitle).filter(String::isNotBlank).joinToString(" ").ifBlank { open.row.deezerName })
                sheet = Sheet.File(open.row)
            },
            onMissing = { vm.match(open.row, "missing") },
            onAuto = { vm.match(open.row, "auto") },
            onFindOnDeezer = {
                val source = open.row.xp
                vm.searchDeezer(listOfNotNull(source?.sourceArtist?.split(",")?.firstOrNull(), source?.sourceTitle).joinToString(" ").ifBlank { open.row.deezerName })
                sheet = Sheet.Deezer(open.row)
            },
            onNotOnDeezer = { vm.pickOnDeezer(open.row, null) },
            onDeezerAuto = { vm.pickOnDeezer(open.row, "auto") },
            onDismiss = { if (sheet == open) sheet = null },
        )
        is Sheet.File -> {
            val files by vm.files.collectAsStateWithLifecycle()
            SearchSheet(
                title = "A file for ${open.row.deezerName}",
                placeholder = "Search the library",
                initial = listOf(open.row.deezerArtist, open.row.deezerTitle).filter(String::isNotBlank).joinToString(" "),
                onSearch = vm::searchFiles,
                onDismiss = {
                    vm.closeSearches()
                    sheet = null
                },
            ) {
                searchResults(files, "No file in the library looks like this. Try other words.") { file: LibraryFile ->
                    ListRow(
                        title = if (file.artist.isNotBlank()) "${file.artist} - ${file.title}" else file.title,
                        subtitle = listOf(file.album, file.file).filter(String::isNotBlank).joinToString(", "),
                        trailing = {
                            D2nButton("Use", {
                                vm.match(open.row, "file", file.path)
                                vm.closeSearches()
                                sheet = null
                            }, kind = ButtonKind.Ghost, small = true, enabled = online)
                        },
                    )
                }
            }
        }
        is Sheet.Deezer -> {
            val picks by vm.picks.collectAsStateWithLifecycle()
            val source = open.row.xp
            SearchSheet(
                title = "Deezer track for ${source?.sourceArtist.orEmpty()} - ${source?.sourceTitle.orEmpty()}",
                placeholder = "Search Deezer",
                initial = listOfNotNull(source?.sourceArtist?.split(",")?.firstOrNull(), source?.sourceTitle).joinToString(" "),
                onSearch = vm::searchDeezer,
                onDismiss = {
                    vm.closeSearches()
                    sheet = null
                },
            ) {
                searchResults(picks, "Nothing on Deezer looks like this. Try other words.") { found: SearchResult ->
                    val current = found.id == open.row.trackId
                    ListRow(
                        title = found.title,
                        subtitle = listOf(found.artist, found.album, formatDuration(found.duration)).filter(String::isNotBlank).joinToString(", "),
                        chips = if (found.explicit) ({ ExplicitMark() }) else null,
                        leading = { Cover(found.cover, found.title, size = 44.dp) },
                        trailing = {
                            PlayButton(now?.id == found.id && now?.playing == true, "Play a preview of ${found.artist} - ${found.title}", {
                                player.playDeezer(found.id, found.title, found.artist, found.cover)
                            })
                            D2nButton(if (current) "In use" else "Use", {
                                vm.pickOnDeezer(open.row, found.id)
                                vm.closeSearches()
                                sheet = null
                            }, kind = ButtonKind.Ghost, small = true, enabled = online && !current)
                        },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Header(
    tile: PlaylistTile?,
    preview: PlaylistPreview?,
    generated: Boolean,
    busy: Set<String>,
    online: Boolean,
    onScan: (Boolean) -> Unit,
    onDownloadMissing: () -> Unit,
) {
    GlassCard(Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Cover(tile?.cover, tile?.title ?: preview?.playlistTitle.orEmpty(), size = 88.dp, shape = D2nShapes.Tile)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(kindLine(tile), style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
                tile?.deezerTitle?.takeIf { it.isNotBlank() && it != tile.title }?.let {
                    Text("Named here as in Navidrome; “$it” on Deezer.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (tile?.automation?.scan == true) {
                        Chip("Auto scan ${io.github.catchow0.d2n.ui.common.formatInterval(tile.automation.intervalMinutes)}", tone = ChipTone.Info)
                        if (tile.automation.download) Chip("Auto download", tone = ChipTone.Info)
                    }
                    if ((tile?.accounts?.size ?: 0) > 1) Chip("${tile!!.accounts.size} profiles")
                }
            }
        }
        if (preview == null) {
            Skeleton(Modifier.fillMaxWidth().height(10.dp))
        } else if (preview.rows.isNotEmpty()) {
            Breakdown(preview)
        }
        preview?.xp?.let { xp ->
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Chip("${xp.onDeezer} found on Deezer", tone = ChipTone.Ok)
                if (xp.review > 0) Chip("${xp.review} to review", tone = ChipTone.Partial)
                if (xp.notFound > 0) Chip("${xp.notFound} not on Deezer", tone = ChipTone.Miss)
                if (xp.pending > 0) Chip("${xp.pending} being found…")
            }
            if (xp.truncated) {
                Banner("${xp.sourceName} only shows the first 100 tracks of a public playlist. Import an Exportify CSV of it to get them all.", BannerTone.Info)
            }
        }
        if (!generated) {
            val missing = preview?.rows?.count { it.matched == false && it.deezerId() != null && !it.downloaded } ?: 0
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                D2nButton("Quick scan", { onScan(true) }, small = true, enabled = online && "scan" !in busy)
                D2nButton("Full scan", { onScan(false) }, kind = ButtonKind.Ghost, small = true, enabled = online && "scan" !in busy)
                D2nButton(
                    if (missing > 0) "Download $missing missing" else "Download missing",
                    onDownloadMissing,
                    kind = ButtonKind.Ghost,
                    small = true,
                    icon = R.drawable.ic_download,
                    enabled = online && missing > 0 && "download-missing" !in busy,
                )
            }
            Text(
                "Quick scan re-matches only what is missing or not checked; full scan re-matches every track.",
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Faint,
            )
        }
    }
}

private fun kindLine(tile: PlaylistTile?): String = when (tile?.kind) {
    null -> "Playlist"
    "auto" -> "Made for you. ${tile.subtitle}".trim()
    "mix" -> "Mix made for you by Deezer, refreshed at each scan"
    "xp" -> if (tile.source == "spotify") "Spotify playlist matched to Deezer, synced at each scan" else "CSV import matched to Deezer"
    else -> "Deezer playlist ${tile.id}"
}

/** In library, missing, not checked: a bar and its legend. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Breakdown(preview: PlaylistPreview) {
    val found = preview.matchedCount
    val missing = preview.unmatchedCount
    val unchecked = preview.uncheckedCount
    Row(
        Modifier.fillMaxWidth().height(8.dp).clip(D2nShapes.Chip)
            .semantics { contentDescription = "$found in library, $missing missing, $unchecked not checked" },
    ) {
        if (found > 0) Box(Modifier.weight(found.toFloat()).height(8.dp).background(D2nColors.Ok))
        if (missing > 0) Box(Modifier.weight(missing.toFloat()).height(8.dp).background(D2nColors.Miss))
        if (unchecked > 0) Box(Modifier.weight(unchecked.toFloat()).height(8.dp).background(D2nColors.IdleLine))
    }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Chip("$found in library", tone = ChipTone.Ok)
        Chip("$missing missing", tone = ChipTone.Miss)
        if (unchecked > 0) Chip("$unchecked not checked")
    }
}

/** A track: its number, its Deezer name, where it stands. */
@Composable
private fun TrackLine(row: PlaylistRow, playing: Boolean, onPlay: (() -> Unit)?, onOpen: () -> Unit) {
    ListRow(
        title = row.deezerName.ifBlank { "${row.deezerArtist} - ${row.deezerTitle}" },
        subtitle = if (row.matched == true && row.sourceName.isNotBlank()) row.sourceName else row.deezerAlbum,
        leading = {
            Text("${row.number}", Modifier.width(28.dp), style = MaterialTheme.typography.labelMedium, color = D2nColors.Faint)
        },
        chips = {
            when (row.matched) {
                true -> Chip("In library", tone = ChipTone.Ok)
                false -> Chip("Missing", tone = ChipTone.Miss)
                null -> Chip("Not checked")
            }
            if (row.manual) Chip("Set by hand", tone = ChipTone.Info)
            if (row.downloaded) Chip("Downloaded", tone = ChipTone.Ok)
            row.xp?.let { source ->
                when {
                    source.status == "pending" -> Chip("Finding on Deezer…")
                    !source.onDeezer -> Chip("Not on Deezer", tone = ChipTone.Miss)
                    source.status == "uncertain" -> Chip("Review", tone = ChipTone.Partial)
                    source.status == "manual" -> Chip("Picked by hand", tone = ChipTone.Info)
                }
            }
        },
        trailing = { if (onPlay != null) PlayButton(playing, "Play a preview of ${row.deezerName}", onPlay) },
        onClick = onOpen,
        clickLabel = "Actions",
    )
}

@Composable
private fun TrackSheet(
    row: PlaylistRow,
    online: Boolean,
    onPlay: (() -> Unit)?,
    onDownload: () -> Unit,
    onChooseFile: () -> Unit,
    onMissing: () -> Unit,
    onAuto: () -> Unit,
    onFindOnDeezer: () -> Unit,
    onNotOnDeezer: () -> Unit,
    onDeezerAuto: () -> Unit,
    onDismiss: () -> Unit,
) {
    val deezer = row.deezerId() != null
    ActionSheet(
        title = row.deezerName,
        subtitle = row.deezerAlbum.ifBlank { null },
        actions = buildList {
            if (onPlay != null) add(SheetAction("Play the preview", R.drawable.ic_play, onClick = onPlay))
            if (deezer && row.matched == false && !row.downloaded) add(SheetAction("Download", R.drawable.ic_download, enabled = online, onClick = onDownload))
            if (row.matched != null && row.trackId != null) {
                add(SheetAction("Choose a library file…", R.drawable.ic_file, enabled = online, onClick = onChooseFile))
                if (!(row.matched == false && row.manual)) add(SheetAction("Not in my library", R.drawable.ic_close, enabled = online, onClick = onMissing))
                if (row.manual) add(SheetAction("Back to automatic matching", R.drawable.ic_restore, enabled = online, onClick = onAuto))
            }
            row.xp?.let { source ->
                add(SheetAction("Find on Deezer…", R.drawable.ic_search, enabled = online, onClick = onFindOnDeezer))
                if (source.onDeezer || source.status != "manual") add(SheetAction("Not on Deezer", R.drawable.ic_close, enabled = online, onClick = onNotOnDeezer))
                if (source.status == "manual") add(SheetAction("Back to the automatic Deezer match", R.drawable.ic_restore, enabled = online, onClick = onDeezerAuto))
            }
        },
        onDismiss = onDismiss,
    )
}

/** A sheet with a search and its results: a library file, or a Deezer track. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SearchSheet(
    title: String,
    placeholder: String,
    initial: String,
    onSearch: (String) -> Unit,
    onDismiss: () -> Unit,
    results: androidx.compose.foundation.lazy.LazyListScope.() -> Unit,
) {
    var query by remember { mutableStateOf(initial) }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = D2nColors.Ink2,
        contentColor = D2nColors.Text,
    ) {
        Column(Modifier.fillMaxWidth().navigationBarsPadding().imePadding().padding(horizontal = 16.dp)) {
            Text(title, Modifier.padding(horizontal = 8.dp).semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            SearchField(query, { query = it }, placeholder, Modifier.padding(vertical = 12.dp), onSearch = { onSearch(query) })
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp), content = results)
        }
    }
}

private fun <T> androidx.compose.foundation.lazy.LazyListScope.searchResults(
    found: Remote<List<T>>?,
    empty: String,
    row: @Composable (T) -> Unit,
) {
    val remote = found ?: return
    val value = remote.value
    when {
        value == null && remote.loading -> items(4) { Skeleton(Modifier.fillMaxWidth().height(56.dp)) }
        value == null -> item { Banner(remote.error ?: "The search failed.", BannerTone.Error) }
        value.isEmpty() -> item { Text(empty, color = D2nColors.Muted, modifier = Modifier.padding(8.dp)) }
        else -> items(value) { row(it) }
    }
}

/** Where the playlist is in Navidrome, and the profiles it goes to. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NavidromeSheet(
    status: NavidromeStatus?,
    generated: Boolean,
    busy: Boolean,
    online: Boolean,
    onAccounts: (List<String>) -> Unit,
    onPublish: () -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = D2nColors.Ink2,
        contentColor = D2nColors.Text,
    ) {
        Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 24.dp).padding(bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("In Navidrome", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            Text(
                if (generated) "Where this playlist is in Navidrome." else "The Navidrome accounts this playlist goes to, each as its own private playlist.",
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Muted,
            )
            val accounts = status?.accounts.orEmpty()
            if (status == null) Skeleton(Modifier.fillMaxWidth().height(56.dp))
            accounts.forEach { account ->
                val members = accounts.filter { it.member }.map { it.id }
                Row(
                    Modifier
                        .fillMaxWidth()
                        .toggleable(
                            value = account.member,
                            enabled = !generated && online && !busy,
                            role = Role.Checkbox,
                            onValueChange = { on -> onAccounts(if (on) members + account.id else members - account.id) },
                        )
                        .padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Checkbox(
                        checked = account.member,
                        onCheckedChange = null,
                        enabled = !generated && online && !busy,
                        colors = CheckboxDefaults.colors(checkedColor = D2nColors.Violet, uncheckedColor = D2nColors.LineStrong),
                    )
                    Column(Modifier.weight(1f)) {
                        Text(account.label, style = MaterialTheme.typography.bodyLarge)
                        Text(publicationLine(account), style = MaterialTheme.typography.bodySmall, color = if (publicationWarns(account)) D2nColors.Partial else D2nColors.Muted)
                    }
                }
            }
            if (accounts.any { it.member && it.mode == "api" && it.complete }) {
                D2nButton(
                    if (busy) "Publishing…" else "Publish again now",
                    onPublish,
                    kind = ButtonKind.Ghost,
                    small = true,
                    enabled = online && !busy,
                )
                Text("Replaces the playlist in Navidrome with this one, even unchanged.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Faint)
            }
        }
    }
}

private fun publicationWarns(account: PublishedIn) =
    account.member && account.mode != "m3u8" && (!account.complete || account.publication?.error != null)

/** What the web's drawer says of one account. */
private fun publicationLine(account: PublishedIn): String {
    if (!account.member) return "Not in this account"
    if (account.mode == "m3u8") return "As a .m3u8 file Navidrome imports: it belongs to Navidrome's first admin"
    if (!account.complete) return "Add the address and password of this account in Settings"
    val publication = account.publication ?: return "Waiting: published after the next scan"
    publication.error?.let { return it }
    val parts = mutableListOf("${plural(publication.songCount, "track")} in Navidrome")
    publication.customTitle?.takeIf { it.isNotBlank() }?.let { parts.add(0, "Named “$it” in Navidrome") }
    if (publication.missing > 0) parts += "${publication.missing} not in Navidrome yet, added once it scanned them"
    if (publication.hidden > 0) parts += "${publication.hidden} in a library this user cannot see"
    ago(publication.publishedAt).takeIf { it.isNotEmpty() }?.let { parts += it }
    return parts.joinToString(" · ")
}

/** Minutes, hours or days: as the web's interval field. */
private enum class IntervalUnit(val minutes: Int, val label: String) { Minutes(1, "minutes"), Hours(60, "hours"), Days(1440, "days") }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AutomationSheet(current: PlaylistAutomation, busy: Boolean, onSave: (PlaylistAutomation) -> Unit, onDismiss: () -> Unit) {
    val startUnit = when {
        current.intervalMinutes >= 1440 && current.intervalMinutes % 1440 == 0 -> IntervalUnit.Days
        current.intervalMinutes >= 60 && current.intervalMinutes % 60 == 0 -> IntervalUnit.Hours
        else -> IntervalUnit.Minutes
    }
    var scan by remember { mutableStateOf(current.scan) }
    var download by remember { mutableStateOf(current.download) }
    var unit by remember { mutableStateOf(startUnit) }
    var value by remember { mutableStateOf(current.intervalMinutes / startUnit.minutes) }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = D2nColors.Ink2,
        contentColor = D2nColors.Text,
    ) {
        Column(
            Modifier.fillMaxWidth().navigationBarsPadding().imePadding().padding(horizontal = 24.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Automation", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            ToggleRow("Scan automatically", scan, { on ->
                scan = on
                if (!on) download = false
            }, description = "Runs a quick scan on a schedule to pick up new tracks.")
            if (scan) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Bottom) {
                    NumberField("Every", value, { value = it }, 1..999, Modifier.weight(1f))
                    ChoiceField("Unit", IntervalUnit.entries.map { it to it.label }, unit, { unit = it }, Modifier.weight(1f))
                }
            }
            ToggleRow(
                "Download missing tracks",
                download,
                { download = it },
                description = "After each automatic scan, download the tracks that are not in the library.",
                enabled = scan,
            )
            D2nButton(
                if (busy) "Saving…" else "Save automation",
                { onSave(PlaylistAutomation(scan, (value * unit.minutes).coerceAtLeast(1), download && scan)) },
                Modifier.fillMaxWidth(),
                enabled = !busy && LocalOnline.current,
            )
        }
    }
}
