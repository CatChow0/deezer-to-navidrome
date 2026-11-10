package io.github.catchow0.d2n.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.ConnectionTest
import io.github.catchow0.d2n.data.DeezerProfile
import io.github.catchow0.d2n.data.DeezerProfilesAnswer
import io.github.catchow0.d2n.data.NavidromeProfile
import io.github.catchow0.d2n.data.NavidromeProfileFields
import io.github.catchow0.d2n.ui.common.ago
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.ChoiceField
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.ConfirmDialog
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.D2nTextField
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.IconAction
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import java.util.Locale

@Composable
private fun Note(text: String, color: androidx.compose.ui.graphics.Color = D2nColors.Muted) =
    Text(text, style = MaterialTheme.typography.bodySmall, color = color)

/** What a connection test found, as the web says it. */
private fun testLine(test: ConnectionTest): String {
    if (!test.ok) return test.error ?: "The test failed."
    val facts = listOfNotNull(
        test.serverVersion?.let { "Navidrome $it" },
        when (test.admin) { true -> "admin"; false -> "not an admin"; null -> null },
        test.libraries.map { it.name }.filter(String::isNotBlank).takeIf { it.isNotEmpty() }?.let { "sees ${it.joinToString(", ")}" },
        if (test.apiKeys) "API keys accepted" else "no API keys, so the password is used",
    )
    return "Connected: ${facts.joinToString(" · ")}." + (test.navidromeUser?.let { " Found in Navidrome's database as $it." } ?: "")
}

