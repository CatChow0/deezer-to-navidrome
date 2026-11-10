package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** The web's state chips. */
enum class ChipTone(val text: Color, val background: Color, val line: Color) {
    Ok(D2nColors.Ok, D2nColors.OkBg, D2nColors.OkLine),
    Miss(D2nColors.Miss, D2nColors.MissBg, D2nColors.MissLine),
    Partial(D2nColors.Partial, D2nColors.PartialBg, D2nColors.PartialLine),
    Info(D2nColors.Info, D2nColors.InfoBg, D2nColors.InfoLine),
    Idle(D2nColors.Idle, D2nColors.IdleBg, D2nColors.IdleLine),
}

@Composable
fun Chip(text: String, modifier: Modifier = Modifier, tone: ChipTone = ChipTone.Idle) {
    Text(
        text,
        modifier
            .background(tone.background, D2nShapes.Chip)
            .border(1.dp, tone.line, D2nShapes.Chip)
            .padding(horizontal = 10.dp, vertical = 3.dp),
        color = tone.text,
        style = MaterialTheme.typography.labelSmall,
    )
}
