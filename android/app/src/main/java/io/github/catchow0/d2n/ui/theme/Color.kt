package io.github.catchow0.d2n.ui.theme

import androidx.compose.ui.graphics.Color

/** The web's colors (static/css/tokens.css), with their alpha in the high byte. */
object D2nColors {
    // The night sky the aurora is painted on
    val Ink = Color(0xFF07061A)
    val Ink2 = Color(0xFF0E0C26)

    // The aurora
    val Violet = Color(0xFF8B5CF6)
    val Magenta = Color(0xFFE0479E)
    val Cyan = Color(0xFF22D3EE)
    val Mint = Color(0xFF5EEAD4)

    // Text
    val Text = Color(0xFFEEEAF8)
    val TextSoft = Color(0xFFCFC9E6)
    val Muted = Color(0xFFA39FBF)
    val Faint = Color(0xFF6F6A8E)

    // Glass
    val Glass = Color(0x940E0C22)
    val GlassStrong = Color(0xD10C0A1E)
    val GlassRaised = Color(0x0DFFFFFF)
    val GlassHover = Color(0x14FFFFFF)
    val Line = Color(0x17FFFFFF)
    val LineStrong = Color(0x29FFFFFF)

    // States
    val Ok = Color(0xFF5EEAD4)
    val OkBg = Color(0x1F5EEAD4)
    val OkLine = Color(0x525EEAD4)
    val Miss = Color(0xFFFB7185)
    val MissBg = Color(0x1FFB7185)
    val MissLine = Color(0x57FB7185)
    val Partial = Color(0xFFFBBF24)
    val PartialBg = Color(0x1FFBBF24)
    val PartialLine = Color(0x52FBBF24)
    val Info = Color(0xFF7DD3FC)
    val InfoBg = Color(0x1F7DD3FC)
    val InfoLine = Color(0x527DD3FC)
    val Idle = Color(0xFFA39FBF)
    val IdleBg = Color(0x1FA39FBF)
    val IdleLine = Color(0x47A39FBF)
    val Danger = Color(0xFFF43F5E)
}
