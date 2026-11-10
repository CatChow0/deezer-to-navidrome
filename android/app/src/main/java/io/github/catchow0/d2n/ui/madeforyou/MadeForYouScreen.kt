package io.github.catchow0.d2n.ui.madeforyou

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.audio.PreviewPlayer
import io.github.catchow0.d2n.data.MixTrack
import io.github.catchow0.d2n.data.MixesAnswer
import io.github.catchow0.d2n.ui.common.RefreshOnReturn
import io.github.catchow0.d2n.ui.common.RefreshWhenTasksEnd
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
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.PlayButton
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SearchField
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.SegmentedTabs
import io.github.catchow0.d2n.ui.components.SheetAction
import io.github.catchow0.d2n.ui.components.ToggleRow
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.playlists.PlaylistListRow
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes
import kotlinx.coroutines.launch

/** The web's words for each version. */
fun modeText(mode: String, blendPercent: Int): String = when (mode) {
    "daily" -> "Up to 4 mixes around a track, an album or an artist you keep coming back to, only with music you already have."
    "blend" -> "The same idea as Daily Mix, with $blendPercent% of tracks you do not have yet. They are downloaded and go on trial."
    else -> "No Daily Mix. Turning it off removes these playlists, and tracks on trial stay on trial."
}

private val MODES = listOf("off" to "Off", "daily" to "Daily Mix", "blend" to "Daily Mix+")

private sealed interface Ask {
    data object KeepAll : Ask
    data object EmptyTrash : Ask
    data object Undo : Ask
}

