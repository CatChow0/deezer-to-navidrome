package io.github.catchow0.d2n.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.PathMapping
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.ChoiceField
import io.github.catchow0.d2n.ui.components.ConfirmDialog
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors

/** The pages of Settings, as the web groups them. */
enum class SettingsPage(val title: String, val subtitle: String) {
    Music("Music and downloads", "Folders, Navidrome paths, downloads, performance and the release feed"),
    Navidrome("Navidrome accounts", "One per Navidrome user: the profiles of the picker"),
    Deezer("Deezer accounts", "Releases, Deezer mixes and the downloads"),
    Listening("Listening stats", "How Navidrome sends this app your plays"),
    Security("Sign-in and other apps", "Password, API token, webhook and devices"),
    Maintenance("Maintenance", "Library index, metadata, repairs and duplicates"),
    Reset("Reset data", "Clear the index, match results or playlists"),
}

@Composable
fun SettingsHome(onBack: () -> Unit, onPage: (SettingsPage) -> Unit) {
    ScreenScaffold(title = "Settings", onBack = onBack) {
        items(SettingsPage.entries) { page ->
            ListRow(title = page.title, subtitle = page.subtitle, onClick = { onPage(page) }, clickLabel = "Open")
        }
    }
}

@Composable
private fun FieldNote(text: String) = Text(text, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)

private fun workersLabel(key: String, n: Int): String = n.toString() + when {
    key == "library_workers_per_dir" && n == 2 -> ", spinning disk (recommended)"
    key == "library_workers_per_dir" && n == 4 -> ", fast disk or RAID"
    key == "library_workers_per_dir" && n == 8 -> ", SSD or NVMe"
    key == "metadata_workers" && n == 4 -> ", default"
    key == "match_workers" && n == 4 -> ", default"
    key == "match_workers" && n == 1 -> ", single thread"
    else -> ""
}

private val REFRESH_LABELS = mapOf(6 to "Every 6 hours", 12 to "Every 12 hours", 24 to "Once a day", 48 to "Every 2 days", 168 to "Once a week", 0 to "Never, only when I ask")

