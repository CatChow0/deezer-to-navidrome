package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.FlowRowScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.media
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes
import okhttp3.HttpUrl

/** The server the app talks to: links to its own media are read under it. */
val LocalServer = compositionLocalOf<HttpUrl?> { null }

/** Whether the server answers: actions that change something wait while it does not. */
val LocalOnline = compositionLocalOf { true }

/** A link from an answer, ready for Coil or the player. */
@Composable
fun mediaUrl(link: String?): String? {
    val server = LocalServer.current
    return if (server != null) server.media(link) else link?.takeIf { it.startsWith("http") }
}

/**
 * A cover: the picture, over the first letter of [label] on the aurora's
 * colors while it loads or when there is none. Decorative for TalkBack: the
 * title next to it says what it is.
 */
@Composable
fun Cover(link: String?, label: String, modifier: Modifier = Modifier, size: Dp = 56.dp, shape: Shape = D2nShapes.Control) {
    val url = mediaUrl(link)
    Box(
        modifier
            .size(size)
            .clip(shape)
            .background(Brush.linearGradient(listOf(D2nColors.Violet.copy(alpha = 0.45f), D2nColors.Magenta.copy(alpha = 0.3f)))),
        contentAlignment = Alignment.Center,
    ) {
        Text(label.trim().take(1).uppercase(), style = MaterialTheme.typography.titleMedium, color = D2nColors.TextSoft)
        if (url != null) {
            AsyncImage(model = url, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.matchParentSize())
        }
    }
}

/** Play or pause a preview. */
@Composable
fun PlayButton(playing: Boolean, label: String, onClick: () -> Unit, enabled: Boolean = true) {
    IconButton(onClick, enabled = enabled) {
        Box(
            Modifier.size(36.dp).clip(CircleShape).background(if (playing) D2nColors.Violet else D2nColors.GlassHover)
                .border(1.dp, D2nColors.LineStrong, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                painterResource(if (playing) R.drawable.ic_pause else R.drawable.ic_play),
                contentDescription = if (playing) "Pause" else label,
                Modifier.size(20.dp),
                tint = D2nColors.Text,
            )
        }
    }
}

/**
 * A row of a list on glass: [leading] (a cover, a number), the title and what
 * it is, chips under them, and [trailing] actions. A tap opens it; a long
 * press shows its actions.
 */
@OptIn(ExperimentalFoundationApi::class, ExperimentalLayoutApi::class)
@Composable
fun ListRow(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    leading: (@Composable () -> Unit)? = null,
    chips: (@Composable FlowRowScope.() -> Unit)? = null,
    trailing: @Composable RowScope.() -> Unit = {},
    onClick: (() -> Unit)? = null,
    onLongClick: (() -> Unit)? = null,
    clickLabel: String? = null,
) {
    val shape = D2nShapes.Tile
    Row(
        modifier
            .fillMaxWidth()
            .clip(shape)
            .background(D2nColors.Glass)
            .border(1.dp, D2nColors.Line, shape)
            .then(
                if (onClick != null || onLongClick != null) {
                    Modifier.combinedClickable(onClickLabel = clickLabel, onLongClick = onLongClick, onClick = onClick ?: {})
                } else {
                    Modifier
                },
            )
            .padding(start = 10.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        leading?.invoke()
        Column(Modifier.weight(1f).padding(vertical = 2.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (!subtitle.isNullOrBlank()) {
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            if (chips != null) {
                FlowRow(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    chips()
                }
            }
        }
        trailing()
    }
}

/** The web's small E of an explicit track or album. */
@Composable
fun ExplicitMark() = Chip("E", tone = ChipTone.Idle)

/** "3:42" from seconds. */
fun formatDuration(seconds: Number?): String {
    val total = seconds?.toLong() ?: return ""
    if (total <= 0) return ""
    val hours = total / 3600
    val minutes = (total % 3600) / 60
    val rest = total % 60
    return if (hours > 0) "$hours:%02d:%02d".format(minutes, rest) else "$minutes:%02d".format(rest)
}

/** "1 track", "2 tracks". */
fun plural(count: Int, word: String): String = "$count $word${if (count == 1) "" else "s"}"
