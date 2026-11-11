package io.github.catchow0.d2n.ui.content

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.HelpAnswer
import io.github.catchow0.d2n.data.NoteAction
import io.github.catchow0.d2n.data.NotesAnswer
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.Chip
import io.github.catchow0.d2n.ui.components.ChipTone
import io.github.catchow0.d2n.ui.components.ButtonKind
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.ListRow
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.rememberCopy
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** New: the notes of each version, newest first. Opening them marks them read. */
class NotesViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _notes = MutableStateFlow(Remote<NotesAnswer>())
    val notes: StateFlow<Remote<NotesAnswer>> = _notes

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _notes.fill { notes() }
            if (_notes.value.value?.unseen == true) {
                try {
                    call { notesSeen() }
                    deps.events.unseenNotes.value = false
                } catch (e: ApiFailure) {
                    // The dot stays until the next time.
                }
            }
        }
    }
}

/** Help: its sections, written for the web and shown here as they are. */
class HelpViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _help = MutableStateFlow(Remote<HelpAnswer>())
    val help: StateFlow<Remote<HelpAnswer>> = _help

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { _help.fill { help() } }
    }
}

@Composable
fun NotesScreen(vm: NotesViewModel, onBack: () -> Unit) {
    val notes by vm.notes.collectAsStateWithLifecycle()
    ScreenScaffold(title = "What's new", onBack = onBack, refreshing = notes.refreshing, onRefresh = vm::refresh) {
        remote(notes, onRetry = vm::refresh, skeletons = 3, skeletonHeight = 160.dp) { answer ->
            val unread = answer.pendingActions.map { it.version }.distinct()
            if (answer.unseen && answer.pendingActions.isNotEmpty()) {
                item(key = "since") {
                    GlassCard(Modifier.fillMaxWidth()) {
                        Text(
                            "Since ${answer.since ?: "your version"}: ${answer.pendingActions.size} thing" +
                                (if (answer.pendingActions.size == 1) "" else "s") + " to check",
                            style = MaterialTheme.typography.titleSmall,
                        )
                        answer.pendingActions.forEach { NoteActionView(it, showVersion = unread.size > 1) }
                    }
                }
            }
            items(answer.notes, key = { it.version }) { note ->
                val blocks = remember(note.html) { parseHtml(note.html) }
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(note.version, style = MaterialTheme.typography.titleMedium)
                        Text(note.date, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)
                        if (answer.unseen && note == answer.notes.first()) Chip("New", tone = ChipTone.Info)
                    }
                    Text(note.title, style = MaterialTheme.typography.titleSmall)
                    if (note.actions.isNotEmpty()) {
                        Text("To do", style = MaterialTheme.typography.labelLarge)
                        note.actions.forEach { NoteActionView(it) }
                    } else if (note.highlights.isNotEmpty()) {
                        // Only a server that sends the highlights says what to change.
                        Chip("Nothing to change", tone = ChipTone.Ok)
                    }
                    note.highlights.forEach { line ->
                        Text("★  $line", style = MaterialTheme.typography.bodyMedium)
                    }
                    HtmlContent(blocks)
                }
            }
        }
    }
}

/** One thing to change: its level, where it goes, and each line to copy. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun NoteActionView(action: NoteAction, showVersion: Boolean = false) {
    val copy = rememberCopy()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val tone = when (action.level) {
                "required" -> ChipTone.Miss
                "recommended" -> ChipTone.Partial
                else -> ChipTone.Info
            }
            Chip(action.level.replaceFirstChar { it.uppercase() }, tone = tone)
            if (showVersion && action.version.isNotEmpty()) Chip(action.version)
            if (action.file.isNotEmpty()) Chip(action.file)
        }
        Text(action.`when`, style = MaterialTheme.typography.titleSmall)
        Text(action.`do`, style = MaterialTheme.typography.bodyMedium, color = D2nColors.TextSoft)
        action.lines.forEach { line ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    line,
                    Modifier.weight(1f),
                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                )
                D2nButton("Copy", { copy("Setting", line, false) }, kind = ButtonKind.Ghost, small = true)
            }
        }
    }
}

@Composable
fun HelpScreen(vm: HelpViewModel, onBack: () -> Unit, onSection: (String) -> Unit) {
    val help by vm.help.collectAsStateWithLifecycle()
    ScreenScaffold(title = "Help", onBack = onBack, refreshing = help.refreshing, onRefresh = vm::refresh) {
        remote(help, onRetry = vm::refresh, skeletons = 6, skeletonHeight = 56.dp) { answer ->
            items(answer.sections, key = { it.id }) { section ->
                ListRow(title = section.title, onClick = { onSection(section.id) }, clickLabel = "Read")
            }
        }
    }
}

@Composable
fun HelpSectionScreen(vm: HelpViewModel, id: String, onBack: () -> Unit) {
    val help by vm.help.collectAsStateWithLifecycle()
    val section = help.value?.sections?.firstOrNull { it.id == id }
    ScreenScaffold(title = section?.title ?: "Help", onBack = onBack, refreshing = help.refreshing, onRefresh = vm::refresh) {
        remote(help, onRetry = vm::refresh, skeletons = 4, skeletonHeight = 80.dp) {
            if (section == null) {
                item { Text("This section is not on this server.", color = D2nColors.Muted) }
            } else {
                item(key = section.id) {
                    val blocks = remember(section.html) { parseHtml(section.html) }
                    GlassCard(Modifier.fillMaxWidth()) { HtmlContent(blocks) }
                }
            }
        }
    }
}
