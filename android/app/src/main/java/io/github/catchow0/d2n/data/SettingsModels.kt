package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Settings: folders and limits, accounts, sign-in, maintenance.

@Serializable
data class PathMapping(val host: String = "", val navidrome: String = "")

@Serializable
data class SettingsValues(
    @SerialName("scan_dirs") val scanDirs: List<String> = emptyList(),
    @SerialName("host_to_navidrome_roots") val mappings: List<PathMapping> = emptyList(),
    @SerialName("deezer_dl_dir") val deezerDlDir: String? = null,
    @SerialName("playlists_base_dir") val playlistsBaseDir: String? = null,
    @SerialName("playlist_ids_file") val playlistIdsFile: String? = null,
    @SerialName("library_cache_file") val libraryCacheFile: String? = null,
    @SerialName("preview_state_file") val previewStateFile: String? = null,
    @SerialName("library_workers_per_dir") val libraryWorkersPerDir: Int? = null,
    @SerialName("match_workers") val matchWorkers: Int? = null,
    @SerialName("download_workers") val downloadWorkers: Int? = null,
    @SerialName("metadata_workers") val metadataWorkers: Int? = null,
    @SerialName("release_refresh_hours") val releaseRefreshHours: Int? = null,
)

@Serializable
data class DownloadFolder(
    val path: String = "",
    val configured: String = "",
    val exists: Boolean = false,
    val writable: Boolean = false,
)

@Serializable
data class SettingsAnswer(
    val settings: SettingsValues = SettingsValues(),
    @SerialName("downloads_folder") val downloadsFolder: DownloadFolder = DownloadFolder(),
    /** The values each number takes, as the web's menus offer them. */
    val choices: Map<String, List<Int>> = emptyMap(),
)

/** Only what changes is sent; the server keeps the others. */
@Serializable
data class SettingsChange(
    @SerialName("scan_dirs") val scanDirs: List<String>? = null,
    @SerialName("host_to_navidrome_roots") val mappings: List<PathMapping>? = null,
    @SerialName("deezer_dl_dir") val deezerDlDir: String? = null,
    @SerialName("playlists_base_dir") val playlistsBaseDir: String? = null,
    @SerialName("playlist_ids_file") val playlistIdsFile: String? = null,
    @SerialName("library_cache_file") val libraryCacheFile: String? = null,
    @SerialName("preview_state_file") val previewStateFile: String? = null,
    @SerialName("library_workers_per_dir") val libraryWorkersPerDir: Int? = null,
    @SerialName("match_workers") val matchWorkers: Int? = null,
    @SerialName("download_workers") val downloadWorkers: Int? = null,
    @SerialName("metadata_workers") val metadataWorkers: Int? = null,
    @SerialName("release_refresh_hours") val releaseRefreshHours: Int? = null,
)

@Serializable
data class ClearAnswer(val cleared: String = "", val message: String = "")

// ── Navidrome accounts ──────────────────────────────────────────────────────

@Serializable
data class LibraryName(val name: String = "")

/** What the last connection test learnt. */
@Serializable
data class ConnectionTest(
    val ok: Boolean = false,
    val at: Double? = null,
    val error: String? = null,
    @SerialName("server_version") val serverVersion: String? = null,
    val admin: Boolean? = null,
    val libraries: List<LibraryName> = emptyList(),
    @SerialName("api_keys") val apiKeys: Boolean = false,
    @SerialName("navidrome_user") val navidromeUser: String? = null,
    val warning: String? = null,
)

@Serializable
data class SyncReport(
    val at: Double? = null,
    val error: String? = null,
    val removed: List<String> = emptyList(),
    val renamed: Int = 0,
    val handmade: Int = 0,
    val warning: String? = null,
)

/** A Navidrome account as Settings shows it: never its password. */
@Serializable
data class NavidromeProfile(
    val id: String,
    val label: String = "",
    val url: String = "",
    val username: String = "",
    @SerialName("auth_type") val authType: String = "password",
    @SerialName("has_secret") val hasSecret: Boolean = false,
    @SerialName("publish_mode") val publishMode: String = "api",
    @SerialName("deezer_account") val deezerAccount: String = "",
    @SerialName("is_default") val isDefault: Boolean = false,
    val complete: Boolean = false,
    val legacy: Boolean = false,
    @SerialName("last_test") val lastTest: ConnectionTest? = null,
    val sync: SyncReport? = null,
)

@Serializable
data class EncryptionSource(val source: String = "file")

