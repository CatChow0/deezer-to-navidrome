package io.github.catchow0.d2n.ui.madeforyou

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.IdsRequest
import io.github.catchow0.d2n.data.MixSettingsChange
import io.github.catchow0.d2n.data.MixTrack
import io.github.catchow0.d2n.data.MixesAnswer
import io.github.catchow0.d2n.data.PlaylistTile
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Notice
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.plural
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** The three lists of the quarantine, as on the web. */
enum class TrialList(val label: String, val empty: String) {
    Trial("On trial", "No track on trial."),
    Review("To review", "Nothing to confirm right now."),
    Trash("Trash", "The trash is empty."),
}

fun MixesAnswer.tracksOf(list: TrialList): List<MixTrack> = when (list) {
    TrialList.Trial -> onTrial
    TrialList.Review -> pending
    TrialList.Trash -> trash
}

/** How a list is sorted: the web's choices for each list. */
enum class TrialSort(val label: String, val comparator: Comparator<MixTrack>) {
    NewestDownload("Newest", compareByDescending { it.downloadedAt }),
    NewestState("Newest", compareByDescending { it.stateAt }),
    RecentlyRemoved("Recently removed", compareByDescending { it.stateAt }),
    Ending("Ending soonest", compareBy<MixTrack> { it.daysLeft }.thenByDescending { it.downloadedAt }),
    TrashEnding("Deleted soonest", compareBy<MixTrack> { it.trashDaysLeft }.thenByDescending { it.stateAt }),
    Plays("Most played", compareByDescending<MixTrack> { it.plays }.thenByDescending { it.downloadedAt }),
    Artist("Artist", compareBy<MixTrack, String>(String.CASE_INSENSITIVE_ORDER) { it.artist }.thenBy(String.CASE_INSENSITIVE_ORDER) { it.title }),
    Title("Title", compareBy(String.CASE_INSENSITIVE_ORDER) { it.title }),
    ;

    companion object {
        fun of(list: TrialList): List<TrialSort> = when (list) {
            TrialList.Trial -> listOf(NewestDownload, Ending, Plays, Artist, Title)
            TrialList.Review -> listOf(NewestState, Plays, Artist, Title)
            TrialList.Trash -> listOf(TrashEnding, RecentlyRemoved, Artist, Title)
        }
    }
}

/** What a list shows: all, a source, played or not, or one reason. */
fun trialFilters(list: TrialList, tracks: List<MixTrack>): List<Pair<String, String>> = buildList {
    add("all" to "All tracks")
    add("source:Daily Mix+" to "From Daily Mix+")
    add("source:Discover" to "From Discover")
    if (list == TrialList.Trial) {
        add("played" to "Played")
        add("unplayed" to "Never played")
    }
    if (list == TrialList.Review) {
        tracks.map { it.reason }.filter(String::isNotBlank).distinct().sorted().forEach { add("reason:$it" to it) }
    }
}

fun List<MixTrack>.shown(query: String, sort: TrialSort, filter: String): List<MixTrack> {
    val words = query.trim().lowercase()
    return filter { track ->
        if (words.isNotEmpty() && !"${track.title} ${track.artist} ${track.album}".lowercase().contains(words)) return@filter false
        when {
            filter == "all" -> true
            filter == "played" -> track.plays > 0
            filter == "unplayed" -> track.plays == 0
            filter.startsWith("reason:") -> track.reason == filter.removePrefix("reason:")
            filter.startsWith("source:") -> track.source == filter.removePrefix("source:")
            else -> true
        }
    }.sortedWith(sort.comparator)
}

/** "3 plays" or "Never played". */
fun playsText(plays: Int) = if (plays > 0) plural(plays, "play") else "Never played"

/** The line under a track, as the web words it for each list. */
fun TrialList.detail(track: MixTrack): String = when (this) {
    TrialList.Trial -> "${playsText(track.plays)} · ${plural(track.daysLeft, "day")} left"
    TrialList.Review -> {
        val plays = playsText(track.plays)
        if (track.reason.isBlank() || track.reason == plays || track.reason.startsWith("Played") || track.reason.startsWith("Never played")) {
            track.reason.ifBlank { plays }
        } else {
            "${track.reason} · $plays"
        }
    }
    TrialList.Trash -> "${track.reason.ifBlank { "Removed" }} · deleted in ${plural(track.trashDaysLeft, "day")}"
}

/** Made for you of the profile: the versions, the quarantine and the mixes they made. */
class MadeForYouViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _state = MutableStateFlow(Remote<MixesAnswer>())
    val state: StateFlow<Remote<MixesAnswer>> = _state

    private val _playlists = MutableStateFlow<List<PlaylistTile>>(emptyList())

    /** The playlists Made for you and Deezer's mixes made for this profile. */
    val playlists: StateFlow<List<PlaylistTile>> = _playlists

    init {
        followProfile { load() }
    }

    private suspend fun load() = coroutineScope {
        launch { _state.fill { mixes() } }
        launch {
            try {
                _playlists.value = call { playlists() }.playlists.filter { it.kind == "auto" || it.kind == "mix" }
            } catch (e: ApiFailure) {
                // The quarantine still shows.
            }
        }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    private fun settings(change: MixSettingsChange, saved: String? = null) {
        act("settings", { mixSettings(change) }, done = { saved?.let(::Notice) }, after = { _state.value = Remote(it, loading = false) })
    }

    fun setMode(mode: String) = settings(MixSettingsChange(mixMode = mode))

    fun setDiscover(on: Boolean) = settings(MixSettingsChange(discover = on))

    /** Daily Mix+ chosen while downloads cannot run: why. */
    fun notifyBlocked(reason: String) = deps.events.post(Notice("Daily Mix+ cannot be chosen. $reason", error = true))

    fun saveLimits(change: MixSettingsChange) = settings(change, "Limits saved")

    fun saveTrialRules(change: MixSettingsChange) = settings(change, "Trial rules saved")

    fun generate() {
        act("generate", { generateMixes() }, done = { Notice("Generating your mixes", it.taskId) }, after = { taskStarted(::refresh) })
    }

    fun keep(track: MixTrack) = decide(track, "keep")

    fun remove(track: MixTrack) = decide(track, "remove")

    fun restore(track: MixTrack) = decide(track, "restore")

    private fun decide(track: MixTrack, verb: String) {
        act(
            "track-${track.id}",
            {
                when (verb) {
                    "keep" -> keepTrack(track.id)
                    "remove" -> removeTrack(track.id)
                    else -> restoreTrack(track.id)
                }
            },
            done = {
                Notice(
                    when (verb) {
                        "keep" -> "Kept: ${track.title}"
                        "remove" -> "Sent to the trash: ${track.title}"
                        else -> "Back in the library: ${track.title}"
                    },
                )
            },
            after = { _state.value = Remote(it, loading = false) },
        )
    }

    /** Keeps the tracks to review that the list shows. */
    fun keepAll(ids: List<String>) {
        act("keep-all", { keepPending(IdsRequest(ids)) }, done = { Notice("Kept ${plural(ids.size, "track")}") }, after = { _state.value = Remote(it, loading = false) })
    }

    fun emptyTheTrash() {
        act("empty-trash", { emptyTrash() }, done = { Notice("Trash emptied") }, after = { _state.value = Remote(it, loading = false) })
    }

    fun startFixMetadata() {
        act("fix-metadata", { fixMetadata() }, done = { Notice("Fixing missing metadata", it.taskId) })
    }

    fun startUndoMetadata() {
        act("undo-metadata", { undoMetadata() }, done = { Notice("Undoing the metadata fix", it.taskId) })
    }
}
