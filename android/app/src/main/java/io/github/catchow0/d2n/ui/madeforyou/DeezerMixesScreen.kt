package io.github.catchow0.d2n.ui.madeforyou

import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
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
import io.github.catchow0.d2n.ui.components.remote
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The mixes and playlists Deezer makes for the profile's Deezer account. */
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

    /** A Deezer playlist is added as any other. */
    fun add(pick: DeezerPick) {
        act(
            "pick-${pick.id}",
            { addPlaylist(LinkRequest(pick.id)) },
            done = { Notice(it.message.ifBlank { "Playlist added" }) },
            after = { mark(picks = { list -> list.map { if (it.id == pick.id) it.copy(followed = true) else it } }) },
        )
    }

    private fun mark(mixes: (List<DeezerMix>) -> List<DeezerMix> = { it }, picks: (List<DeezerPick>) -> List<DeezerPick> = { it }) {
        _found.update { remote ->
            val shown = remote.value ?: return@update remote
            remote.copy(value = shown.copy(mixes = mixes(shown.mixes), playlists = picks(shown.playlists)))
        }
    }
}

@Composable
fun DeezerMixesScreen(vm: DeezerMixesViewModel, onBack: () -> Unit) {
    val found by vm.found.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    ScreenScaffold(title = "Deezer mixes", onBack = onBack, refreshing = found.refreshing, onRefresh = vm::refresh) {
        remote(found, onRetry = vm::refresh, skeletons = 5, skeletonHeight = 64.dp) { answer ->
            if (answer.mixes.isEmpty() && answer.playlists.isEmpty()) {
                item(key = "empty") { EmptyState("Deezer suggests nothing for this account right now.") }
            }
            answer.mixes.groupBy { it.group.ifBlank { "Mixes" } }.forEach { (group, mixes) ->
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
            answer.playlists.groupBy { it.group.ifBlank { "Playlists" } }.forEach { (group, picks) ->
                item(key = "p-$group") { SectionHeader(group, subtitle = "Playlists Deezer suggests: added as any other playlist.") }
                items(picks, key = { "p-${it.id}" }) { pick ->
                    ListRow(
                        title = pick.title,
                        subtitle = pick.subtitle.ifBlank { null },
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
    }
}
