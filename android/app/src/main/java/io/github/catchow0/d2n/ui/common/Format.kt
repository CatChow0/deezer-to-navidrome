package io.github.catchow0.d2n.ui.common

import java.text.DateFormat
import java.util.Date
import kotlin.math.roundToInt

/** "just now", "5 min ago", "3 h ago", or the date: as the web says it. */
fun ago(epochSeconds: Double?, now: Long = System.currentTimeMillis()): String {
    if (epochSeconds == null || epochSeconds <= 0) return ""
    val minutes = ((now / 1000.0 - epochSeconds) / 60).roundToInt()
    return when {
        minutes < 1 -> "just now"
        minutes < 60 -> "$minutes min ago"
        minutes < 60 * 24 -> "${(minutes / 60.0).roundToInt()} h ago"
        else -> DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date((epochSeconds * 1000).toLong()))
    }
}

/** "every 30 min", "every 6 h", "every 2 d". */
fun formatInterval(minutes: Int): String = when {
    minutes >= 1440 && minutes % 1440 == 0 -> "every ${minutes / 1440} d"
    minutes >= 60 -> "every ${minutes / 60} h" + (minutes % 60).let { if (it > 0) " $it" else "" }
    else -> "every $minutes min"
}

/** "1.4 GB", in the web's way: one decimal. */
fun formatGigabytes(bytes: Long): String = "%.1f GB".format(bytes / (1024.0 * 1024 * 1024))
