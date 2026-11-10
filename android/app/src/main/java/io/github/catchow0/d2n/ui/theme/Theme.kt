package io.github.catchow0.d2n.ui.theme

import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color

private val scheme = darkColorScheme(
    primary = D2nColors.Violet,
    onPrimary = Color.White,
    secondary = D2nColors.Cyan,
    onSecondary = D2nColors.Ink,
    tertiary = D2nColors.Magenta,
    background = D2nColors.Ink,
    onBackground = D2nColors.Text,
    surface = D2nColors.Ink2,
    onSurface = D2nColors.Text,
    surfaceVariant = D2nColors.GlassStrong,
    onSurfaceVariant = D2nColors.Muted,
    surfaceContainer = D2nColors.GlassStrong,
    surfaceContainerHigh = D2nColors.Ink2,
    outline = D2nColors.LineStrong,
    outlineVariant = D2nColors.Line,
    error = D2nColors.Danger,
    onError = Color.White,
)

/** Dark only, like the web. The screens draw on the aurora, not on a
 * Surface: the text color is given here, or Compose would draw it black. */
@Composable
fun D2nTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = scheme, typography = D2nTypography, shapes = D2nMaterialShapes) {
        CompositionLocalProvider(LocalContentColor provides D2nColors.Text, content = content)
    }
