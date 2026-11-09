package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** The web's .btn (light), .btn--ghost, .btn--danger and a plain link. */
enum class ButtonKind { Primary, Ghost, Danger, Link }

@Composable
fun D2nButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    kind: ButtonKind = ButtonKind.Primary,
    enabled: Boolean = true,
) {
    val padding = PaddingValues(horizontal = 18.dp, vertical = 12.dp)
    when (kind) {
        ButtonKind.Primary -> Button(
            onClick, modifier, enabled, shape = D2nShapes.Control, contentPadding = padding,
            colors = ButtonDefaults.buttonColors(
                containerColor = D2nColors.Text, contentColor = D2nColors.Ink,
                disabledContainerColor = D2nColors.GlassHover, disabledContentColor = D2nColors.Faint,
            ),
        ) { Text(text) }
        ButtonKind.Danger -> Button(
            onClick, modifier, enabled, shape = D2nShapes.Control, contentPadding = padding,
            colors = ButtonDefaults.buttonColors(containerColor = D2nColors.Danger, contentColor = Color.White),
        ) { Text(text) }
        ButtonKind.Ghost -> OutlinedButton(
            onClick, modifier, enabled, shape = D2nShapes.Control, contentPadding = padding,
            border = BorderStroke(1.dp, D2nColors.LineStrong),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = D2nColors.Text),
        ) { Text(text) }
        ButtonKind.Link -> TextButton(
            onClick, modifier, enabled,
            colors = ButtonDefaults.textButtonColors(contentColor = D2nColors.Muted),
        ) { Text(text) }
    }
}