@Composable
fun MusicSettingsScreen(vm: MusicSettingsViewModel, onBack: () -> Unit) {
    val saved by vm.saved.collectAsStateWithLifecycle()
    val draft by vm.draft.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    ScreenScaffold(title = "Music and downloads", onBack = onBack, refreshing = saved.refreshing, onRefresh = vm::refresh) {
        remote(saved, onRetry = vm::refresh, skeletons = 4, skeletonHeight = 140.dp) { answer ->
            val d = draft ?: return@remote
            val choices = answer.choices
            item(key = "folders") {
                SectionHeader("Music folders", subtitle = "Folders scanned to build the library index.")
                GlassCard(Modifier.fillMaxWidth()) {
                    d.scanDirs.forEachIndexed { i, dir ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            D2nTextField(dir, { value -> vm.edit { it.copy(scanDirs = it.scanDirs.toMutableList().also { l -> l[i] = value }) } }, "Folder ${i + 1}", Modifier.weight(1f))
                            IconAction(R.drawable.ic_close, "Remove this folder", { vm.edit { it.copy(scanDirs = it.scanDirs.filterIndexed { j, _ -> j != i }) } })
                        }
                    }
                    D2nButton("Add a folder", { vm.edit { it.copy(scanDirs = it.scanDirs + "") } }, kind = ButtonKind.Ghost, small = true, icon = R.drawable.ic_add)
                }
            }
            item(key = "mappings") {
                SectionHeader("Navidrome paths", subtitle = "How each folder appears inside Navidrome, so generated playlists point to the right files.")
                GlassCard(Modifier.fillMaxWidth()) {
                    d.mappings.forEachIndexed { i, m ->
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                D2nTextField(m.host, { v -> vm.edit { it.copy(mappings = it.mappings.replaced(i) { x -> x.copy(host = v) }) } }, "Folder on this server", Modifier.weight(1f), placeholder = "/music/library")
                                IconAction(R.drawable.ic_close, "Remove this mapping", { vm.edit { it.copy(mappings = it.mappings.filterIndexed { j, _ -> j != i }) } })
                            }
                            D2nTextField(m.navidrome, { v -> vm.edit { it.copy(mappings = it.mappings.replaced(i) { x -> x.copy(navidrome = v) }) } }, "Same folder in Navidrome", placeholder = "/music")
                        }
                    }
                    D2nButton("Add a mapping", { vm.edit { it.copy(mappings = it.mappings + PathMapping()) } }, kind = ButtonKind.Ghost, small = true, icon = R.drawable.ic_add)
                }
            }
            item(key = "downloads") {
                SectionHeader("Downloads")
                GlassCard(Modifier.fillMaxWidth()) {
                    D2nTextField(
                        d.deezerDlDir.orEmpty(),
                        { v -> vm.edit { it.copy(deezerDlDir = v) } },
                        "Folder for the downloads",
                        placeholder = answer.downloadsFolder.path,
                        supporting = "A folder on this server, not a web address. Leave it empty to use the deezer-dl folder of your music folders.",
                    )
                    val folder = answer.downloadsFolder
                    Banner(
                        when {
                            folder.writable -> "Downloads go to ${folder.path}"
                            folder.exists -> "${folder.path} exists but this app cannot write in it."
                            else -> "${folder.path} does not exist. Mount your downloads folder there, or set another folder above."
                        },
                        if (folder.writable) BannerTone.Info else BannerTone.Warn,
                    )
                }
            }
            item(key = "performance") {
                SectionHeader("Performance")
                GlassCard(Modifier.fillMaxWidth()) {
                    Workers("Library scan threads per folder", "library_workers_per_dir", d.libraryWorkersPerDir, choices) { n -> vm.edit { it.copy(libraryWorkersPerDir = n) } }
                    FieldNote("Each folder gets its own pool. More than 2 on a spinning disk causes seeks and slows the scan down.")
                    Workers("Download threads", "download_workers", d.downloadWorkers ?: 4, choices) { n -> vm.edit { it.copy(downloadWorkers = n) } }
                    FieldNote("How many tracks are fetched from Deezer at the same time. Deezer throttles the requests, so a low number is safer.")
                    Workers("Fix missing metadata threads", "metadata_workers", d.metadataWorkers ?: 4, choices) { n -> vm.edit { it.copy(metadataWorkers = n) } }
                    FieldNote("Up to the CPU cores given to the container. Each thread takes about 80 MB of memory. Use 2 on a spinning disk.")
                    Workers("Playlist matching threads", "match_workers", d.matchWorkers, choices) { n -> vm.edit { it.copy(matchWorkers = n) } }
                    FieldNote("Set it to the number of CPU cores given to the container.")
                }
            }
            item(key = "feed") {
                SectionHeader("Release feed", subtitle = "How often the releases of your favorite Deezer artists are checked.")
                GlassCard(Modifier.fillMaxWidth()) {
                    val hours = choices["release_refresh_hours"].orEmpty()
                    ChoiceField("Refresh automatically", hours.map { it to (REFRESH_LABELS[it] ?: "Every $it hours") }, d.releaseRefreshHours ?: 24, { n -> vm.edit { it.copy(releaseRefreshHours = n) } })
                    FieldNote("Needs a connected Deezer account. Refresh on the Releases tab always works.")
                }
            }
            item(key = "files") {
                SectionHeader("Data files", subtitle = "Where the app keeps its state. The defaults are fine unless you moved them.")
                GlassCard(Modifier.fillMaxWidth()) {
                    D2nTextField(d.playlistsBaseDir.orEmpty(), { v -> vm.edit { it.copy(playlistsBaseDir = v) } }, "Generated playlists folder")
                    D2nTextField(d.playlistIdsFile.orEmpty(), { v -> vm.edit { it.copy(playlistIdsFile = v) } }, "Saved playlists")
                    D2nTextField(d.libraryCacheFile.orEmpty(), { v -> vm.edit { it.copy(libraryCacheFile = v) } }, "Library index")
                    D2nTextField(d.previewStateFile.orEmpty(), { v -> vm.edit { it.copy(previewStateFile = v) } }, "Playlist match results", placeholder = "/data/playlist_preview_state.json")
                }
            }
            item(key = "save") {
                val changed = d != answer.settings
                D2nButton(
                    if ("save" in busy) "Saving…" else if (changed) "Save settings" else "Saved",
                    vm::save,
                    Modifier.fillMaxWidth(),
                    enabled = changed && online && "save" !in busy,
                )
            }
        }
    }
}

private fun <T> List<T>.replaced(index: Int, change: (T) -> T): List<T> = mapIndexed { i, x -> if (i == index) change(x) else x }

