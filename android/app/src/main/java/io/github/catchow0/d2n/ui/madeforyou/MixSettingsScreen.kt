package io.github.catchow0.d2n.ui.madeforyou

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.catchow0.d2n.data.MixSettings
import io.github.catchow0.d2n.data.MixSettingsChange
import io.github.catchow0.d2n.data.MixesAnswer
import io.github.catchow0.d2n.ui.common.formatGigabytes
import io.github.catchow0.d2n.ui.components.D2nButton
import io.github.catchow0.d2n.ui.components.GlassCard
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.NumberField
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.components.SectionHeader
import io.github.catchow0.d2n.ui.components.ToggleRow
import io.github.catchow0.d2n.ui.components.plural
import io.github.catchow0.d2n.ui.components.remote
import io.github.catchow0.d2n.ui.theme.D2nColors

/** Made for you's limits and trial rules, with the web's bounds. */
@Composable
fun MixSettingsScreen(vm: MadeForYouViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    ScreenScaffold(title = "Limits and trial rules", onBack = onBack, refreshing = state.refreshing, onRefresh = vm::refresh) {
        remote(state, onRetry = vm::refresh, skeletons = 3, skeletonHeight = 160.dp) { s ->
            item(key = "limits-${s.settings.hashCode()}") { Limits(s, saving = "settings" in busy, onSave = vm::saveLimits) }
            item(key = "trial-${s.settings.hashCode()}") { TrialRules(s, saving = "settings" in busy, onSave = vm::saveTrialRules) }
        }
    }
}

@Composable
private fun Group(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, Modifier.semantics { heading() }, style = MaterialTheme.typography.titleSmall)
        content()
    }
}

@Composable
private fun Note(text: String) = Text(text, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted)

@Composable
private fun Limits(state: MixesAnswer, saving: Boolean, onSave: (MixSettingsChange) -> Unit) {
    val start = state.settings
    var s by remember { mutableStateOf(start) }
    SectionHeader("Limits")
    GlassCard(Modifier.fillMaxWidth()) {
        Group("Refresh rate") {
            NumberField("Daily Mix / Daily Mix+ every (hours)", s.dailyHours, { s = s.copy(dailyHours = it) }, 1..9999)
            NumberField("Discover every (days)", s.discoverDays, { s = s.copy(discoverDays = it) }, 1..9999)
        }
        Group("Length") {
            NumberField("Tracks in each Daily Mix / Daily Mix+", s.mixSize, { s = s.copy(mixSize = it) }, 12..100)
            NumberField("Tracks in Discover", s.discoverSize, { s = s.copy(discoverSize = it) }, 1..9999)
        }
        Group("New tracks") {
            NumberField("New tracks in each Daily Mix+ (%)", s.blendNewPercent, { s = s.copy(blendNewPercent = it) }, 1..90)
            Note("Daily Mix+ only. Unheard tracks on trial take these places before anything new is downloaded.")
        }
        Group("Disk limit") {
            NumberField("Stop downloading at this many unheard tracks", s.maxUnheard, { s = s.copy(maxUnheard = it) }, 1..99999)
            NumberField("Stop downloading at this quarantine size (GB)", s.maxTrialGb, { s = s.copy(maxTrialGb = it) }, 1..99999)
            Note(
                "In quarantine now${if (state.profile.several) ", every profile together" else ""}: " +
                    "${formatGigabytes(state.usage.bytes)}, ${plural(state.usage.unheard, "unheard track")}." +
                    if (state.profile.several) " The same for every profile: they share the disk." else "",
            )
        }
        Note("New values apply from the next refresh.")
        D2nButton(
            if (saving) "Saving…" else "Save limits",
            {
                onSave(
                    MixSettingsChange(
                        dailyHours = s.dailyHours, discoverDays = s.discoverDays, mixSize = s.mixSize, discoverSize = s.discoverSize,
                        blendNewPercent = s.blendNewPercent, maxUnheard = s.maxUnheard, maxTrialGb = s.maxTrialGb,
                    ),
                )
            },
            Modifier.fillMaxWidth(),
            enabled = !saving && LocalOnline.current && s != start,
        )
    }
}

@Composable
private fun TrialRules(state: MixesAnswer, saving: Boolean, onSave: (MixSettingsChange) -> Unit) {
    val start: MixSettings = state.settings
    var s by remember { mutableStateOf(start) }
    val auto = s.trialAuto
    SectionHeader("Trial")
    GlassCard(Modifier.fillMaxWidth()) {
        Group("Automatic validation") {
            ToggleRow("Decide about tracks on trial with the rules below", auto, { s = s.copy(trialAuto = it) })
            Note("Off: tracks stay on trial until you keep or remove them. The trash still empties itself.")
        }
        Group("Durations") {
            NumberField("Days on trial", s.trialDays, { s = s.copy(trialDays = it) }, 1..365, enabled = auto)
            NumberField("Days in the trash", s.trashDays, { s = s.copy(trashDays = it) }, 1..365)
            Note("A new length also applies to tracks already there.")
        }
        Group("Rules") {
            ToggleRow("Delete permanently after the trial period ends", s.trialDelete, { s = s.copy(trialDelete = it) }, enabled = auto)
            ToggleRow("Bypass user review", s.trialBypass, { s = s.copy(trialBypass = it) }, enabled = auto)
            NumberField("Plays to validate a track", s.trialPlays, { s = s.copy(trialPlays = it) }, 1..50, enabled = auto)
            ToggleRow("Starred or rated 4-5 in Navidrome counts", s.trialMarks, { s = s.copy(trialMarks = it) }, enabled = auto)
            if (!state.navidromeMounted) Note("Navidrome's database is not mounted at /import/navidrome, so stars and ratings cannot be read.")
        }
        Note("Rules apply at once to the tracks already in quarantine.")
        D2nButton(
            if (saving) "Saving…" else "Save trial rules",
            {
                // Every field, the greyed ones too: turning validation off keeps the rules.
                onSave(
                    MixSettingsChange(
                        trialAuto = s.trialAuto, trialDays = s.trialDays, trashDays = s.trashDays, trialDelete = s.trialDelete,
                        trialBypass = s.trialBypass, trialPlays = s.trialPlays, trialMarks = s.trialMarks,
                    ),
                )
            },
            Modifier.fillMaxWidth(),
            enabled = !saving && LocalOnline.current && s != start,
        )
    }
}
