package io.github.catchow0.d2n.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.data.Device
import io.github.catchow0.d2n.data.DuplicateFile
import io.github.catchow0.d2n.data.DuplicateGroup
import io.github.catchow0.d2n.ui.common.RefreshWhenTasksEnd
import io.github.catchow0.d2n.ui.common.ago
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.ToggleRow
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.ConfirmDialog
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.formatDuration
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.rememberCopy
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors

@Composable
private fun Note(text: String, color: androidx.compose.ui.graphics.Color = D2nColors.Muted) =
    Text(text, style = MaterialTheme.typography.bodySmall, color = color)

/** A token: hidden until shown, copied as sensitive. */
@Composable
private fun SecretRow(label: String, value: String) {
    var shown by remember { mutableStateOf(false) }
    val copy = rememberCopy()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            if (shown) value else "•".repeat(minOf(24, value.length)),
            style = MaterialTheme.typography.bodyMedium.copy(fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace),
            color = D2nColors.TextSoft,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            D2nButton(if (shown) "Hide" else "Show", { shown = !shown }, kind = ButtonKind.Ghost, small = true)
            D2nButton("Copy", { copy(label, value, true) }, kind = ButtonKind.Ghost, small = true)
        }
    }
}

/** Sign-in and other apps. The device token of this phone is never shown. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SecurityScreen(vm: SecurityViewModel, onBack: () -> Unit) {
    val security by vm.security.collectAsStateWithLifecycle()
    val devices by vm.devices.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val passwordDone by vm.passwordDone.collectAsStateWithLifecycle()
    val recoveryCode by vm.recoveryCode.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var current by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var webhook by remember(security.value?.webhookUrl) { mutableStateOf(security.value?.webhookUrl.orEmpty()) }
    var ask by remember { mutableStateOf<String?>(null) }
    var revoking by remember { mutableStateOf<Device?>(null) }
    LaunchedEffect(passwordDone) {
        current = ""
        new = ""
    }
    ScreenScaffold(title = "Sign-in and other apps", onBack = onBack, refreshing = security.refreshing, onRefresh = vm::refresh) {
        remote(security, onRetry = vm::refresh, skeletons = 3, skeletonHeight = 140.dp) { s ->
            item(key = "account") {
                SectionHeader("Account")
                GlassCard(Modifier.fillMaxWidth()) {
                    if (s.disabled) {
                        Note("Sign-in is turned off on this server (DISABLE_AUTH): a proxy in front of it asks instead.")
                    } else if (s.accountFromEnv) {
                        Note("Signed in as ${s.username}. Set by APP_USERNAME / APP_PASSWORD: change it there.")
                    } else {
                        Note("Signed in as ${s.username}. A new password signs out your browsers and your devices, this phone too.")
                        D2nTextField(current, { current = it }, "Current password", password = true)
                        D2nTextField(new, { new = it }, "New password", password = true, imeAction = ImeAction.Done, supporting = if (new.isNotEmpty() && new.length < 8) "At least 8 characters" else null)
                        D2nButton(
                            if ("password" in busy) "Changing…" else "Change the password",
                            { ask = "password" },
                            small = true,
                            enabled = online && current.isNotEmpty() && new.length >= 8 && "password" !in busy,
                        )
                    }
                }
            }
            if (!s.disabled && !s.accountFromEnv) {
                item(key = "recovery") {
                    SectionHeader("Recovery code", subtitle = "With it, you choose a new password on the sign-in screen if you forget yours. A new one stops the old one; it is shown only once.")
                    GlassCard(Modifier.fillMaxWidth()) {
                        recoveryCode?.let { SecretRow("Recovery code", it) }
                        D2nButton("Make a new recovery code", { ask = "recovery" }, kind = ButtonKind.Ghost, small = true, enabled = online && "recovery" !in busy)
                    }
                }
            }
            item(key = "devices") {
                SectionHeader("Devices", subtitle = "Phones and other apps signed in with your account, each with its own token. Sign one out here if you lose it.")
            }
            if (devices.isEmpty()) item(key = "devices-none") { EmptyState("No device signed in yet.") }
            items(devices, key = { "d-${it.id}" }) { device ->
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(device.name, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                        if (device.current) Chip("This phone", tone = ChipTone.Info)
                    }
                    Note("Signed in ${ago(device.createdAt).ifBlank { "—" }} · last used ${ago(device.lastUsedAt).ifBlank { "never" }}" + (device.lastIp?.let { " from $it" } ?: ""))
                    D2nButton("Sign out", { revoking = device }, kind = ButtonKind.Danger, small = true, enabled = online && "device-${device.id}" !in busy)
                }
            }
            item(key = "token") {
                SectionHeader("API token", subtitle = "Paste it in CatBoard (Settings → Integrations → Deezer to Navidrome). It only reads the release feed and checks the library.")
                GlassCard(Modifier.fillMaxWidth()) {
                    val token = s.token
                    if (token.isNullOrBlank()) Note("No token yet.") else SecretRow("API token", token)
                    if (s.tokenFromEnv) {
                        Note("Set by the API_TOKEN environment variable.")
                    } else {
                        D2nButton(if (token.isNullOrBlank()) "Create a token" else "Make a new token", { if (token.isNullOrBlank()) vm.newToken() else ask = "token" }, kind = ButtonKind.Ghost, small = true, enabled = online && "api-token" !in busy)
                    }
                }
            }
            if (s.profiles.size > 1) {
                item(key = "catboard") {
                    SectionHeader("Profiles CatBoard reads", subtitle = "The API token and the webhook are about the releases of these profiles, as one feed.")
                    GlassCard(Modifier.fillMaxWidth()) {
                        var chosen by remember(s.catboardProfiles) { mutableStateOf(s.catboardProfiles.toSet()) }
                        s.profiles.forEach { profile ->
                            ToggleRow(profile.label, profile.id in chosen, { on -> chosen = if (on) chosen + profile.id else chosen - profile.id })
                        }
                        D2nButton("Save", { vm.setCatboardProfiles(s.profiles.map { it.id }.filter { it in chosen }) }, small = true,
                            enabled = online && chosen.isNotEmpty() && chosen != s.catboardProfiles.toSet() && "catboard" !in busy)
                    }
                }
            }
            item(key = "webhook") {
                SectionHeader("CatBoard webhook", subtitle = "Called when the release feed or the library index is refreshed, so CatBoard updates at once.")
                GlassCard(Modifier.fillMaxWidth()) {
                    D2nTextField(webhook, { webhook = it }, "Webhook URL", placeholder = "http://catboard:3000/api/integrations/deezer/webhook?token=…", keyboardType = KeyboardType.Uri)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        D2nButton("Save", { vm.saveWebhook(webhook) }, small = true, enabled = online && webhook != s.webhookUrl.orEmpty() && "webhook" !in busy)
                        if (!s.webhookUrl.isNullOrBlank()) {
                            D2nButton("Send a test", vm::testWebhook, kind = ButtonKind.Ghost, small = true, enabled = online && "webhook-test" !in busy)
                            D2nButton("Remove", { ask = "webhook" }, kind = ButtonKind.Danger, small = true, enabled = online)
                        }
                    }
                }
            }
        }
    }
    when (ask) {
        "password" -> ConfirmDialog("Change the password?", "Every browser and device is signed out, this phone too: you will sign in again with the new password.", "Change", { vm.changePassword(current, new) }, { ask = null })
        "recovery" -> ConfirmDialog("Make a new recovery code?", "The old one stops working. Write the new one down: it is shown only once.", "Make a new one", vm::newRecoveryCode, { ask = null }, danger = false)
        "token" -> ConfirmDialog("Make a new token?", "The old one stops working: CatBoard will need the new one.", "Make a new one", vm::newToken, { ask = null })
        "webhook" -> ConfirmDialog("Remove the webhook?", "CatBoard is no longer told when something changes.", "Remove", vm::removeWebhook, { ask = null })
    }
    revoking?.let { device ->
        ConfirmDialog(
            "Sign out ${device.name}?",
            if (device.current) "This is this phone: it goes back to the sign-in screen." else "It must sign in again to use this server.",
            "Sign out",
            onConfirm = { vm.revoke(device) },
            onDismiss = { revoking = null },
        )
    }
}

/** How Navidrome sends this app the profile's plays, and rebuilding the history. */
@Composable
fun ListeningStatsScreen(vm: ListeningStatsViewModel, onBack: () -> Unit) {
    val status by vm.status.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val loses by vm.cleanLoses.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    val copy = rememberCopy()
    var pasted by remember { mutableStateOf("") }
    var ask by remember { mutableStateOf<String?>(null) }
    RefreshWhenTasksEnd(vm, vm::refresh)
    ScreenScaffold(title = "Listening stats", onBack = onBack, refreshing = status.refreshing, onRefresh = vm::refresh) {
        remote(status, onRetry = vm::refresh, skeletons = 3, skeletonHeight = 140.dp) { s ->
            val whose = if (s.account.several) " of ${s.account.label}" else ""
            item(key = "history") {
                SectionHeader("History$whose")
                GlassCard(Modifier.fillMaxWidth()) {
                    Note(
                        "${plural(s.plays, "play")}, the last one ${ago(s.lastPlayAt).ifBlank { "never" }}. " +
                            if (s.enrich.pending > 0) "Deezer is still being checked for ${plural(s.enrich.pending, "track")}." else "Every track has been checked on Deezer.",
                        D2nColors.TextSoft,
                    )
                    s.lastImport?.let { report ->
                        Note(
                            "Last rebuild (${if (report.mode == "clean") "Start clean" else "Merge"}), ${ago(report.finishedAt)}: ${plural(report.after, "play")} now, " +
                                "${report.added} added, ${report.updated} updated, ${report.merged} joined.",
                        )
                        report.warnings.forEach { Note(it, D2nColors.Partial) }
                    } ?: Note("The history has not been imported yet.")
                    val nd = s.sources.navidrome
                    Note("Navidrome: ${if (nd.found) "found at" else "not found at"} ${nd.path}" + (nd.user?.let { " (the plays of $it)" } ?: ""), if (nd.found) D2nColors.Muted else D2nColors.Partial)
                    val maloja = s.sources.maloja
                    Note(
                        if (!maloja.used) "Maloja: its plays are ${maloja.owner}'s, so this profile does not read them."
                        else "Maloja: ${if (maloja.found) "found at" else "not found at"} ${maloja.path}",
                    )
                    if (nd.found && nd.user == null) {
                        Banner("This profile has no Navidrome user name yet: add it in Navidrome accounts, so that its plays can be told from the others'.", BannerTone.Warn)
                    }
                }
            }
            item(key = "rebuild") {
                SectionHeader("Rebuild the history")
                GlassCard(Modifier.fillMaxWidth()) {
                    Note("Merge adds what the sources have that is missing here and refreshes track details. It never removes a play.")
                    Note("Start clean wipes the history and rebuilds it from the sources only, so plays they no longer have are lost. It needs Navidrome's database.")
                    Note("Both keep a backup of the current history in the data folder (the last 3).")
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        D2nButton("Rebuild (merge)", vm::merge, small = true, enabled = online && s.sources.canMerge && !s.importRunning && "import" !in busy)
                        D2nButton("Start clean", vm::askClean, kind = ButtonKind.Danger, small = true, enabled = online && s.sources.canClean && !s.importRunning && "preview" !in busy)
                    }
                    if (!s.sources.canMerge) Note("Mount Navidrome's${if (s.sources.maloja.used) " or Maloja's" else ""} database to import this history.")
                    if (s.importRunning) Note("A rebuild is running: follow it in Activity.")
                }
            }
            item(key = "link") {
                SectionHeader("Point Navidrome at this app", subtitle = "Set this in Navidrome and restart it, once for all its users.")
                GlassCard(Modifier.fillMaxWidth()) {
                    val setting = "ND_LISTENBRAINZ_BASEURL=${s.baseUrlHint}"
                    Text(setting, style = MaterialTheme.typography.bodySmall.copy(fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace), color = D2nColors.Mint)
                    D2nButton("Copy", { copy("Navidrome setting", setting, false) }, kind = ButtonKind.Ghost, small = true)
                    Note("Change the host if Navidrome reaches this app under another name.")
                }
            }
            item(key = "token") {
                SectionHeader("Token for ${if (s.account.several) s.account.label else "Navidrome"}")
                GlassCard(Modifier.fillMaxWidth()) {
                    val user = s.account.username.ifBlank { null }
                    Note("Then, ${user?.let { "signed in to Navidrome as $it" } ?: "signed in to Navidrome as this profile's user"}, open your personal settings, turn on ListenBrainz and paste this token.")
                    val token = s.token
                    if (token.isNullOrBlank()) Note("No token yet: Navidrome cannot send plays until you create one.") else SecretRow("Token for Navidrome", token)
                    if (s.tokenFromEnv) {
                        Note("Set by the ${s.tokenEnv} environment variable.")
                    } else {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            D2nButton(if (token.isNullOrBlank()) "Create a token" else "Make a new token", { if (token.isNullOrBlank()) vm.newToken() else ask = "new" }, kind = ButtonKind.Ghost, small = true, enabled = online && "token" !in busy)
                            if (!token.isNullOrBlank()) D2nButton("Remove the token", { ask = "remove" }, kind = ButtonKind.Danger, small = true, enabled = online && "token" !in busy)
                        }
                        D2nTextField(pasted, { pasted = it.trim() }, "Or paste a token you already use", imeAction = ImeAction.Done)
                        D2nButton("Use this token", { vm.useToken(pasted) }, kind = ButtonKind.Ghost, small = true, enabled = online && pasted.length >= 8 && "token" !in busy)
                    }
                }
            }
        }
    }
    loses?.let { count ->
        ConfirmDialog(
            "Start clean?",
            "The history is rebuilt from the sources only: ${plural(count, "play")} they no longer have will be lost. A backup is kept.",
            "Start clean",
            onConfirm = vm::clean,
            onDismiss = vm::cancelClean,
        )
    }
    when (ask) {
        "new" -> ConfirmDialog("Make a new token?", "Navidrome must be linked again with the new one.", "Make a new one", vm::newToken, { ask = null })
        "remove" -> ConfirmDialog("Remove the token?", "Navidrome stops recording your plays here.", "Remove", vm::removeToken, { ask = null })
    }
}

