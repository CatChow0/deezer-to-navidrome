package io.github.catchow0.d2n.ui.dashboard

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.LibraryStats
import io.github.catchow0.d2n.ui.common.RefreshOnReturn
import io.github.catchow0.d2n.ui.common.RefreshWhenTasksEnd
import io.github.catchow0.d2n.ui.common.ago
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.StatTile
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.playlists.NavidromeListRow
import io.github.catchow0.d2n.ui.playlists.PlaylistListRow
import io.github.catchow0.d2n.ui.share.linkIn
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes
import java.text.NumberFormat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The dashboard: search, the profile's playlists, those its user made in
 * Navidrome, and the library. [shared] is a link another app shared, which
 * opens the Add sheet with it.
 */
@Composable
fun DashboardScreen(
    vm: DashboardViewModel,
    onSearch: () -> Unit,
    onOpenPlaylist: (String) -> Unit,
    onOpenNavidrome: (account: String, id: String, name: String) -> Unit,
    shared: String?,
    onSharedTaken: () -> Unit,
) {
    val playlists by vm.playlists.collectAsStateWithLifecycle()
    val library by vm.library.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val opened by vm.opened.collectAsStateWithLifecycle()
    var adding by rememberSaveable { mutableStateOf<String?>(null) }

    LaunchedEffect(shared) {
        if (shared != null) {
            // "Listen to … on Spotify: https://…": the link alone in the field.
            adding = linkIn(shared)
            onSharedTaken()
        }
    }
    // Back from a playlist or a task: its counts may have changed.
    RefreshOnReturn(vm, vm::refresh)
    RefreshWhenTasksEnd(vm, vm::refresh)
    LaunchedEffect(opened) {
        opened?.let {
            vm.onOpened()
            onOpenPlaylist(it)
        }
    }

    ScreenScaffold(
        title = "Dashboard",
        refreshing = playlists.refreshing || library.refreshing,
        onRefresh = vm::refresh,
    ) {
        item(key = "search") { SearchEntry(onSearch) }
        item(key = "playlists-head") {
            SectionHeader(
                "Playlists",
                subtitle = "Open a playlist to match it against your library and fetch what is missing.",
                action = { D2nButton("Add", { adding = "" }, kind = ButtonKind.Ghost, small = true, icon = R.drawable.ic_add, enabled = LocalOnline.current) },
            )
        }
        remote(playlists, onRetry = vm::refresh) { answer ->
            val own = answer.own()
            if (own.isEmpty()) {
                item(key = "playlists-empty") {
                    EmptyState("No playlists yet. Add a Deezer or Spotify playlist link, or import a CSV.", actionLabel = "Add a playlist", onAction = { adding = "" })
                }
            }
            items(own, key = { "p-${it.id}" }) { tile -> PlaylistListRow(tile, onClick = { onOpenPlaylist(tile.id) }) }
            if (answer.navidrome.isNotEmpty()) {
                item(key = "navidrome-head") {
                    SectionHeader("Also in Navidrome", subtitle = "Made by hand in Navidrome by this profile: shown here, changed there.")
                }
                items(answer.navidrome, key = { "n-${it.id}" }) { tile ->
                    NavidromeListRow(tile, onClick = { onOpenNavidrome(tile.account.ifBlank { answer.profile.orEmpty() }, tile.id, tile.name) })
                }
            }
        }
        item(key = "library-head") { SectionHeader("Your library") }
        item(key = "library") {
            LibraryCard(library.value, refreshing = "library" in busy, onRefresh = vm::startLibraryRefresh)
        }
    }

    adding?.let { initial ->
        AddPlaylistSheet(
            initial = initial,
            busy = "add" in busy || "import" in busy,
            onAdd = { link ->
                adding = null
                vm.add(link)
            },
            onImport = { name, bytes ->
                adding = null
                vm.importCsv(name, bytes)
            },
            onDismiss = { adding = null },
        )
    }
}

/** Looks like a search box; opens the search. */
@Composable
private fun SearchEntry(onSearch: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 52.dp)
            .background(D2nColors.GlassRaised, D2nShapes.Control)
            .border(1.dp, D2nColors.LineStrong, D2nShapes.Control)
            .clickable(role = Role.Button, onClickLabel = "Search Deezer", onClick = onSearch)
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(painterResource(R.drawable.ic_search), contentDescription = null, tint = D2nColors.Muted)
        Text("Find music on Deezer: a track, an album or an artist", color = D2nColors.Muted, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun LibraryCard(stats: LibraryStats?, refreshing: Boolean, onRefresh: () -> Unit) {
    val numbers = NumberFormat.getIntegerInstance()
    GlassCard(Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile(stats?.let { numbers.format(it.count) } ?: "—", "Tracks", Modifier.weight(1f))
            StatTile(stats?.let { numbers.format(it.artists) } ?: "—", "Artists", Modifier.weight(1f))
            StatTile(stats?.let { numbers.format(it.albums) } ?: "—", "Albums", Modifier.weight(1f))
        }
        stats?.generatedAt?.let { Text("Indexed ${ago(it)}", style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted) }
        D2nButton(
            if (refreshing) "Starting…" else "Refresh library",
            onRefresh,
            kind = ButtonKind.Ghost,
            small = true,
            icon = R.drawable.ic_refresh,
            enabled = !refreshing && LocalOnline.current,
        )
    }
}

/** Add a playlist: its link, or a CSV file. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddPlaylistSheet(
    initial: String,
    busy: Boolean,
    onAdd: (String) -> Unit,
    onImport: (String, ByteArray) -> Unit,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var link by remember { mutableStateOf(initial) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            scope.launch {
                val file = withContext(Dispatchers.IO) { readDocument(context, uri) }
                if (file != null) onImport(file.first, file.second)
            }
        }
    }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = D2nColors.Ink2,
        contentColor = D2nColors.Text,
    ) {
        Column(
            Modifier.fillMaxWidth().navigationBarsPadding().imePadding().padding(horizontal = 24.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("Add a playlist", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            D2nTextField(
                link,
                { link = it },
                "Deezer or Spotify playlist link",
                placeholder = "https://www.deezer.com/playlist/…",
                supporting = "A Deezer playlist ID works too.",
                imeAction = ImeAction.Go,
                onIme = { if (link.isNotBlank()) onAdd(link) },
            )
            D2nButton(if (busy) "Adding…" else "Add", { onAdd(link) }, Modifier.fillMaxWidth(), enabled = link.isNotBlank() && !busy)
            HorizontalDivider(color = D2nColors.Line)
            Text(
                "Or import a CSV from Exportify, TuneMyMusic or Soundiiz: any size, private playlists too.",
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Muted,
            )
            D2nButton(
                "Import a CSV",
                { picker.launch(arrayOf("text/csv", "text/comma-separated-values", "text/plain", "application/csv")) },
                Modifier.fillMaxWidth(),
                kind = ButtonKind.Ghost,
                icon = R.drawable.ic_file,
                enabled = !busy,
            )
        }
    }
}

/** A document the user picked: its name and its bytes, or null when it cannot be read. */
private fun readDocument(context: Context, uri: Uri): Pair<String, ByteArray>? = try {
    val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) cursor.getString(0) else null
    } ?: "playlist.csv"
    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
    name to bytes
} catch (e: Exception) {
    null
}