@Serializable
data class NavidromeDatabase(val mounted: Boolean = false, val users: List<String> = emptyList())

@Serializable
data class NavidromeProfilesAnswer(
    val accounts: List<NavidromeProfile> = emptyList(),
    val active: String? = null,
    val default: String? = null,
    val encryption: EncryptionSource = EncryptionSource(),
    @SerialName("navidrome_db") val navidromeDb: NavidromeDatabase = NavidromeDatabase(),
    val created: String? = null,
    val test: ConnectionTest? = null,
)

/** A Navidrome account typed in the form. An empty secret keeps the saved one. */
@Serializable
data class NavidromeProfileFields(
    val label: String,
    val url: String,
    val username: String,
    @SerialName("auth_type") val authType: String,
    val secret: String? = null,
    @SerialName("deezer_account") val deezerAccount: String,
    val id: String? = null,
)

@Serializable
data class TestAnswer(val test: ConnectionTest = ConnectionTest())

@Serializable
data class OldCopy(val name: String = "", val owner: String = "")

/** What publishing as the Navidrome user (instead of .m3u8 files) would do. */
@Serializable
data class SwitchPreview(
    val ok: Boolean = false,
    val problems: List<String> = emptyList(),
    val playlists: Int = 0,
    val files: Int = 0,
    val database: Boolean = false,
    val old: List<OldCopy> = emptyList(),
    @SerialName("can_remove_old") val canRemoveOld: Boolean = false,
)

@Serializable
data class SwitchPreviewAnswer(val preview: SwitchPreview = SwitchPreview())

// ── Deezer accounts ─────────────────────────────────────────────────────────

/** A Deezer account as Settings shows it: never its ARL. */
@Serializable
data class DeezerProfile(
    val id: String,
    val label: String = "",
    val name: String = "",
    val country: String = "",
    val premium: Boolean = false,
    val format: String = "",
    @SerialName("from_env") val fromEnv: String = "",
    @SerialName("has_arl") val hasArl: Boolean = false,
    @SerialName("is_default") val isDefault: Boolean = false,
    @SerialName("is_download") val isDownload: Boolean = false,
    @SerialName("checked_at") val checkedAt: Double = 0.0,
    val error: String = "",
    /** False for one another account shared with you: you use it, never change it. */
    val mine: Boolean = true,
    val owner: String = "",
    @SerialName("shared_with") val sharedWith: List<String> = emptyList(),
)

@Serializable
data class DownloadsAccount(
    val account: String? = null,
    val label: String = "",
    val connected: Boolean = false,
    val premium: Boolean = false,
    val format: String? = null,
    val country: String? = null,
    val error: String? = null,
)

@Serializable
data class DeezerProfilesAnswer(
    val accounts: List<DeezerProfile> = emptyList(),
    val default: String? = null,
    val download: String? = null,
    val downloads: DownloadsAccount? = null,
    val created: String? = null,
)

/** An ARL is sent, never read back; null keeps the saved one. */
@Serializable
data class DeezerProfileFields(val label: String, val arl: String? = null)

// ── Sign-in and other apps ──────────────────────────────────────────────────

@Serializable
data class SecurityAnswer(
    val disabled: Boolean = false,
    val username: String = "",
    @SerialName("account_from_env") val accountFromEnv: Boolean = false,
    val token: String? = null,
    @SerialName("token_from_env") val tokenFromEnv: Boolean = false,
    @SerialName("webhook_url") val webhookUrl: String? = null,
    /** The profiles the API token and the webhook are about (CatBoard). */
    @SerialName("catboard_profiles") val catboardProfiles: List<String> = emptyList(),
    val profiles: List<Profile> = emptyList(),
)

@Serializable
data class PasswordRequest(val current: String, val new: String)

@Serializable
data class TokenAnswer(val token: String = "")

@Serializable
data class WebhookRequest(val url: String)

@Serializable
data class WebhookAnswer(@SerialName("webhook_url") val webhookUrl: String? = null)

@Serializable
data class WebhookTestAnswer(val message: String = "")

@Serializable
data class Device(
    val id: String,
    val name: String = "",
    @SerialName("created_at") val createdAt: Double? = null,
    @SerialName("last_used_at") val lastUsedAt: Double? = null,
    @SerialName("last_ip") val lastIp: String? = null,
    val current: Boolean = false,
)

@Serializable
data class DevicesAnswer(val devices: List<Device> = emptyList())

// ── Listening stats ─────────────────────────────────────────────────────────

@Serializable
data class StatsSource(val found: Boolean = false, val path: String = "", val user: String? = null)

