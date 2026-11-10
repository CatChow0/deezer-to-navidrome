package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// What the app sends. A field the server must always get has no default: the
// client's JSON leaves out values equal to their default, and nulls.

@Serializable
data class LinkRequest(val link: String)

/** [mode]: quick re-matches what is missing or unchecked, full every track. */
@Serializable
data class ScanRequest(val mode: String)

/** [mode]: file (with [path]), missing, or auto. */
@Serializable
data class MatchRequest(
    @SerialName("track_id") val trackId: String,
    val mode: String,
    val path: String? = null,
)

/** An imported track's Deezer pick: a track ID, "auto", or null for "not on Deezer". */
@Serializable
data class SourceMatchRequest(
    val key: String,
    @SerialName("deezer_id") val deezerId: String? = null,
)

@Serializable
data class AccountsRequest(val accounts: List<String>)

@Serializable
data class AutomationRequest(
    @SerialName("auto_scan_enabled") val scan: Boolean,
    @SerialName("auto_scan_interval_minutes") val intervalMinutes: Int,
    @SerialName("auto_download_after_scan") val download: Boolean,
)

/** [type]: track, album or artist (the discography). */
@Serializable
data class DownloadRequest(
    val type: String,
    @SerialName("music_id") val musicId: String,
    val label: String,
    @SerialName("playlist_id") val playlistId: String? = null,
)

@Serializable
data class TrackDownloadRequest(
    val label: String,
    @SerialName("playlist_id") val playlistId: String? = null,
)

/** Only what changes is sent. */
@Serializable
data class MixSettingsChange(
    @SerialName("mix_mode") val mixMode: String? = null,
    val discover: Boolean? = null,
    @SerialName("daily_hours") val dailyHours: Int? = null,
    @SerialName("discover_days") val discoverDays: Int? = null,
    @SerialName("mix_size") val mixSize: Int? = null,
    @SerialName("discover_size") val discoverSize: Int? = null,
    @SerialName("blend_new_percent") val blendNewPercent: Int? = null,
    @SerialName("max_unheard") val maxUnheard: Int? = null,
    @SerialName("max_trial_gb") val maxTrialGb: Int? = null,
    @SerialName("trial_auto") val trialAuto: Boolean? = null,
    @SerialName("trial_days") val trialDays: Int? = null,
    @SerialName("trash_days") val trashDays: Int? = null,
    @SerialName("trial_delete") val trialDelete: Boolean? = null,
    @SerialName("trial_bypass") val trialBypass: Boolean? = null,
    @SerialName("trial_plays") val trialPlays: Int? = null,
    @SerialName("trial_marks") val trialMarks: Boolean? = null,
)

@Serializable
data class IdsRequest(val ids: List<String>)

@Serializable
data class FollowMixRequest(
    val kind: String,
    @SerialName("source_id") val sourceId: String,
    val title: String,
)
