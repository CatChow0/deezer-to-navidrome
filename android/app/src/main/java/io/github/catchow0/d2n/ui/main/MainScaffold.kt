package io.github.catchow0.d2n.ui.main

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import io.github.catchow0.d2n.AppGraph
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.ui.about.AboutScreen
import io.github.catchow0.d2n.ui.about.AboutViewModel
import io.github.catchow0.d2n.ui.activity.ActivityScreen
import io.github.catchow0.d2n.ui.activity.ActivityViewModel
import io.github.catchow0.d2n.ui.activity.TaskScreen
import io.github.catchow0.d2n.ui.activity.TaskViewModel
import io.github.catchow0.d2n.ui.components.Aurora
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.Brand
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.update.UpdateBanner
import io.github.catchow0.d2n.ui.update.UpdateViewModel
import kotlinx.serialization.Serializable

@Serializable
object ActivityRoute

@Serializable
data class TaskRoute(val id: String)

@Serializable
object AboutRoute

const val UNREACHABLE_BANNER = "Can't reach the server."

/**
 * Inside the app: the top bar with the profile, the banners (server lost, an
 * update), and two destinations until phase 7: Activity and More.
 */
@Composable
fun MainScaffold(graph: AppGraph, onSignedOut: (notice: String?) -> Unit, onOtherServer: () -> Unit) {
    val session: SessionViewModel = viewModel { SessionViewModel(graph::requireApi, graph.store) }
    val updates: UpdateViewModel = viewModel {
        UpdateViewModel(
            check = graph.updateChecker::check,
            download = graph.downloader::download,
            installer = graph.installer,
            base = graph::base,
            dir = graph.updatesDir,
            enabled = graph.updatesEnabled,
        )
    }
    val sessionState by session.state.collectAsStateWithLifecycle()
    val online by graph.reachability.online.collectAsStateWithLifecycle()
    val update by updates.state.collectAsStateWithLifecycle()

    // The server is back: read what could not be read.
    LaunchedEffect(online) { session.onOnline(online) }
    // A 401 from any call: this phone was signed out on the server.
    LaunchedEffect(Unit) { graph.unauthorized.collect { session.onUnauthorized() } }
    LaunchedEffect(sessionState.signedOutMessage) { sessionState.signedOutMessage?.let(onSignedOut) }
    // Back in front: look for an update, and finish one waiting for the permission.
    LifecycleEventEffect(Lifecycle.Event.ON_START) {
        // Also the first time: profiles may have changed on the web meanwhile.
        session.onStart()
        updates.check()
        if (update.needsPermission) updates.install()
    }

    val inner = rememberNavController()
    val entry by inner.currentBackStackEntryAsState()
    val onMore = entry?.destination?.hasRoute<AboutRoute>() == true

    Aurora {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 12.dp, top = 8.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Brand(Modifier.weight(1f))
                ProfilePicker(sessionState.profiles, sessionState.selected, session::select)
            }
            Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!online) {
                    Banner(UNREACHABLE_BANNER, BannerTone.Warn, actionLabel = "Retry", onAction = graph.reachability::retryNow)
                }
                UpdateBanner(update, updates)
            }
            Box(Modifier.weight(1f)) {
                NavHost(inner, startDestination = ActivityRoute) {
                    composable<ActivityRoute> {
                        ActivityScreen(viewModel { ActivityViewModel(graph::requireApi, graph.reachability) }) { id ->
                            inner.navigate(TaskRoute(id))
                        }
                    }
                    composable<TaskRoute> { back ->
                        val id = back.toRoute<TaskRoute>().id
                        val base = graph.base() ?: return@composable
                        TaskScreen(
                            viewModel(key = "task-$id") {
                                TaskViewModel({ url, task, after -> graph.taskFollower.follow(url, task, after) }, graph::requireApi, base, id)
                            },
                            onBack = { inner.popBackStack() },
                        )
                    }
                    composable<AboutRoute> {
                        AboutScreen(
                            viewModel { AboutViewModel(graph::requireApi, graph.store, graph.own) },
                            updates,
                            sessionState,
                            onSignedOut = { onSignedOut(null) },
                            onOtherServer = onOtherServer,
                        )
                    }
                }
            }
            NavigationBar(containerColor = D2nColors.GlassStrong) {
                val colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = D2nColors.Text,
                    selectedTextColor = D2nColors.Text,
                    indicatorColor = D2nColors.Violet.copy(alpha = 0.35f),
                    unselectedIconColor = D2nColors.Muted,
                    unselectedTextColor = D2nColors.Muted,
                )
                NavigationBarItem(
                    selected = !onMore,
                    onClick = { inner.navigate(ActivityRoute) { popUpTo(inner.graph.id) { inclusive = true } } },
                    icon = { Icon(painterResource(R.drawable.ic_activity), contentDescription = null) },
                    label = { Text("Activity") },
                    colors = colors,
                )
                NavigationBarItem(
                    selected = onMore,
                    onClick = { inner.navigate(AboutRoute) { launchSingleTop = true } },
                    icon = { Icon(painterResource(R.drawable.ic_more), contentDescription = null) },
                    label = { Text("More") },
                    colors = colors,
                )
            }
        }
    }
}
