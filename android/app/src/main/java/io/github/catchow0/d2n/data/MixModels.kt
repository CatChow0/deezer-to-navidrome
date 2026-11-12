package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Made for you (GET /api/v1/mixes) and the mixes Deezer makes.

@Serializable
data class MixProfile(val id: String = "", val label: String = "", val several: Boolean = false)

/** The profile's versions, limits and trial rules. [mixMode] is off, daily or blend. */
@Serializable
data class MixSettings(
    @SerialName("mix_mode") val mixMode: String = "off",
    val discover: Boolean = false,
    @SerialName("daily_hours") val dailyHours: Int = 24,
    @SerialName("discover_days") val discoverDays: Int = 7,
    @SerialName("mix_size") val mixSize: Int = 25,
    @SerialName("discover_size") val discoverSize: Int = 30,
    @SerialName("blend_new_percent") val blendNewPercent: Int = 33,
    @SerialName("max_unheard") val maxUnheard: Int = 100,
    @SerialName("max_trial_gb") val maxTrialGb: Int = 20,
    @SerialName("trial_auto") val trialAuto: Boolean = true,
    @SerialName("trial_days") val trialDays: Int = 30,
    @SerialName("trash_days") val trashDays: Int = 7,
    @SerialName("trial_delete") val trialDelete: Boolean = false,
    @SerialName("trial_bypass") val trialBypass: Boolean = false,
    @SerialName("trial_plays") val trialPlays: Int = 3,
    @SerialName("trial_marks") val trialMarks: Boolean = true,
)

/** Fix missing metadata: how far it got over the library. */
@Serializable
data class MetadataAnalysis(
    val total: Int = 0,
    val left: Int = 0,
    val tagged: Int = 0,
    @SerialName("only_in_app") val onlyInApp: Int = 0,
    @SerialName("write_errors") val writeErrors: Int = 0,
    @SerialName("can_undo") val canUndo: Int = 0,
    @SerialName("write_off") val writeOff: Boolean = false,
    val paused: Boolean = false,
    val running: Boolean = false,
)

@Serializable
data class MixLastRun(val at: Double? = null, val notes: List<String> = emptyList())

/** What the disk limits count, every profile together. */
@Serializable
data class TrialUsage(val unheard: Int = 0, val bytes: Long = 0)

@Serializable
data class MixTrack(
    val id: FlexibleId,
    @SerialName("shared_with") val sharedWith: List<String> = emptyList(),
    val artist: String = "",
    val title: String = "",
    val album: String = "",
    val plays: Int = 0,
    val reason: String = "",
    val source: String = "",
    val cover: String = "",
    @SerialName("downloaded_at") val downloadedAt: Double = 0.0,
    @SerialName("state_at") val stateAt: Double = 0.0,
    @SerialName("days_left") val daysLeft: Int = 0,
    @SerialName("trash_days_left") val trashDaysLeft: Int = 0,
)

@Serializable
data class MixesAnswer(
    val profile: MixProfile = MixProfile(),
    val settings: MixSettings = MixSettings(),
    @SerialName("downloads_blocked") val downloadsBlocked: String = "",
    val analysis: MetadataAnalysis = MetadataAnalysis(),
    val running: Boolean = false,
    @SerialName("last_run") val lastRun: MixLastRun? = null,
    @SerialName("navidrome_mounted") val navidromeMounted: Boolean = false,
    val usage: TrialUsage = TrialUsage(),
    @SerialName("on_trial") val onTrial: List<MixTrack> = emptyList(),
    val pending: List<MixTrack> = emptyList(),
    val trash: List<MixTrack> = emptyList(),
)

/** A mix Deezer makes for the profile's Deezer account. [kind] is stl or flow. */
@Serializable
data class DeezerMix(
    val kind: String = "",
    @SerialName("source_id") val sourceId: FlexibleId = "",
    val id: String = "",
    val title: String = "",
    val subtitle: String = "",
    val group: String = "",
    val followed: Boolean = false,
)

/** A Deezer playlist: one of the account's own, or one Deezer suggests on its home page. */
@Serializable
data class DeezerPick(
    val id: FlexibleId = "",
    val title: String = "",
    val subtitle: String = "",
    val picture: String = "",
    val group: String = "",
    val followed: Boolean = false,
    val tracks: Int? = null,
)

@Serializable
data class DeezerMixesAnswer(
    val mixes: List<DeezerMix> = emptyList(),
    /** Recommended: the playlists of Deezer's home page. */
    val playlists: List<DeezerPick> = emptyList(),
    /** The account's own: Loved tracks, those it made, its favorites. */
    val yours: List<DeezerPick> = emptyList(),
    @SerialName("yours_error") val yoursError: String? = null,
)

@Serializable
data class FollowAnswer(val id: String = "", val added: Boolean = false)
