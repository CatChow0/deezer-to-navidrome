package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.res.painterResource
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
    small: Boolean = false,
    icon: Int? = null,
) {
    val padding = if (small) PaddingValues(horizontal = 12.dp, vertical = 6.dp) else PaddingValues(horizontal = 18.dp, vertical = 12.dp)
    val label: @Composable () -> Unit = {
        if (icon != null) {
            Icon(painterResource(icon), contentDescription = null, Modifier.size(if (small) 16.dp else 18.dp))
            Spacer(Modifier.width(6.dp))
        }
        Text(text, style = if (small) MaterialTheme.typography.labelMedium else MaterialTheme.typography.labelLarge)
    }
    when (kind) {
        ButtonKind.Primary -> Button(
            onClick, modifier, enabled, shape = D2nShapes.Control, contentPadding = padding,
            colors = ButtonDefaults.buttonColors(
                containerColor = D2nColors.Text, contentColor = D2nColors.Ink,
                disabledContainerColor = D2nColors.GlassHover, disabledContentColor = D2nColors.Faint,
            ),
        ) { label() }
        ButtonKind.Danger -> Button(
            onClick, modifier, enabled, shape = D2nShapes.Control, contentPadding = padding,
            colors = ButtonDefaults.buttonColors(containerColor = D2nColors.Danger, contentColor = Color.White),
        ) { label() }
        ButtonKind.Ghost -> OutlinedButton(
            onClick, modifier, enabled, shape = D2nShapes.Control, contentPadding = padding,
            border = BorderStroke(1.dp, D2nColors.LineStrong),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = D2nColors.Text),
        ) { label() }
        ButtonKind.Link -> TextButton(
            onClick, modifier, enabled,
            colors = ButtonDefaults.textButtonColors(contentColor = D2nColors.Muted),
        ) { label() }
    }
}
