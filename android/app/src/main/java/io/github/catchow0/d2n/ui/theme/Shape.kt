package io.github.catchow0.d2n.ui.theme

import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

/** The web's radii: they grow with the surface. */
object D2nShapes {
    val Chip = CircleShape
    val Control = RoundedCornerShape(12.dp)
    val Tile = RoundedCornerShape(16.dp)
    val Cell = RoundedCornerShape(24.dp)
    val Panel = RoundedCornerShape(30.dp)
}

val D2nMaterialShapes = Shapes(
    small = D2nShapes.Control,
    medium = D2nShapes.Tile,
    large = D2nShapes.Cell,
    extraLarge = D2nShapes.Panel,
)
