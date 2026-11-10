package io.github.catchow0.d2n.ui.settings

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.DeezerProfileFields
import io.github.catchow0.d2n.data.DeezerProfilesAnswer
import io.github.catchow0.d2n.data.Device
import io.github.catchow0.d2n.data.DuplicateApply
import io.github.catchow0.d2n.data.DuplicateDecision
import io.github.catchow0.d2n.data.DuplicateReport
import io.github.catchow0.d2n.data.ImportRequest
import io.github.catchow0.d2n.data.NavidromeProfileFields
import io.github.catchow0.d2n.data.NavidromeProfilesAnswer
import io.github.catchow0.d2n.data.PasswordRequest
import io.github.catchow0.d2n.data.SecurityAnswer
import io.github.catchow0.d2n.data.SettingsAnswer
import io.github.catchow0.d2n.data.SettingsChange
import io.github.catchow0.d2n.data.SettingsValues
import io.github.catchow0.d2n.data.StatsStatus
import io.github.catchow0.d2n.data.StatsTokenRequest
import io.github.catchow0.d2n.data.SwitchPreview
import io.github.catchow0.d2n.data.ConnectionTest
import io.github.catchow0.d2n.data.WebhookRequest
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.plural
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Music folders, Navidrome paths, downloads, performance, the release feed and data files. */
class MusicSettingsViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _saved = MutableStateFlow(Remote<SettingsAnswer>())
    val saved: StateFlow<Remote<SettingsAnswer>> = _saved

    private val _draft = MutableStateFlow<SettingsValues?>(null)

    /** What the form holds, saved or not. */
    val draft: StateFlow<SettingsValues?> = _draft

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _saved.fill { settings() }
            _saved.value.value?.let { _draft.value = it.settings }
        }
    }

    fun edit(change: (SettingsValues) -> SettingsValues) {
        _draft.update { it?.let(change) }
    }

    val dirty: Boolean get() = _draft.value != _saved.value.value?.settings

    fun save() {
        val d = _draft.value ?: return
        act(
            "save",
            {
                saveSettings(
                    SettingsChange(
                        scanDirs = d.scanDirs.map(String::trim).filter(String::isNotEmpty),
                        mappings = d.mappings.filter { it.host.isNotBlank() && it.navidrome.isNotBlank() },
                        deezerDlDir = d.deezerDlDir.orEmpty(),
                        playlistsBaseDir = d.playlistsBaseDir.orEmpty(),
                        playlistIdsFile = d.playlistIdsFile.orEmpty(),
                        libraryCacheFile = d.libraryCacheFile.orEmpty(),
                        previewStateFile = d.previewStateFile.orEmpty(),
                        libraryWorkersPerDir = d.libraryWorkersPerDir,
                        matchWorkers = d.matchWorkers,
                        downloadWorkers = d.downloadWorkers,
                        metadataWorkers = d.metadataWorkers,
                        releaseRefreshHours = d.releaseRefreshHours,
                    ),
                )
            },
            done = { Notice("Settings saved") },
            after = { answer ->
                _saved.value = Remote(answer, loading = false)
                _draft.value = answer.settings
            },
        )
    }
}

/** The Navidrome accounts: the profiles. A password is sent, never read back. */
class NavidromeAccountsViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _state = MutableStateFlow(Remote<NavidromeProfilesAnswer>())
    val state: StateFlow<Remote<NavidromeProfilesAnswer>> = _state

    private val _deezer = MutableStateFlow<DeezerProfilesAnswer?>(null)

    /** The Deezer accounts a profile can follow. */
    val deezer: StateFlow<DeezerProfilesAnswer?> = _deezer

    private val _tests = MutableStateFlow<Map<String, ConnectionTest>>(emptyMap())

    /** The last test of each account, and of the form ("form"). */
    val tests: StateFlow<Map<String, ConnectionTest>> = _tests

    private val _switch = MutableStateFlow<Pair<String, SwitchPreview>?>(null)
    val switch: StateFlow<Pair<String, SwitchPreview>?> = _switch

    private val _formDone = MutableStateFlow(0)

    /** Counts the saves: the form closes when it moves. */
    val formDone: StateFlow<Int> = _formDone

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            coroutineScope {
                launch { _state.fill { navidromeProfiles() } }
                launch {
                    _deezer.value = try {
                        call { deezerProfiles() }
                    } catch (e: ApiFailure) {
                        null
                    }
                }
            }
        }
    }

    private fun keep(answer: NavidromeProfilesAnswer) {
        _state.value = Remote(answer, loading = false)
    }

    fun save(id: String?, fields: NavidromeProfileFields) {
        act(
            "save",
            { if (id == null) createNavidromeProfile(fields) else updateNavidromeProfile(id, fields) },
            done = { Notice(if (id == null) "Account added" else "Account saved") },
            after = { answer ->
                keep(answer)
                _formDone.update { it + 1 }
                (id ?: answer.created)?.let(::test)
            },
        )
    }

    fun testForm(id: String?, fields: NavidromeProfileFields) {
        act("test-form", { testNavidromeFields(fields.copy(id = id.orEmpty())) }, after = { answer -> _tests.update { it + ("form" to answer.test) } })
    }

    fun test(id: String) {
        act("test-$id", { testNavidromeProfile(id) }, after = { answer ->
            keep(answer)
            answer.test?.let { test -> _tests.update { it + (id to test) } }
        })
    }

    fun makeDefault(id: String) {
        act("default-$id", { defaultNavidromeProfile(id) }, after = ::keep)
    }

    fun delete(id: String, label: String) {
        act("delete-$id", { deleteNavidromeProfile(id) }, done = { Notice("$label removed") }, after = ::keep)
    }

    fun previewSwitch(id: String) {
        act("switch-$id", { switchPreview(id) }, after = { _switch.value = id to it.preview })
    }

    fun closeSwitch() {
        _switch.value = null
    }

    fun switch(id: String, label: String) {
        _switch.value = null
        act("switch-$id", { switchToUser(id) }, done = { Notice("Publishing the playlists of $label as its user", it.taskId) }, after = { taskStarted(::refresh) })
    }
}

