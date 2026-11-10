package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.takeOrElse
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp

/**
 * One line of text that shrinks to fit when the room runs out, as it does
 * with a large font: a number never breaks in two ("1,89 / 4"), a tab's name
 * is never cut. At the usual sizes it shows at [style]'s size; it never gets
 * smaller than [minSize] at the usual font scale.
 */
@Composable
fun FitText(
    text: AnnotatedString,
    style: TextStyle,
    modifier: Modifier = Modifier,
    color: Color = Color.Unspecified,
    minSize: TextUnit = 9.sp,
) {
    // [minSize] is the size at the usual font scale: sp grow with the user's font, and
    // a floor that grew with it would never let the text shrink at 200 %.
    val floor = (minSize.value / LocalDensity.current.fontScale).sp
    // BasicText does not read the theme's content color as Material's Text does.
    val shown = style.copy(color = color.takeOrElse { style.color.takeOrElse { LocalContentColor.current } })
    BasicText(
        text,
        modifier,
        style = shown,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        autoSize = TextAutoSize.StepBased(minFontSize = floor, maxFontSize = style.fontSize, stepSize = 0.5.sp),
    )
}

@Composable
fun FitText(text: String, style: TextStyle, modifier: Modifier = Modifier, color: Color = Color.Unspecified, minSize: TextUnit = 9.sp) =
    FitText(AnnotatedString(text), style, modifier, color, minSize)
