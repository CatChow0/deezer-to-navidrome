package io.github.catchow0.d2n.ui.releases

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.Release
import io.github.catchow0.d2n.ui.common.RefreshOnReturn
import io.github.catchow0.d2n.ui.common.RefreshWhenTasksEnd
import io.github.catchow0.d2n.ui.components.ActionSheet
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.Cover
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.ExplicitMark
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.SegmentedTabs
import io.github.catchow0.d2n.ui.components.SheetAction
import io.github.catchow0.d2n.ui.components.ToggleRow
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.search.rememberOpenLink
import io.github.catchow0.d2n.ui.theme.D2nColors

private const val FOLLOWED_PREVIEW = 8

@Composable
fun ReleasesScreen(vm: ReleasesViewModel, onAlbum: (id: String, title: String) -> Unit, onSettings: () -> Unit) {
    val feed by vm.feed.collectAsStateWithLifecycle()
    val owned by vm.owned.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    val open = rememberOpenLink()
    var type by rememberSaveable { mutableStateOf(ReleaseType.All) }
    var hideFeatures by rememberSaveable { mutableStateOf(false) }
    var hideOwned by rememberSaveable { mutableStateOf(false) }
    var allArtists by rememberSaveable { mutableStateOf(false) }
    var picked by remember { mutableStateOf<Release?>(null) }

    RefreshOnReturn(vm, vm::refresh)
    RefreshWhenTasksEnd(vm, vm::refresh)
    ScreenScaffold(
        title = "Releases",
        actions = {
            IconAction(R.drawable.ic_refresh, "Refresh the feed from Deezer", vm::rebuild, enabled = online && feed.value?.connected == true && "rebuild" !in busy)
        },
        refreshing = feed.refreshing,
        onRefresh = vm::refresh,
    ) {
        item(key = "lead") {
            Text(
                "What your favorite Deezer artists put out recently, and whether it is already in your library.",
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Muted,
            )
        }
        remote(feed, onRetry = vm::refresh, skeletons = 6, skeletonHeight = 80.dp) { answer ->
            item(key = "feed") {
                GlassCard(Modifier.fillMaxWidth()) {
                    Text(feedLine(answer), style = MaterialTheme.typography.bodyMedium, color = D2nColors.TextSoft)
                    if (answer.failedArtists > 0) {
                        Text("${plural(answer.failedArtists, "artist")} could not be read at the last refresh.", style = MaterialTheme.typography.bodySmall, color = D2nColors.Partial)
                    }
                    if (!answer.connected) {
                        D2nButton("Open Settings", onSettings, kind = ButtonKind.Ghost, small = true)
                    } else {
                        D2nButton(
                            if ("rebuild" in busy) "Starting…" else "Refresh now",
                            vm::rebuild,
                            kind = ButtonKind.Ghost,
                            small = true,
                            icon = R.drawable.ic_refresh,
                            enabled = online && "rebuild" !in busy,
                        )
                    }
                }
            }
            if (!answer.connected) return@remote
            item(key = "filters") {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    SegmentedTabs(ReleaseType.entries.map { it to it.label }, type, { type = it })
                    ToggleRow("Hide features", hideFeatures, { hideFeatures = it }, description = "Releases where your artist is only a guest.")
                    ToggleRow("Hide what I own", hideOwned, { hideOwned = it })
                }
            }
            val shown = answer.visible(owned, ReleaseFilters(type, hideFeatures, hideOwned))
            if (shown.isEmpty()) {
                item(key = "none") {
                    EmptyState(if (answer.releases.isEmpty()) "No releases from your favorite artists in this period." else "Nothing left with these filters.")
                }
            }
            shown.groupBy { releaseGroup(it) }.forEach { (group, releases) ->
                item(key = "g-$group") {
                    Text(group, Modifier.semantics { heading() }, style = MaterialTheme.typography.titleSmall, color = D2nColors.TextSoft)
                }
                items(releases, key = { "r-${it.id}" }) { release -> ReleaseRow(release, ownership(owned[release.id], release), owned[release.id]?.let { it.ownedCount to (it.total ?: release.nbTracks) }) { picked = release } }
            }
            item(key = "followed-head") {
                SectionHeader(
                    "Artists you follow",
                    subtitle = "Your Deezer favorites. Mute one to drop it from this feed; to unfollow it, open its Deezer page.",
                )
            }
            val active = answer.followedArtists.filter { it.id !in answer.muted }.sortedWith(compareByDescending<io.github.catchow0.d2n.data.FollowedArtist> { it.releases }.thenBy { it.name.lowercase() })
            if (answer.followedArtists.isEmpty()) {
                item(key = "followed-none") { EmptyState("Refresh the feed to see the artists it follows.") }
            }
            items(if (allArtists) active else active.take(FOLLOWED_PREVIEW), key = { "a-${it.id}" }) { artist ->
                ListRow(
                    title = artist.name,
                    subtitle = if (artist.releases > 0) plural(artist.releases, "release") else "Nothing recent",
                    leading = { Cover(artist.picture, artist.name, size = 44.dp, shape = androidx.compose.foundation.shape.CircleShape) },
                    trailing = {
                        D2nButton("Mute", { vm.setMuted(artist.id, artist.name, true) }, kind = ButtonKind.Ghost, small = true, enabled = online && "mute-${artist.id}" !in busy)
                    },
                    onClick = { open("https://www.deezer.com/artist/${artist.id}") },
                    clickLabel = "Open in Deezer",
                )
            }
            if (active.size > FOLLOWED_PREVIEW) {
                item(key = "followed-more") {
                    D2nButton(if (allArtists) "Show fewer" else "Show all ${active.size}", { allArtists = !allArtists }, kind = ButtonKind.Ghost, small = true)
                }
            }
            if (answer.muted.isNotEmpty()) {
                item(key = "muted-head") { SectionHeader("Muted") }
                items(answer.muted.entries.toList(), key = { "m-${it.key}" }) { (id, name) ->
                    val shownName = answer.followedArtists.firstOrNull { it.id == id }?.name ?: name
                    ListRow(
                        title = shownName,
                        subtitle = "Muted",
                        trailing = {
                            D2nButton("Unmute", { vm.setMuted(id, shownName, false) }, kind = ButtonKind.Ghost, small = true, enabled = online && "mute-$id" !in busy)
                        },
                    )
                }
            }
        }
    }

    picked?.let { release ->
        val upcoming = isUpcoming(release)
        ActionSheet(
            title = release.title,
            subtitle = release.artist,
            actions = buildList {
                add(SheetAction("Open the album", R.drawable.ic_note) { onAlbum(release.id, release.title) })
                add(SheetAction(if (upcoming) "Not out yet" else "Download the album", R.drawable.ic_download, enabled = online && !upcoming) {
                    vm.download("album", release.id, "${release.artist} - ${release.title}")
                })
                release.followedArtists().filter { it.id !in (feed.value?.muted ?: emptyMap()) }.forEach { artist ->
                    add(SheetAction("Mute ${artist.name}", R.drawable.ic_close, enabled = online) { vm.setMuted(artist.id, artist.name, true) })
                }
                add(SheetAction("Open in Deezer", R.drawable.ic_open) { open("https://www.deezer.com/album/${release.id}") })
            },
            onDismiss = { picked = null },
        )
    }
}

