package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

enum class BannerTone(val text: Color, val background: Color, val line: Color) {
    Info(D2nColors.Info, D2nColors.InfoBg, D2nColors.InfoLine),
    Warn(D2nColors.Partial, D2nColors.PartialBg, D2nColors.PartialLine),
    Error(D2nColors.Miss, D2nColors.MissBg, D2nColors.MissLine),
}

/** A message in the page, with an optional action (Retry, Update…). */
@Composable
fun Banner(
    message: String,
    tone: BannerTone,
    modifier: Modifier = Modifier,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    Row(
        modifier
            .fillMaxWidth()
            .background(tone.background, D2nShapes.Control)
            .border(1.dp, tone.line, D2nShapes.Control)
            .padding(start = 14.dp, end = 6.dp, top = 10.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(message, Modifier.weight(1f).padding(end = 8.dp), color = tone.text, style = MaterialTheme.typography.bodySmall)
        if (actionLabel != null && onAction != null) {
            TextButton(onAction, colors = ButtonDefaults.textButtonColors(contentColor = D2nColors.Text)) { Text(actionLabel) }
        }
    }
}
