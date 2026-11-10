package io.github.catchow0.d2n.ui.playlists

import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.NavidromePlaylist
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.formatDuration
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** A playlist the user made in Navidrome, read from Navidrome as that user. */
class NavidromePlaylistViewModel(deps: ScreenDeps, private val account: String, private val id: String) : D2nViewModel(deps) {
    private val _playlist = MutableStateFlow(Remote<NavidromePlaylist>())
    val playlist: StateFlow<Remote<NavidromePlaylist>> = _playlist

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { _playlist.fill { navidromePlaylist(account, id).playlist } }
    }
}

@Composable
fun NavidromePlaylistScreen(vm: NavidromePlaylistViewModel, name: String, onBack: () -> Unit) {
    val playlist by vm.playlist.collectAsStateWithLifecycle()
    ScreenScaffold(title = playlist.value?.name?.ifBlank { null } ?: name, onBack = onBack, refreshing = playlist.refreshing, onRefresh = vm::refresh) {
        item(key = "note") { Banner("Made by hand in Navidrome: change it there.", BannerTone.Info) }
        remote(playlist, onRetry = vm::refresh, skeletons = 6, skeletonHeight = 56.dp) { found ->
            item(key = "count") {
                Text(
                    listOf(plural(found.songCount, "track"), formatDuration(found.duration)).filter(String::isNotBlank).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = D2nColors.Muted,
                )
            }
            if (found.tracks.isEmpty()) item(key = "empty") { EmptyState("This playlist is empty.") }
            itemsIndexed(found.tracks) { index, track ->
                ListRow(
                    title = track.title,
                    subtitle = listOf(track.artist, track.album, formatDuration(track.duration)).filter(String::isNotBlank).joinToString(" · "),
                    leading = { Text("${index + 1}", Modifier.width(28.dp), style = MaterialTheme.typography.labelMedium, color = D2nColors.Faint) },
                )
            }
        }
    }
}
