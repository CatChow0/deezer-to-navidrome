package io.github.catchow0.d2n.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** A placeholder that breathes while something loads. */
@Composable
fun Skeleton(modifier: Modifier = Modifier) {
    val pulse by rememberInfiniteTransition(label = "skeleton").animateFloat(
        initialValue = 0.45f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(900), RepeatMode.Reverse),
        label = "skeleton alpha",
    )
    Box(modifier.alpha(pulse).background(D2nColors.GlassHover, D2nShapes.Tile))
}
