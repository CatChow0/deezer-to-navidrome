package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.theme.D2nColors

/** An icon that does something: 48 dp to touch, and its [label] for TalkBack. */
@Composable
fun IconAction(icon: Int, label: String, onClick: () -> Unit, enabled: Boolean = true, tint: Color = D2nColors.Text) {
    IconButton(onClick, enabled = enabled) {
        Icon(painterResource(icon), contentDescription = label, tint = if (enabled) tint else D2nColors.Faint)
    }
}

/**
 * A screen: its title (with Back on a screen inside a tab), its actions, then
 * a list that can be pulled to refresh.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenScaffold(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
    refreshing: Boolean = false,
    onRefresh: (() -> Unit)? = null,
    state: LazyListState = rememberLazyListState(),
    /** Stays under the list: the actions of a long one. */
    bottomBar: (@Composable () -> Unit)? = null,
    content: LazyListScope.() -> Unit,
) {
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(start = if (onBack != null) 4.dp else 16.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (onBack != null) IconAction(R.drawable.ic_back, "Back", onBack)
            Text(
                title,
                Modifier.weight(1f).semantics { heading() },
                style = if (onBack == null) MaterialTheme.typography.headlineSmall else MaterialTheme.typography.titleLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            actions()
        }
        val list: @Composable () -> Unit = {
            LazyColumn(
                Modifier.fillMaxSize(),
                state = state,
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                content = content,
            )
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (onRefresh != null) {
                PullToRefreshBox(isRefreshing = refreshing, onRefresh = onRefresh, modifier = Modifier.fillMaxSize()) { list() }
            } else {
                list()
            }
        }
        bottomBar?.invoke()
    }
}

/** A part of a screen: its title, what it is for, and an action. */
@Composable
fun SectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    action: (@Composable RowScope.() -> Unit)? = null,
) {
    Column(modifier.fillMaxWidth().padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, Modifier.weight(1f).semantics { heading() }, style = MaterialTheme.typography.titleMedium)
            action?.invoke(this)
        }
        subtitle?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = D2nColors.Muted) }
    }
}

/** Nothing to show yet, and what would fill it. */
@Composable
fun EmptyState(message: String, modifier: Modifier = Modifier, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    GlassCard(modifier.fillMaxWidth()) {
        Text(message, color = D2nColors.Muted, style = MaterialTheme.typography.bodyMedium)
        if (actionLabel != null && onAction != null) D2nButton(actionLabel, onAction, kind = ButtonKind.Ghost, small = true)
    }
}

/**
 * What a [Remote] holds, in a list: skeletons while the first read runs, the
 * error with Retry when it failed, else [content] (with the last error above,
 * when a refresh failed but older data is there).
 */
fun <T> LazyListScope.remote(
    remote: Remote<T>,
    onRetry: () -> Unit,
    skeletons: Int = 3,
    skeletonHeight: Dp = 72.dp,
    content: LazyListScope.(T) -> Unit,
) {
    val value = remote.value
    when {
        value != null -> {
            remote.error?.let { error ->
                item(key = "remote-error") { Banner(error, BannerTone.Error, actionLabel = "Retry", onAction = onRetry) }
            }
            content(value)
        }
        remote.loading -> items(skeletons, key = { "skeleton-$it" }) {
            Skeleton(Modifier.fillMaxWidth().height(skeletonHeight))
        }
        else -> item(key = "remote-error") {
            Banner(remote.error ?: "Nothing to show.", BannerTone.Error, actionLabel = "Retry", onAction = onRetry)
        }
    }
}
