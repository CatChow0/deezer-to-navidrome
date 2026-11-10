package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** The web's segmented buttons: one choice among a few, scrolling sideways when long. */
@Composable
fun <T> SegmentedTabs(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        options.forEach { (key, label) ->
            val on = key == selected
            Box(
                Modifier
                    .heightIn(min = 40.dp)
                    .clip(D2nShapes.Chip)
                    .background(if (on) D2nColors.Violet.copy(alpha = 0.35f) else D2nColors.GlassRaised)
                    .border(1.dp, if (on) D2nColors.Violet else D2nColors.LineStrong, D2nShapes.Chip)
                    .selectable(selected = on, role = Role.Tab, onClick = { onSelect(key) })
                    .padding(horizontal = 16.dp, vertical = 9.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(label, style = MaterialTheme.typography.labelLarge, color = if (on) D2nColors.Text else D2nColors.TextSoft)
            }
        }
    }
}

private val fieldColors
    @Composable get() = OutlinedTextFieldDefaults.colors(
        focusedTextColor = D2nColors.Text,
        unfocusedTextColor = D2nColors.Text,
        focusedContainerColor = D2nColors.GlassRaised,
        unfocusedContainerColor = D2nColors.GlassRaised,
        focusedBorderColor = D2nColors.Violet,
        unfocusedBorderColor = D2nColors.LineStrong,
        focusedLabelColor = D2nColors.Violet,
        unfocusedLabelColor = D2nColors.Muted,
        cursorColor = D2nColors.Violet,
    )

/** A search box: the keyboard's Search key runs [onSearch]; × clears it. */
@Composable
fun SearchField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    onSearch: () -> Unit = {},
    onClear: (() -> Unit)? = null,
) {
    val focus = LocalFocusManager.current
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth(),
        singleLine = true,
        placeholder = { Text(placeholder, color = D2nColors.Faint) },
        leadingIcon = { Icon(painterResource(R.drawable.ic_search), contentDescription = null, tint = D2nColors.Muted) },
        trailingIcon = if (value.isNotEmpty()) {
            {
                IconAction(R.drawable.ic_close, "Clear", { onValueChange(""); onClear?.invoke() }, tint = D2nColors.Muted)
            }
        } else {
            null
        },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search, autoCorrectEnabled = false),
        keyboardActions = KeyboardActions(onSearch = {
            focus.clearFocus()
            onSearch()
        }),
        shape = D2nShapes.Control,
        colors = fieldColors,
    )
}

/** A whole number, with its unit in the label. A value out of [range] is not sent. */
@Composable
fun NumberField(label: String, value: Int, onValueChange: (Int) -> Unit, range: IntRange, modifier: Modifier = Modifier, enabled: Boolean = true) {
    var text by remember(value) { mutableStateOf(value.toString()) }
    val number = text.toIntOrNull()
    OutlinedTextField(
        value = text,
        onValueChange = { typed ->
            text = typed.filter(Char::isDigit).take(6)
            text.toIntOrNull()?.takeIf { it in range }?.let(onValueChange)
        },
        modifier = modifier.fillMaxWidth(),
        enabled = enabled,
        singleLine = true,
        label = { Text(label) },
        isError = number == null || number !in range,
        supportingText = if (number == null || number !in range) {
            { Text("From ${range.first} to ${range.last}", color = D2nColors.Miss) }
        } else {
            null
        },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
        shape = D2nShapes.Control,
        colors = fieldColors,
    )
}

/** A setting that is on or off, the whole row toggling it. */
@Composable
fun ToggleRow(title: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier, description: String? = null, enabled: Boolean = true) {
    Row(
        modifier
            .fillMaxWidth()
            .clip(D2nShapes.Control)
            .toggleable(value = checked, enabled = enabled, role = Role.Switch, onValueChange = onCheckedChange)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, color = if (enabled) D2nColors.Text else D2nColors.Faint)
            description?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted) }
        }
        Switch(
            checked = checked,
            onCheckedChange = null,
            enabled = enabled,
            colors = SwitchDefaults.colors(
                checkedThumbColor = D2nColors.Text,
                checkedTrackColor = D2nColors.Violet,
                uncheckedThumbColor = D2nColors.Muted,
                uncheckedTrackColor = D2nColors.GlassHover,
                uncheckedBorderColor = D2nColors.LineStrong,
            ),
        )
    }
}

/** One value among a list, from a menu, as the web's <select>. */
@Composable
fun <T> ChoiceField(label: String, options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    var open by remember { mutableStateOf(false) }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = D2nColors.Muted)
        Box {
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .clip(D2nShapes.Control)
                    .background(D2nColors.GlassRaised)
                    .border(1.dp, D2nColors.LineStrong, D2nShapes.Control)
                    .clickable(enabled = enabled, role = Role.DropdownList, onClickLabel = label) { open = true }
                    .padding(horizontal = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(options.firstOrNull { it.first == selected }?.second ?: "—", Modifier.weight(1f), color = if (enabled) D2nColors.Text else D2nColors.Faint)
                Text("▾", color = D2nColors.Muted)
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = D2nColors.Ink2) {
                options.forEach { (key, text) ->
                    DropdownMenuItem(
                        text = { Text(text, color = if (key == selected) D2nColors.Cyan else D2nColors.Text) },
                        onClick = {
                            open = false
                            onSelect(key)
                        },
                    )
                }
            }
        }
    }
}

/** A figure and what it counts, as the web's library figures. */
@Composable
fun StatTile(value: String, label: String, modifier: Modifier = Modifier) {
    Column(
        modifier
            .clip(D2nShapes.Tile)
            .background(D2nColors.GlassRaised)
            .border(1.dp, D2nColors.Line, D2nShapes.Tile)
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Text(value, style = MaterialTheme.typography.titleLarge)
        Text(label, style = MaterialTheme.typography.labelMedium, color = D2nColors.Muted)
    }
}