@Composable
private fun ReleaseRow(release: Release, owned: Ownership?, counts: Pair<Int, Int>?, onOpen: () -> Unit) {
    val type = TYPE_LABEL[release.recordType] ?: release.recordType.replaceFirstChar { it.uppercase() }
    val tracks = if (release.nbTracks > 1) ", ${release.nbTracks} tracks" else ""
    val with = if (release.featured) " with ${release.followedArtists().joinToString(", ") { it.name }}" else ""
    ListRow(
        title = release.title,
        subtitle = "${release.artist}$with\n$type$tracks, ${releaseDay(release)}",
        leading = { Cover(release.cover, release.title) },
        chips = if (owned == Ownership.Full || owned == Ownership.Partial || release.explicit || isUpcoming(release) || release.featured) ({
            if (release.explicit) ExplicitMark()
            if (isUpcoming(release)) Chip("Not out yet", tone = ChipTone.Info)
            if (release.featured) Chip("Feature")
            when (owned) {
                Ownership.Full -> Chip("In library", tone = ChipTone.Ok)
                Ownership.Partial -> Chip("${counts?.first}/${counts?.second?.takeIf { it > 0 } ?: "?"} tracks owned", tone = ChipTone.Partial)
                else -> Unit
            }
        }) else null,
        onClick = onOpen,
        clickLabel = "Actions",
    )
}