private fun syncLine(profile: NavidromeProfile): String? {
    val sync = profile.sync ?: return null
    sync.error?.takeIf(String::isNotBlank)?.let { return "Last sync with Navidrome failed: $it" }
    val parts = mutableListOf("Synced with Navidrome ${ago(sync.at)}")
    if (sync.removed.isNotEmpty()) parts += "${plural(sync.removed.size, "playlist")} removed, deleted in Navidrome (${sync.removed.joinToString(", ")})"
    if (sync.renamed > 0) parts += "${plural(sync.renamed, "playlist")} renamed there"
    if (sync.handmade > 0) parts += "${sync.handmade} made by hand"
    return parts.joinToString(" · ")
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun NavidromeAccountsScreen(vm: NavidromeAccountsViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val deezer by vm.deezer.collectAsStateWithLifecycle()
    val tests by vm.tests.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val switch by vm.switch.collectAsStateWithLifecycle()
    val formDone by vm.formDone.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var editing by remember { mutableStateOf<NavidromeProfile?>(null) }
    var adding by remember { mutableStateOf(false) }
    var removing by remember { mutableStateOf<NavidromeProfile?>(null) }
    LaunchedEffect(formDone) {
        editing = null
        adding = false
    }

    ScreenScaffold(
        title = "Navidrome accounts",
        onBack = onBack,
        actions = { IconAction(R.drawable.ic_add, "Add an account", { adding = true }, enabled = online) },
        refreshing = state.refreshing,
        onRefresh = vm::refresh,
    ) {
        item(key = "lead") {
            Note("One per Navidrome user this app works for. The library, the downloads and the folders stay shared; each browser or phone chooses its account at the top.")
        }
        remote(state, onRetry = vm::refresh, skeletons = 2, skeletonHeight = 160.dp) { answer ->
            items(answer.accounts, key = { it.id }) { profile ->
                GlassCard(Modifier.fillMaxWidth()) {
                    Text(profile.label, style = MaterialTheme.typography.titleMedium)
                    Note(listOf(profile.username, profile.url).filter(String::isNotBlank).joinToString(" · ").ifBlank { "No address or user yet" })
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (profile.isDefault) Chip("Default", tone = ChipTone.Ok)
                        val test = profile.lastTest
                        when {
                            !profile.complete -> Chip("Address or password missing", tone = ChipTone.Partial)
                            test == null -> Chip("Not tested yet")
                            test.ok -> Chip("Connected", tone = ChipTone.Ok)
                            else -> Chip("Connection failed", tone = ChipTone.Miss)
                        }
                        Chip(if (profile.publishMode == "m3u8") "Playlists as .m3u8 files" else "Playlists as this user", tone = ChipTone.Info)
                        deezerLabel(deezer, profile.deezerAccount)?.let { Chip("Deezer: $it") }
                    }
                    if (profile.legacy && !profile.complete) {
                        Note("Made from your install: it keeps working as before. Add its address and password to get ready for per-user playlists.")
                    }
                    syncLine(profile)?.let { Note(it, if (profile.sync?.error != null) D2nColors.Partial else D2nColors.Muted) }
                    profile.sync?.warning?.takeIf(String::isNotBlank)?.let { Note(it, D2nColors.Partial) }
                    tests[profile.id]?.let { Banner(testLine(it), if (it.ok) BannerTone.Info else BannerTone.Error) }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (profile.publishMode == "m3u8" && profile.complete && profile.lastTest?.ok == true) {
                            D2nButton("Publish as this user…", { vm.previewSwitch(profile.id) }, small = true, enabled = online && "switch-${profile.id}" !in busy)
                        }
                        if (profile.complete) {
                            D2nButton(if ("test-${profile.id}" in busy) "Testing…" else "Test", { vm.test(profile.id) }, kind = ButtonKind.Ghost, small = true, enabled = online && "test-${profile.id}" !in busy)
                        }
                        D2nButton("Edit", { editing = profile }, kind = ButtonKind.Ghost, small = true, enabled = online)
                        if (!profile.isDefault) D2nButton("Make default", { vm.makeDefault(profile.id) }, kind = ButtonKind.Ghost, small = true, enabled = online)
                        if (answer.accounts.size > 1) D2nButton("Remove", { removing = profile }, kind = ButtonKind.Danger, small = true, enabled = online)
                    }
                }
            }
            item(key = "footer") {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Note(
                        if (answer.encryption.source == "env") "Passwords and API keys are encrypted with your D2N_ENCRYPTION_KEY."
                        else "Passwords and API keys are encrypted with a key kept in /data/encryption.key. Set D2N_ENCRYPTION_KEY to keep the key out of the data folder.",
                    )
                    Note(
                        if (answer.navidromeDb.mounted) "Navidrome's database is mounted: ${plural(answer.navidromeDb.users.size, "user")} found (${answer.navidromeDb.users.joinToString(", ")})."
                        else "Navidrome's database is not mounted at /import/navidrome: telling each user's plays and stars apart will need it.",
                    )
                }
            }
        }
    }

    if (adding || editing != null) {
        NavidromeForm(
            profile = editing,
            deezer = deezer,
            test = tests["form"],
            busy = "save" in busy,
            testing = "test-form" in busy,
            onTest = { vm.testForm(editing?.id, it) },
            onSave = { vm.save(editing?.id, it) },
            onDismiss = {
                editing = null
                adding = false
            },
        )
    }
    removing?.let { profile ->
        ConfirmDialog(
            "Remove ${profile.label}?",
            "Its playlists stay for the other profiles they go to. Its settings and history in this app are removed.",
            "Remove",
            onConfirm = { vm.delete(profile.id, profile.label) },
            onDismiss = { removing = null },
        )
    }
    switch?.let { (id, preview) ->
        val profile = state.value?.accounts?.firstOrNull { it.id == id }
        if (!preview.ok) {
            ConfirmDialog("Cannot publish as this user", preview.problems.joinToString(" "), "OK", onConfirm = {}, onDismiss = vm::closeSwitch, danger = false)
        } else {
            val lines = buildList {
                add("The ${plural(preview.playlists, "playlist")} of ${profile?.label} become private playlists of ${profile?.username}, kept up to date through Navidrome's API.")
                add("${plural(preview.files, ".m3u8 file")} written by this app are removed from the playlists folder.")
                if (preview.old.isNotEmpty()) add("The copies Navidrome imported from them are removed from Navidrome: ${preview.old.joinToString(", ") { it.name }}.")
                if (!preview.database) add("Navidrome's database is not mounted: remove the old copies in Navidrome afterwards.")
                if (!preview.canRemoveOld) add("This user is not an admin and does not own the old copies: remove them in Navidrome afterwards.")
                add("If Navidrome refuses a playlist, what was made is undone and nothing changes.")
            }
            ConfirmDialog("Publish as ${profile?.username}?", lines.joinToString("\n\n"), "Switch now", onConfirm = { vm.switch(id, profile?.label.orEmpty()) }, onDismiss = vm::closeSwitch, danger = false)
        }
    }
}