@Composable
fun MadeForYouScreen(
    vm: MadeForYouViewModel,
    player: PreviewPlayer,
    onSettings: () -> Unit,
    onOpenPlaylist: (String) -> Unit,
    onDeezerMixes: () -> Unit,
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val playlists by vm.playlists.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val now by player.now.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var list by rememberSaveable { mutableStateOf(TrialList.Trial) }
    var query by rememberSaveable { mutableStateOf("") }
    var sorts by rememberSaveable { mutableStateOf(mapOf<TrialList, TrialSort>()) }
    var filters by rememberSaveable { mutableStateOf(mapOf<TrialList, String>()) }
    var opened by remember { mutableStateOf<MixTrack?>(null) }
    var ask by remember { mutableStateOf<Ask?>(null) }

    RefreshOnReturn(vm, vm::refresh)
    RefreshWhenTasksEnd(vm, vm::refresh)
    ScreenScaffold(
        title = "Made for you",
        actions = { IconAction(R.drawable.ic_tune, "Limits and trial rules", onSettings) },
        refreshing = state.refreshing,
        onRefresh = vm::refresh,
    ) {
        remote(state, onRetry = vm::refresh, skeletons = 4, skeletonHeight = 96.dp) { s ->
            item(key = "versions") { Versions(s, busy, online, vm, onUndo = { ask = Ask.Undo }) }

            val generated = playlists.filter { it.kind == "auto" }
            item(key = "mixes-head") {
                SectionHeader("Your mixes", subtitle = "Playlists built from what you listen to. New tracks they download stay on trial until you decide.")
            }
            if (generated.isEmpty()) {
                item(key = "mixes-empty") { EmptyState("Nothing yet. Turn on Daily Mix, Daily Mix+ or Discover above.") }
            }
            items(generated, key = { "g-${it.id}" }) { tile -> PlaylistListRow(tile, onClick = { onOpenPlaylist(tile.id) }) }

            item(key = "quarantine-head") { SectionHeader("Quarantine") }
            item(key = "lists") {
                SegmentedTabs(
                    TrialList.entries.map { it to "${it.label} (${s.tracksOf(it).size})" },
                    list,
                    { list = it; query = "" },
                )
            }
            item(key = "intro") { Text(introText(list, s), style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted) }
            val all = s.tracksOf(list)
            val sortOptions = TrialSort.of(list)
            val sort = sorts[list]?.takeIf { it in sortOptions } ?: sortOptions.first()
            val filterOptions = trialFilters(list, all)
            val filter = filters[list]?.takeIf { key -> filterOptions.any { it.first == key } } ?: "all"
            val visible = all.shown(query, sort, filter)
            if (all.isEmpty()) {
                item(key = "list-empty") { EmptyState(list.empty) }
            } else {
                item(key = "toolbar") {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SearchField(query, { query = it }, "Search title, artist or album")
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            ChoiceField("Sort", sortOptions.map { it to it.label }, sort, { sorts = sorts + (list to it) }, Modifier.weight(1f))
                            ChoiceField("Show", filterOptions, filter, { filters = filters + (list to it) }, Modifier.weight(1f))
                        }
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                if (visible.size == all.size) plural(all.size, "track") else "${visible.size} of ${plural(all.size, "track")}",
                                Modifier.weight(1f),
                                style = MaterialTheme.typography.bodySmall,
                                color = D2nColors.Muted,
                            )
                            if (list == TrialList.Review && visible.isNotEmpty()) {
                                D2nButton(
                                    "Keep ${if (visible.size == all.size) "all" else "these"} ${visible.size}",
                                    { ask = Ask.KeepAll },
                                    small = true,
                                    enabled = online && "keep-all" !in busy,
                                )
                            }
                            if (list == TrialList.Trash) {
                                D2nButton("Empty trash", { ask = Ask.EmptyTrash }, kind = ButtonKind.Danger, small = true, enabled = online && "empty-trash" !in busy)
                            }
                        }
                        if (list != TrialList.Trash) {
                            Text("Swipe right to keep, left to remove.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Faint)
                        } else {
                            Text("Swipe right to restore.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Faint)
                        }
                    }
                }
                if (visible.isEmpty()) item(key = "no-match") { EmptyState("No track matches.") }
                items(visible, key = { "t-${list.name}-${it.id}" }) { track ->
                    SwipeTrack(
                        list = list,
                        track = track,
                        enabled = online && "track-${track.id}" !in busy,
                        playing = now?.id == track.id && now?.playing == true,
                        onPlay = { player.playDeezer(track.id, track.title, track.artist, null) },
                        onKeep = { vm.keep(track) },
                        onRemove = { vm.remove(track) },
                        onRestore = { vm.restore(track) },
                        onOpen = { opened = track },
                    )
                }
            }

            val followed = playlists.filter { it.kind == "mix" }
            item(key = "deezer-head") {
                SectionHeader(
                    "Deezer mixes",
                    subtitle = "Mixes Deezer makes for you. Their tracks change, and every scan picks up the current ones.",
                    action = { D2nButton("Choose", onDeezerMixes, kind = ButtonKind.Ghost, small = true) },
                )
            }
            if (followed.isEmpty()) {
                item(key = "deezer-empty") {
                    EmptyState("No mixes followed yet. Add a Deezer account in Settings, then choose the mixes to keep in your library.", actionLabel = "Choose mixes", onAction = onDeezerMixes)
                }
            }
            items(followed, key = { "m-${it.id}" }) { tile -> PlaylistListRow(tile, onClick = { onOpenPlaylist(tile.id) }) }
        }
    }

    opened?.let { track ->
        ActionSheet(
            title = track.title,
            subtitle = listOf(track.artist, track.album).filter(String::isNotBlank).joinToString(" · "),
            actions = buildList {
                add(SheetAction("Play the preview", R.drawable.ic_play) { player.playDeezer(track.id, track.title, track.artist, null) })
                if (list == TrialList.Trash) {
                    add(SheetAction("Restore", R.drawable.ic_restore, enabled = online) { vm.restore(track) })
                } else {
                    add(SheetAction("Keep", R.drawable.ic_check, enabled = online) { vm.keep(track) })
                    add(SheetAction("Remove", R.drawable.ic_delete, danger = true, enabled = online) { vm.remove(track) })
                }
            },
            onDismiss = { opened = null },
        )
    }

    val shownState = state.value
    when (ask) {
        null -> Unit
        Ask.KeepAll -> {
            val all = shownState?.pending.orEmpty()
            val ids = all.shown(query, sorts[TrialList.Review] ?: TrialSort.NewestState, filters[TrialList.Review] ?: "all").map { it.id }
            ConfirmDialog(
                "Keep ${plural(ids.size, "track")}?",
                "They move to your downloads, for every profile.",
                "Keep",
                onConfirm = { vm.keepAll(ids) },
                onDismiss = { ask = null },
                danger = false,
            )
        }
        Ask.EmptyTrash -> ConfirmDialog(
            "Empty the trash?",
            "Deletes ${plural(shownState?.trash?.size ?: 0, "file")} for good.",
            "Empty trash",
            onConfirm = vm::emptyTheTrash,
            onDismiss = { ask = null },
        )
        Ask.Undo -> ConfirmDialog(
            "Undo the metadata fix?",
            "Removes what was added to ${plural(shownState?.analysis?.canUndo ?: 0, "file")}.",
            "Undo",
            onConfirm = vm::startUndoMetadata,
            onDismiss = { ask = null },
        )
    }
}

