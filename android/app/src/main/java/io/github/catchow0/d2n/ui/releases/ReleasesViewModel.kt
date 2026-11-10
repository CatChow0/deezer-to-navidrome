package io.github.catchow0.d2n.ui.releases

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.LibraryCheckItem
import io.github.catchow0.d2n.data.MuteRequest
import io.github.catchow0.d2n.data.Owned
import io.github.catchow0.d2n.data.Release
import io.github.catchow0.d2n.data.ReleasesAnswer
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.search.DeezerViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The web's type filter. */
enum class ReleaseType(val label: String) { All("All"), Albums("Albums"), Short("EPs and singles") }

data class ReleaseFilters(val type: ReleaseType = ReleaseType.All, val hideFeatures: Boolean = false, val hideOwned: Boolean = false)

/** Whether the library has a release: all its tracks, some, or none. */
enum class Ownership { Full, Partial, None }

fun ownership(owned: Owned?, release: Release): Ownership? {
    owned ?: return null
    val total = owned.total ?: release.nbTracks
    return when {
        owned.ownedCount <= 0 -> Ownership.None
        total > 0 && owned.ownedCount >= total -> Ownership.Full
        else -> Ownership.Partial
    }
}

/** Feeds built before artist credits were kept only know the followed artist. */
fun Release.followedArtists() = followed.ifEmpty { listOf(io.github.catchow0.d2n.data.ArtistRef(artistId, artist)) }

/** Hidden when every artist it is followed for is muted. */
fun Release.isMuted(muted: Map<String, String>) = followedArtists().all { it.id in muted }

fun ReleasesAnswer.visible(owned: Map<String, Owned>, filters: ReleaseFilters): List<Release> = releases.filter { release ->
    when {
        release.isMuted(muted) -> false
        filters.hideFeatures && release.featured -> false
        filters.type == ReleaseType.Albums && release.recordType != "album" -> false
        filters.type == ReleaseType.Short && release.recordType == "album" -> false
        filters.hideOwned && ownership(owned[release.id], release) == Ownership.Full -> false
        else -> true
    }
}

private val MONTH = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.ENGLISH)
private val DAY = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)

private fun parse(iso: String): LocalDate? = runCatching { LocalDate.parse(iso.take(10)) }.getOrNull()

/** "Upcoming", or the month, as the web groups the feed. */
fun releaseGroup(release: Release, today: LocalDate = LocalDate.now()): String {
    val date = parse(release.releaseDate) ?: return "Undated"
    return if (date.isAfter(today)) "Upcoming" else date.format(MONTH)
}

fun releaseDay(release: Release): String = parse(release.releaseDate)?.format(DAY) ?: release.releaseDate

fun isUpcoming(release: Release, today: LocalDate = LocalDate.now()) = parse(release.releaseDate)?.isAfter(today) == true

val TYPE_LABEL = mapOf("album" to "Album", "ep" to "EP", "single" to "Single", "compile" to "Compilation")

/** The feed line the web shows: how many artists, the window, when and how often it refreshes. */
fun feedLine(answer: ReleasesAnswer, now: Long = System.currentTimeMillis()): String {
    if (!answer.connected) return "Add a Deezer account in Settings to follow the releases of your favorite artists."
    val updated = answer.updatedAt ?: return "The feed has not been built yet. It starts on its own within a minute, or refresh it now."
    val minutes = ((now / 1000.0 - updated) / 60).toInt()
    val whenText = when {
        minutes < 1 -> "just now"
        minutes < 90 -> "$minutes min ago"
        else -> "${(minutes + 30) / 60} h ago"
    }
    val hours = answer.refreshHours
    val schedule = when {
        hours == 0 -> "refreshed only when you ask"
        hours % 24 == 0 -> "refreshed every " + when (hours) { 24 -> "day"; 168 -> "week"; else -> "${hours / 24} days" }
        else -> "refreshed every $hours hours"
    }
    val whose = answer.deezerAccount?.label?.takeIf { it.isNotBlank() }?.let { " of $it" }.orEmpty()
    return "${answer.artists} favorite artists$whose, releases from the last ${answer.windowDays} days. Updated $whenText; $schedule."
}

/** The release feed of the profile's Deezer account, with what the library has. */
class ReleasesViewModel(deps: ScreenDeps) : DeezerViewModel(deps) {
    private val _feed = MutableStateFlow(Remote<ReleasesAnswer>())
    val feed: StateFlow<Remote<ReleasesAnswer>> = _feed

    private val _owned = MutableStateFlow<Map<String, Owned>>(emptyMap())
    val owned: StateFlow<Map<String, Owned>> = _owned

    init {
        followProfile { load() }
    }

    private suspend fun load() {
        _feed.fill { releases() }
        val releases = _feed.value.value?.releases.orEmpty()
        _owned.value = emptyMap()
        // As the web: 100 at a time, the list updating as each batch comes.
        releases.chunked(100).forEach { batch ->
            val found = owned(batch.map { LibraryCheckItem(it.id, "album", id = it.id, title = it.title, artist = it.artist) })
            _owned.update { it + found }
        }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    /** A new feed from Deezer: a task. */
    fun rebuild() {
        act("rebuild", { refreshReleases() }, done = { Notice("Refreshing the release feed", it.taskId) }, after = { taskStarted(::refresh) })
    }

    fun setMuted(artistId: String, name: String, muted: Boolean) {
        act(
            "mute-$artistId",
            { muteArtist(MuteRequest(artistId, name, muted)) },
            done = { Notice(if (muted) "$name is muted in the feed" else "$name is back in the feed") },
            after = { answer -> _feed.update { remote -> remote.copy(value = remote.value?.copy(muted = answer.muted)) } },
        )
    }
}
