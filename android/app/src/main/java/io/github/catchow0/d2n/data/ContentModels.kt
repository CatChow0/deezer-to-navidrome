package io.github.catchow0.d2n.data

import kotlinx.serialization.Serializable

// New and Help, written on the server for the web and the app alike.

@Serializable
data class ReleaseNote(val version: String = "", val date: String = "", val title: String = "", val html: String = "")

/** [unseen]: the New button still shows its dot. */
@Serializable
data class NotesAnswer(val notes: List<ReleaseNote> = emptyList(), val unseen: Boolean = false)

@Serializable
data class HelpSection(val id: String = "", val title: String = "", val html: String = "")

@Serializable
data class HelpAnswer(val sections: List<HelpSection> = emptyList())