/** The Deezer accounts. An ARL is sent, never read back. */
class DeezerAccountsViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _state = MutableStateFlow(Remote<DeezerProfilesAnswer>())
    val state: StateFlow<Remote<DeezerProfilesAnswer>> = _state

    private val _formDone = MutableStateFlow(0)
    val formDone: StateFlow<Int> = _formDone

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { _state.fill { deezerProfiles() } }
    }

    /** Some answers leave out the downloads' account: the last one stays. */
    private fun keep(answer: DeezerProfilesAnswer) {
        _state.update { old -> Remote(answer.copy(downloads = answer.downloads ?: old.value?.downloads), loading = false) }
    }

    fun save(id: String?, label: String, arl: String) {
        val fields = DeezerProfileFields(label.trim(), arl.trim().ifEmpty { null })
        act(
            "save",
            { if (id == null) createDeezerProfile(fields) else updateDeezerProfile(id, fields) },
            done = { Notice(if (id == null) "Account added" else "Account saved") },
            after = {
                keep(it)
                _formDone.update { n -> n + 1 }
            },
        )
    }

    fun check(id: String) = act("check-$id", { checkDeezerProfile(id) }, done = { Notice("Checked") }, after = ::keep)

    fun makeDefault(id: String) = act("default-$id", { defaultDeezerProfile(id) }, after = ::keep)

    fun useForDownloads(id: String) = act("download-$id", { downloadDeezerProfile(id) }, done = { Notice("Downloads now use this account") }, after = ::keep)

    fun delete(id: String, label: String) = act("delete-$id", { deleteDeezerProfile(id) }, done = { Notice("$label removed") }, after = ::keep)
}

/** How Navidrome sends this app the profile's plays, and rebuilding the history. */
class ListeningStatsViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _status = MutableStateFlow(Remote<StatsStatus>())
    val status: StateFlow<Remote<StatsStatus>> = _status

    private val _cleanLoses = MutableStateFlow<Int?>(null)

    /** Start clean asked: how many plays it would lose, for the confirmation. */
    val cleanLoses: StateFlow<Int?> = _cleanLoses

    init {
        followProfile { _status.fill { statsStatus() } }
    }

    fun refresh() {
        viewModelScope.launch { _status.fill { statsStatus() } }
    }

    fun merge() {
        act("import", { importStats(ImportRequest("merge")) }, done = { Notice("Rebuilding the history (merge)", it.taskId) }, after = { taskStarted(::refresh) })
    }

    fun askClean() {
        act("preview", { previewStatsImport() }, after = { _cleanLoses.value = it.removed })
    }

    fun cancelClean() {
        _cleanLoses.value = null
    }

    fun clean() {
        _cleanLoses.value = null
        act("import", { importStats(ImportRequest("clean")) }, done = { Notice("Rebuilding the history (start clean)", it.taskId) }, after = { taskStarted(::refresh) })
    }

    fun newToken() {
        act("token", { setStatsToken(StatsTokenRequest()) }, done = { Notice("New token: paste it in Navidrome") }, after = { refresh() })
    }

    fun useToken(token: String) {
        act("token", { setStatsToken(StatsTokenRequest(token.trim())) }, done = { Notice("Token saved") }, after = { refresh() })
    }

    fun removeToken() {
        act("token", { deleteStatsToken() }, done = { Notice("Token removed: Navidrome stops recording") }, after = { refresh() })
    }
}

