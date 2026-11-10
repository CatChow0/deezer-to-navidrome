package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** The web's cell: translucent glass with a fine line around it. */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    shape: Shape = D2nShapes.Cell,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .clip(shape)
            .background(D2nColors.Glass)
            .border(1.dp, D2nColors.Line, shape)
            .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        content = content,
    )
}