@Composable
private fun Workers(label: String, key: String, value: Int?, choices: Map<String, List<Int>>, onSelect: (Int) -> Unit) {
    val options = choices[key].orEmpty()
    if (options.isEmpty()) return
    ChoiceField(label, options.map { it to workersLabel(key, it) }, value ?: options.first(), onSelect)
}

/** The library index, the metadata, the repairs and the duplicates. */
@Composable
fun MaintenanceScreen(vm: MaintenanceViewModel, onBack: () -> Unit, onDuplicates: () -> Unit) {
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var ask by remember { mutableStateOf<String?>(null) }
    ScreenScaffold(title = "Maintenance", onBack = onBack) {
        item(key = "index") {
            SectionHeader("Library index")
            GlassCard(Modifier.fillMaxWidth()) {
                Action("Refresh library", "Indexes new and changed files only. Use this after downloads.", "refresh" in busy || !online, vm::refreshLibrary)
                Action("Rebuild from scratch", "Reads every file again. Slow on large libraries.", "rebuild" in busy || !online) { ask = "rebuild" }
                Action("Fix missing metadata", "Finds the tempo and genre your files lack and adds them to their tags. Existing values are kept.", "metadata" in busy || !online) { ask = "metadata" }
                Action("Repair downloads", "Replaces the damaged files saved by versions 1.10.0 to 1.11.0 (noise, skips). Only broken files are downloaded again.", "repair" in busy || !online, vm::repairDownloads)
            }
        }
        item(key = "dedup") {
            SectionHeader("Duplicates", subtitle = "Copies of the same track in your library: keep the best one, move the others aside.")
            GlassCard(Modifier.fillMaxWidth()) {
                Action("Find duplicates", "Scans the library index. Open the report once the scan is done.", "dedup" in busy || !online, vm::scanDuplicates)
                D2nButton("Open the last report", onDuplicates, kind = ButtonKind.Ghost, small = true)
            }
        }
    }
    when (ask) {
        "rebuild" -> ConfirmDialog("Rebuild the index?", "Every file is read again: slow on large libraries.", "Rebuild", vm::rebuildLibrary, { ask = null }, danger = false)
        "metadata" -> ConfirmDialog("Fix missing metadata?", "Adds the missing tempo and genre to your files' tags. Undo is in Made for you.", "Fix", vm::fixMetadata, { ask = null }, danger = false)
    }
}

@Composable
private fun Action(label: String, help: String, disabled: Boolean, onClick: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        D2nButton(label, onClick, Modifier.fillMaxWidth(), kind = ButtonKind.Ghost, enabled = !disabled)
        FieldNote(help)
    }
}

/** What each Reset clears, as the web says it. */
private val RESETS = listOf(
    Triple("library-cache", "Clear library index", "Forget every indexed file. Refresh the library afterwards."),
    Triple("preview-state", "Clear match results", "Playlists will show every track as not checked."),
    Triple("playlists", "Remove all playlists", "Also removes their covers and match results."),
    Triple("dedup-report", "Clear duplicate report", "The next duplicate scan starts fresh."),
    Triple("dedup-choices", "Forget duplicate decisions", "Groups you already reviewed come back."),
    Triple("all", "Reset everything", "Playlists, covers, match results and the library index."),
)

@Composable
fun ResetScreen(vm: MaintenanceViewModel, onBack: () -> Unit) {
    val busy by vm.busy.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var ask by remember { mutableStateOf<Triple<String, String, String>?>(null) }
    ScreenScaffold(title = "Reset data", onBack = onBack) {
        item(key = "warn") { Banner("These cannot be undone. Each one asks first.", BannerTone.Warn) }
        itemsIndexed(RESETS, key = { _, r -> r.first }) { _, reset ->
            ListRow(
                title = reset.second,
                subtitle = reset.third,
                trailing = {
                    D2nButton(reset.second.substringBefore(' '), { ask = reset }, kind = ButtonKind.Danger, small = true, enabled = online && "clear-${reset.first}" !in busy)
                },
            )
        }
    }
    ask?.let { reset ->
        ConfirmDialog(
            title = "${reset.second}?",
            text = "${reset.third} This cannot be undone.",
            confirmLabel = reset.second.substringBefore(' '),
            onConfirm = { vm.clear(reset.first) },
            onDismiss = { ask = null },
            typeToConfirm = if (reset.first == "all" || reset.first == "playlists") "RESET" else null,
        )
    }
}