/** The last duplicate report: checked files are kept, the others moved aside or deleted. */
@Composable
fun DuplicatesScreen(vm: DuplicatesViewModel, onBack: () -> Unit) {
    val report by vm.report.collectAsStateWithLifecycle()
    val keep by vm.keep.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val none by vm.none.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var ask by remember { mutableStateOf<String?>(null) }
    RefreshWhenTasksEnd(vm, vm::refresh)
    val groups = report.value?.groups.orEmpty()
    // Read from the states here, so the count follows each checkbox: the
    // confirmation says how many files go.
    val dropped = remember(groups, keep) { droppedCount(groups, keep) }
    ScreenScaffold(
        title = "Duplicates",
        onBack = onBack,
        refreshing = report.refreshing,
        onRefresh = vm::refresh,
        bottomBar = if (none || groups.isEmpty()) null else {
            {
                Surface(color = D2nColors.Ink2.copy(alpha = 0.96f)) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text("${plural(dropped, "file")} not kept", Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
                        D2nButton("Quarantine", { ask = "quarantine" }, small = true, enabled = online && dropped > 0 && "apply" !in busy)
                        D2nButton("Delete", { ask = "delete" }, kind = ButtonKind.Danger, small = true, enabled = online && dropped > 0 && "apply" !in busy)
                    }
                }
            }
        },
    ) {
        remote(report, onRetry = vm::refresh, skeletons = 4, skeletonHeight = 120.dp) { r ->
            if (none) {
                item(key = "no-report") {
                    EmptyState(
                        if ("dedup" in busy) "Looking for duplicates…" else "No scan yet. Find duplicates looks through the library index; the report opens here when it is done.",
                        actionLabel = "Find duplicates".takeIf { online && "dedup" !in busy },
                        onAction = vm::scan,
                    )
                }
                return@remote
            }
            item(key = "summary") {
                val reviewed = r.totalGroupCount - r.groupCount
                Text(
                    listOfNotNull(
                        "${plural(r.groupCount, "group")} to review",
                        plural(r.duplicateFileCount, "duplicate file"),
                        if (reviewed > 0) "$reviewed already reviewed" else null,
                    ).joinToString(", ") + ". Checked files are kept.",
                    style = MaterialTheme.typography.bodySmall,
                    color = D2nColors.Muted,
                )
            }
            if (r.groups.isEmpty()) {
                item(key = "none") { EmptyState("No duplicates left to review.") }
                return@remote
            }
            item(key = "presets") {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    D2nButton("Keep the best copies", vm::keepBest, kind = ButtonKind.Ghost, small = true)
                    D2nButton("Keep everything", vm::keepAll, kind = ButtonKind.Ghost, small = true)
                }
            }
            r.groups.groupBy { it.identity.artist to it.identity.album }.forEach { (album, groups) ->
                item(key = "a-${album.first}-${album.second}") {
                    SectionHeader("${album.first.ifBlank { "Unknown artist" }}, ${album.second.ifBlank { "Unknown album" }}")
                }
                items(groups, key = { it.groupId }) { group ->
                    GlassCard(Modifier.fillMaxWidth()) {
                        Text(group.identity.baseTitle.ifBlank { "Unknown" }, style = MaterialTheme.typography.titleSmall)
                        group.entries.forEach { file ->
                            FileChoice(file, kept = file.path in keep[group.groupId].orEmpty(), best = file.path == group.keeper.path) { vm.toggle(group.groupId, file.path) }
                        }
                    }
                }
            }
        }
    }
    when (ask) {
        "quarantine" -> ConfirmDialog("Move ${plural(dropped, "file")} to quarantine?", "They are moved out of your library into the quarantine folder, from where they can be put back.", "Move", { vm.apply("quarantine") }, { ask = null }, danger = false)
        "delete" -> ConfirmDialog("Delete ${plural(dropped, "file")} for good?", "They are deleted from the disk. This cannot be undone.", "Delete", { vm.apply("delete") }, { ask = null }, typeToConfirm = "DELETE")
    }
}

