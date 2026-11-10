package io.github.catchow0.d2n.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import io.github.catchow0.d2n.R

// Variable fonts: one file each, the weight set through its axis.
private fun variable(res: Int, weight: Int) =
    Font(res, FontWeight(weight), variationSettings = FontVariation.Settings(FontVariation.weight(weight)))

/** Titles, as the web's --font-display. */
val Unbounded = FontFamily(
    variable(R.font.unbounded, 500),
    variable(R.font.unbounded, 600),
    variable(R.font.unbounded, 700),
)

/** Everything else, as the web's --font-body. */
val InstrumentSans = FontFamily(
    variable(R.font.instrument_sans, 400),
    variable(R.font.instrument_sans, 500),
    variable(R.font.instrument_sans, 600),
)

// The web's type steps: 13, 15, 18, 24 and 36 px.
val D2nTypography = Typography(
    displaySmall = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(600), fontSize = 36.sp, lineHeight = 42.sp),
    headlineSmall = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(600), fontSize = 24.sp, lineHeight = 30.sp),
    titleLarge = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(600), fontSize = 20.sp, lineHeight = 26.sp),
    titleMedium = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(500), fontSize = 18.sp, lineHeight = 24.sp),
    titleSmall = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(600), fontSize = 15.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(400), fontSize = 16.sp, lineHeight = 23.sp),
    bodyMedium = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(400), fontSize = 15.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(400), fontSize = 13.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(600), fontSize = 15.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(500), fontSize = 13.sp, lineHeight = 18.sp),
    labelSmall = TextStyle(fontFamily = InstrumentSans, fontWeight = FontWeight(500), fontSize = 12.sp, lineHeight = 16.sp),
)
