package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// The listening history of the profile: overview, recaps, details and plays.

@Serializable
data class StatsTotals(
    val plays: Int = 0,
    val seconds: Long = 0,
    val artists: Int = 0,
    val albums: Int = 0,
    val tracks: Int = 0,
)

@Serializable
data class StatsCoverage(
    @SerialName("length_pct") val lengthPct: Int = 100,
    @SerialName("genre_pct") val genrePct: Int = 100,
)

/** A row of a top list: an artist ([name]), an album or a track ([title]). */
@Serializable
data class RankRow(
    val id: Long = 0,
    val name: String? = null,
    val title: String? = null,
    val artist: String? = null,
    val image: String? = null,
    val plays: Int = 0,
    val seconds: Long = 0,
    @SerialName("deezer_track_id") val deezerTrackId: FlexibleId? = null,
    @SerialName("previous_plays") val previousPlays: Int? = null,
    @SerialName("is_new") val isNew: Boolean = false,
    val delta: Int = 0,
) {
    val label: String get() = name ?: title ?: ""
}

@Serializable
data class StatsTop(
    val artists: List<RankRow> = emptyList(),
    val albums: List<RankRow> = emptyList(),
    val tracks: List<RankRow> = emptyList(),
)

@Serializable
data class StatsGenre(val name: String = "", val plays: Int = 0, val seconds: Long = 0, val share: Double = 0.0)

@Serializable
data class BusiestDay(val date: String = "", val plays: Int = 0)

@Serializable
data class Streak(val days: Int = 0, val start: String = "", val end: String = "")

@Serializable
data class StatsHabits(
    /** 7 weekdays (Monday first) of 24 hours. */
    val heatmap: List<List<Int>> = emptyList(),
    @SerialName("busiest_day") val busiestDay: BusiestDay = BusiestDay(),
    @SerialName("longest_streak") val longestStreak: Streak = Streak(),
)

@Serializable
data class StatsOverview(
    val period: String = "month",
    val key: String = "",
    val label: String = "",
    val totals: StatsTotals = StatsTotals(),
    val coverage: StatsCoverage = StatsCoverage(),
    val top: StatsTop = StatsTop(),
    val genres: List<StatsGenre> = emptyList(),
    val habits: StatsHabits = StatsHabits(),
)

@Serializable
data class RecapEntry(
    val key: String = "",
    val label: String = "",
    val plays: Int = 0,
    val partial: Boolean = false,
    @SerialName("so_far") val soFar: Boolean = false,
)

@Serializable
data class RecapIndex(
    val months: List<RecapEntry> = emptyList(),
    val years: List<RecapEntry> = emptyList(),
    @SerialName("latest_complete") val latestComplete: String? = null,
)

/** A track of the history: its file plays at /api/v1/stats/audio/{id}. */
@Serializable
data class HistoryTrack(
    val id: Long = 0,
    val title: String = "",
    val artist: String = "",
    /** Seconds, as the file's tags say: 248.85. */
    val duration: Double = 0.0,
    @SerialName("deezer_track_id") val deezerTrackId: FlexibleId = "",
    val image: String = "",
    val date: String = "",
    val time: String = "",
    val plays: Int = 0,
)

@Serializable
data class Loyalty(val artist: RankRow = RankRow(), val percent: Int = 0, @SerialName("one_in") val oneIn: Int = 0)

@Serializable
data class Binge(
    val date: String = "",
    val seconds: Long = 0,
    val plays: Int = 0,
    @SerialName("top_artist") val topArtist: String = "",
)

@Serializable
data class AlbumRun(
    val title: String = "",
    val artist: String = "",
    val tracks: Int = 0,
    val of: Int = 0,
    val date: String = "",
    val image: String = "",
)

@Serializable
data class Movers(val rise: RankRow? = null, val fall: RankRow? = null)

@Serializable
data class Comparison(val value: Long = 0, val unit: String = "")

@Serializable
data class HourClock(val hours: List<Int> = emptyList(), @SerialName("peak_hour") val peakHour: Int = 0)

@Serializable
data class BiggestMonth(val label: String = "", val plays: Int = 0)

@Serializable
data class Personality(val name: String = "", val reason: String = "")

@Serializable
data class StorySlide(val type: String = "", val track: HistoryTrack? = null)

/** What the recap tells, slide by slide; the server picks the slides. */
@Serializable
data class Story(
    @SerialName("top_artists") val topArtists: List<RankRow> = emptyList(),
    val established: Boolean? = null,
    val comparable: Boolean = false,
    val opener: HistoryTrack? = null,
    val loyalty: Loyalty? = null,
    val obsession: HistoryTrack? = null,
    val binge: Binge? = null,
    @SerialName("album_run") val albumRun: AlbumRun? = null,
    val movers: Movers? = null,
    val comeback: RankRow? = null,
    val dropped: RankRow? = null,
    val comparisons: List<Comparison> = emptyList(),
    val clock: HourClock? = null,
    @SerialName("biggest_month") val biggestMonth: BiggestMonth? = null,
    val personality: Personality = Personality(),
    val slides: List<StorySlide> = emptyList(),
)

@Serializable
data class PreviousPeriod(val key: String = "", val label: String = "", val totals: StatsTotals = StatsTotals())

@Serializable
data class Recap(
    val kind: String = "month",
    val key: String = "",
    val label: String = "",
    val totals: StatsTotals = StatsTotals(),
    val coverage: StatsCoverage = StatsCoverage(),
    val top: StatsTop = StatsTop(),
    val genres: List<StatsGenre> = emptyList(),
    @SerialName("so_far") val soFar: Boolean = false,
    val partial: Boolean = false,
    val previous: PreviousPeriod? = null,
    @SerialName("new_artists") val newArtists: List<RankRow> = emptyList(),
    val discovery: RankRow? = null,
    val story: Story = Story(),
)

@Serializable
data class MonthPlays(val key: String = "", val plays: Int = 0)

@Serializable
data class EntityTrack(val title: String = "", val artist: String = "", val plays: Int = 0)

/** An artist, an album or a track of the history ([kind]). */
@Serializable
data class StatsEntity(
    val kind: String = "artist",
    val id: Long = 0,
    val name: String = "",
    val artist: String? = null,
    val image: String? = null,
    @SerialName("deezer_track_id") val deezerTrackId: FlexibleId = "",
    val plays: Int = 0,
    val seconds: Long = 0,
    @SerialName("first_play") val firstPlay: Double? = null,
    @SerialName("last_play") val lastPlay: Double? = null,
    @SerialName("by_month") val byMonth: List<MonthPlays> = emptyList(),
    @SerialName("top_tracks") val topTracks: List<EntityTrack> = emptyList(),
)

@Serializable
data class Play(
    val id: Long = 0,
    @SerialName("listened_at") val listenedAt: Double = 0.0,
    val source: String? = null,
    @SerialName("track_id") val trackId: Long = 0,
    val title: String = "",
    val artist: String = "",
    val album: String? = null,
)

@Serializable
data class PlaysPage(val plays: List<Play> = emptyList(), val total: Int = 0, val page: Int = 1, val pages: Int = 1)