private fun deezerLabel(deezer: DeezerProfilesAnswer?, id: String): String? {
    val accounts = deezer?.accounts.orEmpty()
    if (id.isBlank()) return accounts.firstOrNull { it.isDefault }?.let { "${it.label} (default)" }
    return accounts.firstOrNull { it.id == id }?.label
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NavidromeForm(
    profile: NavidromeProfile?,
    deezer: DeezerProfilesAnswer?,
    test: ConnectionTest?,
    busy: Boolean,
    testing: Boolean,
    onTest: (NavidromeProfileFields) -> Unit,
    onSave: (NavidromeProfileFields) -> Unit,
    onDismiss: () -> Unit,
) {
    var label by remember { mutableStateOf(profile?.label.orEmpty()) }
    var url by remember { mutableStateOf(profile?.url.orEmpty()) }
    var username by remember { mutableStateOf(profile?.username.orEmpty()) }
    var authType by remember { mutableStateOf(profile?.authType ?: "password") }
    var secret by remember { mutableStateOf("") }
    var deezerAccount by remember { mutableStateOf(profile?.deezerAccount.orEmpty()) }
    val fields = NavidromeProfileFields(label.trim(), url.trim(), username.trim(), authType, secret.ifEmpty { null }, deezerAccount)
    val canSave = url.isNotBlank() && username.isNotBlank() && (profile != null || secret.isNotEmpty())
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = D2nColors.Ink2,
        contentColor = D2nColors.Text,
    ) {
        Column(
            Modifier.fillMaxWidth().navigationBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(if (profile != null) "Edit ${profile.label}" else "New Navidrome account", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            D2nTextField(label, { label = it.take(40) }, "Name", placeholder = "Shown in the picker, e.g. Alice")
            D2nTextField(url, { url = it }, "Navidrome address", placeholder = "http://navidrome:4533", keyboardType = KeyboardType.Uri, supporting = "The address this server reaches Navidrome at.")
            D2nTextField(username, { username = it }, "Navidrome user name")
            ChoiceField("Sign in with", listOf("password" to "Password", "apikey" to "API key (if your Navidrome accepts them)"), authType, { authType = it })
            D2nTextField(
                secret,
                { secret = it },
                if (authType == "apikey") "API key" else "Password",
                password = true,
                supporting = (if (profile?.hasSecret == true) "One is saved: leave this empty to keep it. " else "") +
                    "Kept encrypted on the server. Never shown again, and never written in a log.",
            )
            val deezerAccounts = deezer?.accounts.orEmpty()
            if (deezerAccounts.isNotEmpty()) {
                val fallback = deezerAccounts.firstOrNull { it.isDefault }
                ChoiceField(
                    "Deezer account",
                    listOf("" to "Default" + (fallback?.let { " (${it.label})" } ?: "")) + deezerAccounts.map { it.id to it.label },
                    deezerAccount,
                    { deezerAccount = it },
                )
                Note("Its releases and Deezer mixes. The downloads always use the account marked for them.")
            }
            test?.let { Banner(testLine(it), if (it.ok) BannerTone.Info else BannerTone.Error) }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                D2nButton(if (testing) "Testing…" else "Test the connection", { onTest(fields) }, kind = ButtonKind.Ghost, small = true, enabled = !testing && url.isNotBlank() && username.isNotBlank())
                D2nButton(if (busy) "Saving…" else if (profile != null) "Save" else "Add the account", { onSave(fields) }, small = true, enabled = canSave && !busy)
            }
        }
    }
}

private val FORMAT_LABEL = mapOf("FLAC" to "FLAC", "MP3_320" to "MP3 320", "MP3_128" to "MP3 128")

