package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import io.github.catchow0.d2n.ui.theme.D2nColors
import kotlin.math.max

/**
 * The web's background: an aurora of soft violet, magenta, cyan and mint
 * glows on the night ink. It is static, to spare the battery. Over it,
 * translucent glass looks like blurred glass, so there is no backdrop blur.
 */
@Composable
fun Aurora(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    Box(modifier.fillMaxSize().background(D2nColors.Ink)) {
        Canvas(Modifier.fillMaxSize()) {
            val reach = max(size.width, size.height)
            glow(D2nColors.Violet, Offset(size.width * 0.15f, size.height * 0.08f), reach * 0.75f, 0.42f)
            glow(D2nColors.Magenta, Offset(size.width * 0.95f, size.height * 0.22f), reach * 0.55f, 0.30f)
            glow(D2nColors.Cyan, Offset(size.width * 0.05f, size.height * 0.78f), reach * 0.6f, 0.26f)
            glow(D2nColors.Mint, Offset(size.width * 0.9f, size.height * 0.98f), reach * 0.5f, 0.20f)
            // The web's vignette: the edges sink back into the night.
            drawRect(
                Brush.radialGradient(
                    0.4f to Color.Transparent, 1f to Color(0x8C050412),
                    center = Offset(size.width / 2, size.height * 0.4f), radius = reach * 0.9f,
                ),
            )
        }
        content()
    }
}

private fun DrawScope.glow(color: Color, center: Offset, radius: Float, alpha: Float) =
    drawCircle(
        Brush.radialGradient(listOf(color.copy(alpha = alpha), Color.Transparent), center = center, radius = radius),
        radius = radius,
        center = center,
    )