@Serializable
data class MalojaSource(
    val used: Boolean = false,
    val owner: String = "",
    val found: Boolean = false,
    val path: String = "",
    @SerialName("kept_copy") val keptCopy: Boolean = false,
    @SerialName("kept_at") val keptAt: Double? = null,
)

@Serializable
data class StatsSources(
    val navidrome: StatsSource = StatsSource(),
    val maloja: MalojaSource = MalojaSource(),
    @SerialName("can_merge") val canMerge: Boolean = false,
    @SerialName("can_clean") val canClean: Boolean = false,
)

@Serializable
data class ImportReport(
    val mode: String = "merge",
    @SerialName("finished_at") val finishedAt: Double? = null,
    val after: Int = 0,
    val added: Int = 0,
    val updated: Int = 0,
    val merged: Int = 0,
    val warnings: List<String> = emptyList(),
)

@Serializable
data class EnrichProgress(val pending: Int = 0, val done: Int = 0)

@Serializable
data class StatsStatusAccount(val id: String = "", val label: String = "", val username: String = "", val several: Boolean = false)

@Serializable
data class StatsStatus(
    val account: StatsStatusAccount = StatsStatusAccount(),
    val plays: Int = 0,
    @SerialName("last_play_at") val lastPlayAt: Double? = null,
    val token: String? = null,
    @SerialName("token_from_env") val tokenFromEnv: Boolean = false,
    @SerialName("token_env") val tokenEnv: String = "",
    @SerialName("base_url_hint") val baseUrlHint: String = "",
    val sources: StatsSources = StatsSources(),
    @SerialName("last_import") val lastImport: ImportReport? = null,
    val enrich: EnrichProgress = EnrichProgress(),
    @SerialName("import_running") val importRunning: Boolean = false,
)

@Serializable
data class ImportRequest(val mode: String)

@Serializable
data class ImportPreview(val removed: Int = 0)

@Serializable
data class StatsTokenRequest(val token: String? = null)

@Serializable
data class StatsTokenAnswer(val token: String? = null)

// ── Duplicates ──────────────────────────────────────────────────────────────

@Serializable
data class DuplicateFile(
    @SerialName("path_str") val path: String = "",
    @SerialName("tag_title") val tagTitle: String? = null,
    @SerialName("parsed_track_title") val parsedTitle: String? = null,
    @SerialName("track_number") val trackNumber: Int? = null,
    val duration: Double? = null,
    val size: Long? = null,
    @SerialName("quality_score") val quality: Double = 0.0,
)

@Serializable
data class DuplicateIdentity(val artist: String = "", val album: String = "", @SerialName("base_title") val baseTitle: String = "")

@Serializable
data class DuplicateKeeper(@SerialName("path_str") val path: String = "")

@Serializable
data class DuplicateGroup(
    @SerialName("group_id") val groupId: String,
    val identity: DuplicateIdentity = DuplicateIdentity(),
    val keeper: DuplicateKeeper = DuplicateKeeper(),
    val entries: List<DuplicateFile> = emptyList(),
)

@Serializable
data class DuplicateReport(
    @SerialName("generated_at") val generatedAt: Double? = null,
    @SerialName("group_count") val groupCount: Int = 0,
    @SerialName("total_group_count") val totalGroupCount: Int = 0,
    @SerialName("duplicate_file_count") val duplicateFileCount: Int = 0,
    val groups: List<DuplicateGroup> = emptyList(),
    /** Group ID to the paths to keep, from earlier decisions. */
    @SerialName("keeper_hints") val keeperHints: Map<String, List<String>> = emptyMap(),
)

@Serializable
data class DuplicateReportAnswer(val report: DuplicateReport = DuplicateReport())

@Serializable
data class DuplicateDecision(@SerialName("group_id") val groupId: String, @SerialName("keep_paths") val keepPaths: List<String>)

/** [mode]: quarantine (moved aside, recoverable) or delete. */
@Serializable
data class DuplicateApply(val decisions: List<DuplicateDecision>, val mode: String)

@Serializable
data class DuplicateApplyAnswer(val processed: Int = 0, val results: List<DuplicateOutcome> = emptyList()) {
    /** Files really moved or deleted; the others were already gone. */
    val done: Int get() = results.count { it.status == "moved" || it.status == "deleted" }
    val missing: Int get() = results.count { it.status == "missing" }
}

/** What happened to one file: "moved", "deleted" or "missing". */
@Serializable
data class DuplicateOutcome(val path: String = "", val status: String = "")