/** Sign-in and other apps: the password, the API token, the webhook and the devices. */
class SecurityViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _security = MutableStateFlow(Remote<SecurityAnswer>())
    val security: StateFlow<Remote<SecurityAnswer>> = _security

    private val _devices = MutableStateFlow<List<Device>>(emptyList())
    val devices: StateFlow<List<Device>> = _devices

    private val _passwordDone = MutableStateFlow(0)
    val passwordDone: StateFlow<Int> = _passwordDone

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            coroutineScope {
                launch { _security.fill { security() } }
                launch {
                    try {
                        _devices.value = call { devices() }.devices
                    } catch (e: ApiFailure) {
                        // The list stays as it was.
                    }
                }
            }
        }
    }

    /** A new password signs every device out, this phone too: it comes back to sign-in. */
    fun changePassword(current: String, new: String) {
        act("password", { changePassword(PasswordRequest(current, new)) }, done = { Notice("Password changed: your devices must sign in again") }, after = { _passwordDone.update { it + 1 } })
    }

    fun newToken() {
        act("api-token", { newApiToken() }, done = { Notice("New token created: update it in CatBoard") }, after = { answer ->
            _security.update { it.copy(value = it.value?.copy(token = answer.token)) }
        })
    }

    fun saveWebhook(url: String) {
        act("webhook", { setWebhook(WebhookRequest(url.trim())) }, done = { Notice(if (url.isBlank()) "Webhook removed" else "Webhook saved") }, after = { answer ->
            _security.update { it.copy(value = it.value?.copy(webhookUrl = answer.webhookUrl)) }
        })
    }

    fun testWebhook() {
        act("webhook-test", { testWebhook() }, done = { Notice("CatBoard received the test") })
    }

    fun removeWebhook() {
        act("webhook", { removeWebhook() }, done = { Notice("Webhook removed") }, after = { answer ->
            _security.update { it.copy(value = it.value?.copy(webhookUrl = answer.webhookUrl)) }
        })
    }

    fun revoke(device: Device) {
        act("device-${device.id}", { revokeDevice(device.id) }, done = { Notice("${device.name} signed out") }, after = { _devices.update { list -> list.filter { it.id != device.id } } })
    }
}

/** The library index, the metadata, the downloads to repair, and Reset data. */
class MaintenanceViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    fun refreshLibrary() = act("refresh", { refreshLibrary() }, done = { Notice("Library refresh started", it.taskId) })

    fun rebuildLibrary() = act("rebuild", { rebuildLibrary() }, done = { Notice("Full library rebuild started", it.taskId) })

    fun fixMetadata() = act("metadata", { fixMetadata() }, done = { Notice("Fixing missing metadata", it.taskId) })

    fun repairDownloads() = act("repair", { repairDownloads() }, done = { Notice("Repairing downloads", it.taskId) })

    fun scanDuplicates() = act("dedup", { scanDuplicates() }, done = { Notice("Duplicate scan started", it.taskId) })

    fun clear(what: String) = act("clear-$what", { clear(what) }, done = { Notice(it.message.ifBlank { "Cleared" }) })
}

/** The last duplicate report: which copy of each track to keep. */
class DuplicatesViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _report = MutableStateFlow(Remote<DuplicateReport>())
    val report: StateFlow<Remote<DuplicateReport>> = _report

    private val _keep = MutableStateFlow<Map<String, Set<String>>>(emptyMap())

    /** Group ID to the paths kept: checked files are kept. */
    val keep: StateFlow<Map<String, Set<String>>> = _keep

    private val _none = MutableStateFlow(false)

    /** No scan has written a report yet: the server answers 404. */
    val none: StateFlow<Boolean> = _none

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _report.fill {
                try {
                    duplicates().report.also { _none.value = false }
                } catch (e: retrofit2.HttpException) {
                    if (e.code() != 404) throw e
                    _none.value = true
                    DuplicateReport()
                }
            }
            _report.value.value?.let { report -> _keep.value = defaults(report) }
        }
    }

    fun scan() = act("dedup", { scanDuplicates() }, done = { Notice("Duplicate scan started", it.taskId) }, after = { taskStarted(::refresh) })

    /** The web's preselection: earlier decisions, else the best copy. */
    private fun defaults(report: DuplicateReport): Map<String, Set<String>> = report.groups.associate { group ->
        group.groupId to (report.keeperHints[group.groupId]?.toSet() ?: setOfNotNull(group.keeper.path.takeIf(String::isNotEmpty)))
    }

    fun toggle(groupId: String, path: String) {
        _keep.update { all ->
            val current = all[groupId].orEmpty()
            all + (groupId to if (path in current) current - path else current + path)
        }
    }

    fun keepAll() {
        _keep.value = _report.value.value?.groups?.associate { g -> g.groupId to g.entries.map { it.path }.toSet() } ?: emptyMap()
    }

    fun keepBest() {
        _report.value.value?.let { _keep.value = defaults(it) }
    }

    fun apply(mode: String) {
        val decisions = _keep.value.map { (id, paths) -> DuplicateDecision(id, paths.toList()) }
        act(
            "apply",
            { applyDuplicates(DuplicateApply(decisions, mode)) },
            done = { answer ->
                val verb = if (mode == "delete") "deleted" else "moved to quarantine"
                val gone = if (answer.missing > 0) ", ${plural(answer.missing, "file")} already gone" else ""
                Notice("${plural(answer.done, "file")} $verb$gone")
            },
            after = { refresh() },
        )
    }
}