private fun countryName(code: String): String = runCatching { Locale.Builder().setRegion(code).build().getDisplayCountry(Locale.ENGLISH) }.getOrNull()?.ifBlank { null } ?: code

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DeezerAccountsScreen(vm: DeezerAccountsViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val formDone by vm.formDone.collectAsStateWithLifecycle()
    val online = LocalOnline.current
    var editing by remember { mutableStateOf<DeezerProfile?>(null) }
    var adding by remember { mutableStateOf(false) }
    var removing by remember { mutableStateOf<DeezerProfile?>(null) }
    LaunchedEffect(formDone) {
        editing = null
        adding = false
    }
    ScreenScaffold(
        title = "Deezer accounts",
        onBack = onBack,
        actions = { IconAction(R.drawable.ic_add, "Add an account", { adding = true }, enabled = online) },
        refreshing = state.refreshing,
        onRefresh = vm::refresh,
    ) {
        item(key = "lead") {
            Note("Each Navidrome profile follows the releases and mixes of one of them, the default one unless it chose another. The one marked for the downloads fetches the files for everyone.")
        }
        remote(state, onRetry = vm::refresh, skeletons = 2, skeletonHeight = 140.dp) { answer ->
            item(key = "downloads") {
                val downloads = answer.downloads
                Banner(
                    when {
                        downloads?.account == null -> "Add a Deezer account to download what is missing."
                        !downloads.connected -> "The downloads use ${downloads.label}, which cannot sign in: ${downloads.error ?: "check its ARL"}."
                        else -> "The downloads use ${downloads.label}, in ${FORMAT_LABEL[downloads.format] ?: downloads.format ?: "the best quality it allows"}, for every profile." +
                            if (downloads.premium) "" else " A free account only downloads MP3 128: mark a premium one with Use for download for FLAC."
                    },
                    if (downloads?.connected == true) BannerTone.Info else BannerTone.Warn,
                )
            }
            if (answer.accounts.isEmpty()) {
                item(key = "none") { Note("No Deezer account yet. Add one with its ARL.") }
            }
            items(answer.accounts, key = { it.id }) { account ->
                GlassCard(Modifier.fillMaxWidth()) {
                    Text(account.label, style = MaterialTheme.typography.titleMedium)
                    if (account.name.isNotBlank()) Note("Signed in as ${account.name}")
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (account.isDefault) Chip("Default", tone = ChipTone.Ok)
                        if (account.isDownload) Chip("Downloads", tone = ChipTone.Partial)
                        when {
                            account.error.isNotBlank() -> Chip("Cannot sign in", tone = ChipTone.Miss)
                            account.checkedAt > 0 -> Chip(if (account.premium) "Premium account" else "Free account", tone = if (account.premium) ChipTone.Ok else ChipTone.Idle)
                        }
                        if (account.country.isNotBlank()) Chip(countryName(account.country), tone = ChipTone.Info)
                    }
                    if (account.fromEnv.isNotBlank()) Note("Set by the ${account.fromEnv} environment variable: change the ARL there.")
                    if (account.error.isNotBlank()) Note(account.error, D2nColors.Partial)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        D2nButton(if ("check-${account.id}" in busy) "Checking…" else "Check", { vm.check(account.id) }, kind = ButtonKind.Ghost, small = true, enabled = online && "check-${account.id}" !in busy)
                        D2nButton("Edit", { editing = account }, kind = ButtonKind.Ghost, small = true, enabled = online)
                        if (!account.isDefault) D2nButton("Make default", { vm.makeDefault(account.id) }, kind = ButtonKind.Ghost, small = true, enabled = online)
                        if (!account.isDownload) D2nButton("Use for download", { vm.useForDownloads(account.id) }, kind = ButtonKind.Ghost, small = true, enabled = online)
                        if (answer.accounts.size > 1) D2nButton("Remove", { removing = account }, kind = ButtonKind.Danger, small = true, enabled = online)
                    }
                }
            }
        }
    }
    if (adding || editing != null) {
        DeezerForm(editing, "save" in busy, onSave = { label, arl -> vm.save(editing?.id, label, arl) }, onDismiss = {
            editing = null
            adding = false
        })
    }
    removing?.let { account ->
        ConfirmDialog(
            "Remove ${account.label}?",
            "Profiles following it go back to the default account. Its ARL is deleted from the server.",
            "Remove",
            onConfirm = { vm.delete(account.id, account.label) },
            onDismiss = { removing = null },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DeezerForm(account: DeezerProfile?, busy: Boolean, onSave: (String, String) -> Unit, onDismiss: () -> Unit) {
    var label by remember { mutableStateOf(account?.label.orEmpty()) }
    var arl by remember { mutableStateOf("") }
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
            Text(if (account != null) "Edit ${account.label}" else "New Deezer account", Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            D2nTextField(label, { label = it.take(40) }, "Name", placeholder = "Shown in the lists, e.g. Alice")
            if (account?.fromEnv?.isNotBlank() != true) {
                D2nTextField(
                    arl,
                    { arl = it },
                    "ARL",
                    password = true,
                    placeholder = if (account == null) "Paste the arl cookie value" else null,
                    supporting = (if (account != null) "One is saved: leave this empty to keep it. " else "") + "Signed in to deezer.com in a browser: developer tools → Application (Storage in Firefox) → Cookies → arl. It stays on the server, encrypted.",
                )
            }
            D2nButton(
                if (busy) "Signing in to Deezer…" else if (account != null) "Save" else "Add the account",
                { onSave(label, arl) },
                Modifier.fillMaxWidth(),
                enabled = !busy && (account != null || arl.isNotBlank()),
            )
        }
    }
}
