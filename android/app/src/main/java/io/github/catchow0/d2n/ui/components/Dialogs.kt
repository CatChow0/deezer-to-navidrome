package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.theme.D2nColors

/**
 * Asks before something that cannot be undone. With [typeToConfirm], the
 * button waits until that word is typed.
 */
@Composable
fun ConfirmDialog(
    title: String,
    text: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    danger: Boolean = true,
    typeToConfirm: String? = null,
) {
    var typed by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = D2nColors.Ink2,
        titleContentColor = D2nColors.Text,
        textContentColor = D2nColors.TextSoft,
        title = { Text(title, style = MaterialTheme.typography.titleMedium) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(text, style = MaterialTheme.typography.bodyMedium)
                if (typeToConfirm != null) {
                    D2nTextField(typed, { typed = it }, "Type $typeToConfirm to confirm", imeAction = androidx.compose.ui.text.input.ImeAction.Done)
                }
            }
        },
        confirmButton = {
            D2nButton(
                confirmLabel,
                {
                    onDismiss()
                    onConfirm()
                },
                kind = if (danger) ButtonKind.Danger else ButtonKind.Primary,
                enabled = typeToConfirm == null || typed.trim() == typeToConfirm,
                small = true,
            )
        },
        dismissButton = { D2nButton("Cancel", onDismiss, kind = ButtonKind.Ghost, small = true) },
    )
}

/** One choice of an [ActionSheet]. */
data class SheetAction(
    val label: String,
    val icon: Int? = null,
    val danger: Boolean = false,
    val enabled: Boolean = true,
    val onClick: () -> Unit,
)

/** The actions on one thing (a track, a playlist), from the bottom of the screen. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActionSheet(title: String, actions: List<SheetAction>, onDismiss: () -> Unit, subtitle: String? = null) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = D2nColors.Ink2, contentColor = D2nColors.Text) {
        Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(bottom = 12.dp)) {
            Column(Modifier.padding(horizontal = 24.dp, vertical = 4.dp)) {
                Text(title, Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                subtitle?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted, maxLines = 2) }
            }
            actions.forEach { action ->
                val color = when {
                    !action.enabled -> D2nColors.Faint
                    action.danger -> D2nColors.Miss
                    else -> D2nColors.Text
                }
                Row(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = 56.dp)
                        .clickable(enabled = action.enabled) {
                            onDismiss()
                            action.onClick()
                        }
                        .padding(horizontal = 24.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    if (action.icon != null) Icon(painterResource(action.icon), contentDescription = null, Modifier.size(22.dp), tint = color)
                    Text(action.label, style = MaterialTheme.typography.bodyLarge, color = color)
                }
            }
        }
    }
}