@Composable
private fun FileChoice(file: DuplicateFile, kept: Boolean, best: Boolean, onToggle: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().toggleable(value = kept, role = Role.Checkbox, onValueChange = { onToggle() }),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Checkbox(kept, onCheckedChange = null, colors = CheckboxDefaults.colors(checkedColor = D2nColors.Violet, uncheckedColor = D2nColors.LineStrong))
        Column(Modifier.weight(1f)) {
            Text(
                (file.trackNumber?.let { "%02d. ".format(it) } ?: "") + (file.tagTitle ?: file.parsedTitle ?: file.path.substringAfterLast('/')),
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(shortPath(file.path), style = MaterialTheme.typography.bodySmall, color = D2nColors.Faint, maxLines = 2)
            Text(
                listOf(formatDuration(file.duration), file.size?.let { "%.1f MB".format(it / 1048576.0) }.orEmpty(), "quality %.1f".format(file.quality)).filter(String::isNotBlank).joinToString(", "),
                style = MaterialTheme.typography.bodySmall,
                color = D2nColors.Muted,
            )
        }
        Chip(if (best) "Best copy" else "Duplicate", tone = if (best) ChipTone.Ok else ChipTone.Miss)
    }
}

/**
 * The end of a path, where copies differ: its folder and file name. The
 * folders above are the same for every copy and would push it out of view.
 */
internal fun shortPath(path: String, keep: Int = 3): String {
    val parts = path.split('/', '\\').filter(String::isNotEmpty)
    return if (parts.size <= keep) path else "…/" + parts.takeLast(keep).joinToString("/")
}

/** How many files the choices would move or delete: those not checked. */
internal fun droppedCount(groups: List<DuplicateGroup>, keep: Map<String, Set<String>>): Int =
    groups.sumOf { g -> g.entries.count { it.path !in keep[g.groupId].orEmpty() } }
