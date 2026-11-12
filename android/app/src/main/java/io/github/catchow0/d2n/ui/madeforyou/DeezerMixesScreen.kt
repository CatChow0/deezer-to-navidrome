package io.github.catchow0.d2n.ui.madeforyou

import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.DeezerMix
import io.github.catchow0.d2n.data.DeezerMixesAnswer
import io.github.catchow0.d2n.data.DeezerPick
import io.github.catchow0.d2n.data.FollowMixRequest
import io.github.catchow0.d2n.data.LinkRequest
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.SegmentedTabs
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** From Deezer, as on the web: the account's own playlists, the mixes Deezer
 * makes for it, and the playlists it recommends. */
enum class DeezerTab(val label: String) { Yours("Your playlists"), Mixes("Mixes"), Recommended("Recommended") }

/** The profile's Deezer account: its playlists, and the mixes and playlists Deezer makes for it. */
class DeezerMixesViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _found = MutableStateFlow(Remote<DeezerMixesAnswer>())
    val found: StateFlow<Remote<DeezerMixesAnswer>> = _found

    init {
        followProfile { _found.fill { deezerMixes() } }
    }

    fun refresh() {
        viewModelScope.launch { _found.fill { deezerMixes() } }
    }

    fun follow(mix: DeezerMix) {
        act(
            "mix-${mix.kind}-${mix.sourceId}",
            { followMix(FollowMixRequest(mix.kind, mix.sourceId, mix.title)) },
            done = { Notice(if (it.added) "Following ${mix.title}: scan it to fill it" else "${mix.title} is already followed") },
            after = { mark(mixes = { list -> list.map { if (it.kind == mix.kind && it.sourceId == mix.sourceId) it.copy(followed = true) else it } }) },
        )
    }

    /** A Deezer playlist, the account's own or a recommended one, is added as any other. */
    fun add(pick: DeezerPick) {
        act(
            "pick-${pick.id}",
            { addPlaylist(LinkRequest(pick.id)) },
            done = { Notice(it.message.ifBlank { "Playlist added" }) },
            after = { mark(picks = { list -> list.map { if (it.id == pick.id) it.copy(followed = true) else it } }) },
        )
    }

    /** A favorite can also be recommended: it is marked in both. */
    private fun mark(mixes: (List<DeezerMix>) -> List<DeezerMix> = { it }, picks: (List<DeezerPick>) -> List<DeezerPick> = { it }) {
        _found.update { remote ->
            val shown = remote.value ?: return@update remote
            remote.copy(value = shown.copy(mixes = mixes(shown.mixes), playlists = picks(shown.playlists), yours = picks(shown.yours)))
        }
    }
}

@Composable
fun DeezerMixesScreen(vm: DeezerMixesViewModel, start: DeezerTab, onBack: () -> Unit) {
    val found by vm.found.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var tab by rememberSaveable { mutableStateOf(start) }
    ScreenScaffold(title = "From Deezer", onBack = onBack, refreshing = found.refreshing, onRefresh = vm::refresh) {
        item(key = "tabs") { SegmentedTabs(DeezerTab.entries.map { it to it.label }, tab, { tab = it }) }
        remote(found, onRetry = vm::refresh, skeletons = 5, skeletonHeight = 64.dp) { answer ->
            when (tab) {
                DeezerTab.Yours -> {
                    if (answer.yours.isEmpty()) {
                        item(key = "yours-empty") {
                            EmptyState(answer.yoursError?.let { "Deezer did not give this account's playlists: $it" } ?: "This Deezer account has no playlists yet.")
                        }
                    }
                    picks(answer.yours, vm, busy, online)
                }
                DeezerTab.Mixes -> mixes(answer.mixes, vm, busy, online)
                DeezerTab.Recommended -> {
                    if (answer.playlists.isEmpty()) item(key = "rec-empty") { EmptyState("Deezer recommends no playlist for this account right now.") }
                    picks(answer.playlists, vm, busy, online)
                }
            }
        }
    }
}

private fun LazyListScope.mixes(found: List<DeezerMix>, vm: DeezerMixesViewModel, busy: Set<String>, online: Boolean) {
    if (found.isEmpty()) item(key = "mixes-empty") { EmptyState("Deezer has no mixes for this account yet.") }
    found.groupBy { it.group.ifBlank { "Mixes" } }.forEach { (group, mixes) ->
        item(key = "g-$group") { SectionHeader(group) }
        items(mixes, key = { "m-${it.kind}-${it.sourceId}" }) { mix ->
            ListRow(
                title = mix.title,
                subtitle = mix.subtitle.ifBlank { null },
                leading = { Cover(null, mix.title, size = 48.dp) },
                trailing = {
                    if (mix.followed) {
                        Chip("Following", tone = ChipTone.Ok)
                    } else {
                        D2nButton("Follow", { vm.follow(mix) }, kind = ButtonKind.Ghost, small = true, enabled = online && "mix-${mix.kind}-${mix.sourceId}" !in busy)
                    }
                },
            )
        }
    }
}

private fun LazyListScope.picks(found: List<DeezerPick>, vm: DeezerMixesViewModel, busy: Set<String>, online: Boolean) {
    found.groupBy { it.group.ifBlank { "Playlists" } }.forEach { (group, picks) ->
        item(key = "pg-$group") { SectionHeader(group) }
        items(picks, key = { "p-$group-${it.id}" }) { pick ->
            ListRow(
                title = pick.title,
                subtitle = listOfNotNull(pick.subtitle.ifBlank { null }, pick.tracks?.let { plural(it, "track") }).joinToString(" · ").ifBlank { null },
                leading = { Cover(pick.picture, pick.title, size = 48.dp) },
                trailing = {
                    if (pick.followed) {
                        Chip("Added", tone = ChipTone.Ok)
                    } else {
                        D2nButton("Add", { vm.add(pick) }, kind = ButtonKind.Ghost, small = true, enabled = online && "pick-${pick.id}" !in busy)
                    }
                },
            )
        }
    }
}