private fun introText(list: TrialList, state: MixesAnswer): String {
    val s = state.settings
    return when (list) {
        TrialList.Trial -> {
            if (!s.trialAuto) {
                "Automatic validation is off: tracks stay here until you keep or remove them."
            } else {
                val marks = if (s.trialMarks) ", or star it or rate it 4 or 5 in Navidrome" else ""
                val then = if (s.trialBypass) "it is kept at once" else "it waits under To review"
                val end = if (s.trialDelete) "it is deleted" else "it goes to the trash"
                "Play a track ${plural(s.trialPlays, "time")}$marks, and $then. After ${plural(s.trialDays, "day")} without that, $end."
            }
        }
        TrialList.Review -> "These tracks earned their place. Keep moves them to your downloads, Remove sends them to the trash. They wait here as long as needed."
        TrialList.Trash -> "Removed tracks wait here for ${plural(s.trashDays, "day")}, then the file is deleted. They are never proposed again."
    }
}

@Composable
private fun Versions(state: MixesAnswer, busy: Set<String>, online: Boolean, vm: MadeForYouViewModel, onUndo: () -> Unit) {
    val s = state.settings
    val blocked = state.downloadsBlocked
    val anyOn = s.mixMode != "off" || s.discover
    val a = state.analysis
    GlassCard(Modifier.fillMaxWidth()) {
        if (state.profile.several) {
            Text(
                "For ${state.profile.label}: built from ${state.profile.label}'s listening history and published for this profile only.",
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Muted,
            )
        }
        SegmentedTabs(MODES, s.mixMode, { mode ->
            if (mode == "blend" && blocked.isNotBlank()) vm.notifyBlocked(blocked) else if (mode != s.mixMode) vm.setMode(mode)
        })
        Text(modeText(s.mixMode, s.blendNewPercent), style = MaterialTheme.typography.bodyMedium, color = D2nColors.TextSoft)
        if (s.mixMode != "blend" && blocked.isNotBlank()) Banner("Daily Mix+ cannot be chosen. $blocked", BannerTone.Warn)
        ToggleRow(
            "Discover",
            s.discover,
            { vm.setDiscover(it) },
            description = "Only new releases and tracks you never heard, chosen from your habits. They are downloaded and go on trial." +
                if (!s.discover && blocked.isNotBlank()) " $blocked" else "",
            enabled = online && "settings" !in busy && (s.discover || blocked.isBlank()),
        )
        Text(
            if (a.left > 0) {
                "Missing metadata: ${a.total - a.left} of ${a.total} files done. " +
                    if (anyOn) "Mixes start once most of it is done." else "Turning a version on starts it: it adds the missing tempo and genre to your files' tags."
            } else {
                "Tempo and genre checked for all ${a.total} files."
            },
            style = MaterialTheme.typography.bodySmall,
            color = D2nColors.Muted,
        )
        if (a.writeErrors > 0) Banner("${plural(a.writeErrors, "file")} could not be tagged. Is the folder mounted read-only? Writing is tried again every day.", BannerTone.Warn)
        if (a.paused) Text("Fix missing metadata was cancelled, so it does not run on its own.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
        if (a.writeOff) Text("Writing to your files is off since the last undo. Fix missing metadata turns it back on.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
        state.lastRun?.notes?.takeIf { it.isNotEmpty() }?.let { Banner(it.joinToString(" "), BannerTone.Warn) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            D2nButton(
                if (state.running) "Generating…" else "Regenerate now",
                vm::generate,
                small = true,
                enabled = online && anyOn && !state.running && "generate" !in busy,
            )
            if (a.paused || a.writeOff || a.left > 0) {
                D2nButton("Fix missing metadata", vm::startFixMetadata, kind = ButtonKind.Ghost, small = true, enabled = online && !a.running && "fix-metadata" !in busy)
            } else if (a.canUndo > 0) {
                D2nButton("Undo metadata fix", onUndo, kind = ButtonKind.Ghost, small = true, enabled = online && "undo-metadata" !in busy)
            }
        }
    }
}

/** A track of the quarantine: swipe right to keep (or restore), left to remove. */
@Composable
private fun SwipeTrack(
    list: TrialList,
    track: MixTrack,
    enabled: Boolean,
    playing: Boolean,
    onPlay: () -> Unit,
    onKeep: () -> Unit,
    onRemove: () -> Unit,
    onRestore: () -> Unit,
    onOpen: () -> Unit,
) {
    val haptics = LocalHapticFeedback.current
    val scope = rememberCoroutineScope()
    val swipe = rememberSwipeToDismissBoxState()
    val trash = list == TrialList.Trash
    val actions = if (trash) {
        listOf(CustomAccessibilityAction("Restore") { onRestore(); true })
    } else {
        listOf(CustomAccessibilityAction("Keep") { onKeep(); true }, CustomAccessibilityAction("Remove") { onRemove(); true })
    }
    SwipeToDismissBox(
        state = swipe,
        modifier = Modifier.semantics { customActions = actions },
        enableDismissFromStartToEnd = enabled,
        enableDismissFromEndToStart = enabled && !trash,
        onDismiss = { value ->
            haptics.performHapticFeedback(HapticFeedbackType.LongPress)
            when (value) {
                SwipeToDismissBoxValue.StartToEnd -> if (trash) onRestore() else onKeep()
                SwipeToDismissBoxValue.EndToStart -> onRemove()
                SwipeToDismissBoxValue.Settled -> Unit
            }
            // The list changes when the server answers; on a failure the row comes back.
            scope.launch { swipe.snapTo(SwipeToDismissBoxValue.Settled) }
        },
        backgroundContent = {
            val direction = swipe.dismissDirection
            val keep = direction == SwipeToDismissBoxValue.StartToEnd
            val color = when (direction) {
                SwipeToDismissBoxValue.StartToEnd -> D2nColors.OkBg
                SwipeToDismissBoxValue.EndToStart -> D2nColors.MissBg
                SwipeToDismissBoxValue.Settled -> D2nColors.Glass
            }
            Row(
                Modifier.fillMaxSize().clip(D2nShapes.Tile).background(color).padding(horizontal = 20.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = if (keep) Arrangement.Start else Arrangement.End,
            ) {
                if (direction != SwipeToDismissBoxValue.Settled) {
                    Icon(
                        painterResource(if (keep) (if (trash) R.drawable.ic_restore else R.drawable.ic_check) else R.drawable.ic_delete),
                        contentDescription = null,
                        tint = if (keep) D2nColors.Ok else D2nColors.Miss,
                    )
                    Text(
                        if (keep) (if (trash) " Restore" else " Keep") else " Remove",
                        color = if (keep) D2nColors.Ok else D2nColors.Miss,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }
        },
    ) {
        ListRow(
            title = track.title,
            subtitle = listOf(track.artist, track.album).filter(String::isNotBlank).joinToString(" · "),
            leading = { Cover(track.cover, track.title, size = 48.dp) },
            chips = {
                Chip(list.detail(track), tone = ChipTone.Idle)
                if (track.source.isNotBlank()) Chip(track.source, tone = ChipTone.Info)
                if (track.sharedWith.isNotEmpty()) Chip("Also on trial for ${track.sharedWith.joinToString(", ")}", tone = ChipTone.Partial)
            },
            trailing = { PlayButton(playing, "Play a preview of ${track.artist} - ${track.title}", onPlay) },
            onClick = onOpen,
            clickLabel = "Actions",
        )
    }
}
