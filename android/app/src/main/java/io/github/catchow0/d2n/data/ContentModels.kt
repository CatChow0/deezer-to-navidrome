package io.github.catchow0.d2n.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// New and Help, written on the server for the web and the app alike.

/** What to change for a version: [level] is required, recommended or
 * optional; [lines] are to copy into [file]. [version] is only set in
 * [NotesAnswer.pendingActions]. */
@Serializable
data class NoteAction(
    val level: String = "",
    val `when`: String = "",
    val `do`: String = "",
    val lines: List<String> = emptyList(),
    val file: String = "",
    val version: String = "",
)

@Serializable
data class ReleaseNote(
    val version: String = "",
    val date: String = "",
    val title: String = "",
    val html: String = "",
    val highlights: List<String> = emptyList(),
    val actions: List<NoteAction> = emptyList(),
)

/** [unseen]: the New button still shows its dot; [since] the version read
 * last, and [pendingActions] what to change for every version after it.
 * A server before 1.19 sends neither: the defaults show nothing more. */
@Serializable
data class NotesAnswer(
    val notes: List<ReleaseNote> = emptyList(),
    val unseen: Boolean = false,
    val since: String? = null,
    @SerialName("pending_actions") val pendingActions: List<NoteAction> = emptyList(),
)

@Serializable
data class HelpSection(val id: String = "", val title: String = "", val html: String = "")

@Serializable
data class HelpAnswer(val sections: List<HelpSection> = emptyList())
