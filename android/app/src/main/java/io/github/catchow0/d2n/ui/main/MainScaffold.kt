package io.github.catchow0.d2n.ui.main

import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.navigation
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import io.github.catchow0.d2n.AppGraph
import io.github.catchow0.d2n.R
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.ui.about.AboutScreen
import io.github.catchow0.d2n.ui.about.AboutViewModel
import io.github.catchow0.d2n.ui.activity.ActivityScreen
import io.github.catchow0.d2n.ui.activity.ActivityViewModel
import io.github.catchow0.d2n.ui.activity.TaskScreen
import io.github.catchow0.d2n.ui.activity.TaskViewModel
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Motion
import io.github.catchow0.d2n.ui.common.ScreenDeps
import io.github.catchow0.d2n.ui.components.FitText
import io.github.catchow0.d2n.ui.components.Aurora
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone
import io.github.catchow0.d2n.ui.components.Brand
import io.github.catchow0.d2n.ui.components.EmptyState
import io.github.catchow0.d2n.ui.components.LocalOnline
import io.github.catchow0.d2n.ui.components.LocalServer
import io.github.catchow0.d2n.ui.components.MiniPlayer
import io.github.catchow0.d2n.ui.components.ScreenScaffold
import io.github.catchow0.d2n.ui.dashboard.DashboardScreen
import io.github.catchow0.d2n.ui.dashboard.DashboardViewModel
import io.github.catchow0.d2n.ui.madeforyou.DeezerMixesScreen
import io.github.catchow0.d2n.ui.madeforyou.DeezerTab
import io.github.catchow0.d2n.ui.madeforyou.DeezerMixesViewModel
import io.github.catchow0.d2n.ui.madeforyou.MadeForYouScreen
import io.github.catchow0.d2n.ui.madeforyou.MadeForYouViewModel
import io.github.catchow0.d2n.ui.madeforyou.MixSettingsScreen
import io.github.catchow0.d2n.ui.playlists.NavidromePlaylistScreen
import io.github.catchow0.d2n.ui.playlists.NavidromePlaylistViewModel
import io.github.catchow0.d2n.ui.playlists.PlaylistScreen
import io.github.catchow0.d2n.ui.playlists.PlaylistViewModel
import io.github.catchow0.d2n.ui.search.AlbumScreen
import io.github.catchow0.d2n.ui.search.AlbumViewModel
import io.github.catchow0.d2n.ui.search.ArtistScreen
import io.github.catchow0.d2n.ui.search.ArtistViewModel
import io.github.catchow0.d2n.ui.search.SearchScreen
import io.github.catchow0.d2n.ui.search.SearchViewModel
import io.github.catchow0.d2n.ui.releases.ReleasesScreen
import io.github.catchow0.d2n.ui.releases.ReleasesViewModel
import io.github.catchow0.d2n.ui.content.HelpScreen
import io.github.catchow0.d2n.ui.content.HelpSectionScreen
import io.github.catchow0.d2n.ui.content.HelpViewModel
import io.github.catchow0.d2n.ui.content.NotesScreen
import io.github.catchow0.d2n.ui.content.NotesViewModel
import io.github.catchow0.d2n.ui.settings.DeezerAccountsScreen
import io.github.catchow0.d2n.ui.settings.DeezerAccountsViewModel
import io.github.catchow0.d2n.ui.settings.DuplicatesScreen
import io.github.catchow0.d2n.ui.settings.DuplicatesViewModel
import io.github.catchow0.d2n.ui.settings.ListeningStatsScreen
import io.github.catchow0.d2n.ui.settings.ListeningStatsViewModel
import io.github.catchow0.d2n.ui.settings.MaintenanceScreen
import io.github.catchow0.d2n.ui.settings.MaintenanceViewModel
import io.github.catchow0.d2n.ui.settings.MusicSettingsScreen
import io.github.catchow0.d2n.ui.settings.MusicSettingsViewModel
import io.github.catchow0.d2n.ui.settings.NavidromeAccountsScreen
import io.github.catchow0.d2n.ui.settings.NavidromeAccountsViewModel
import io.github.catchow0.d2n.ui.settings.ResetScreen
import io.github.catchow0.d2n.ui.settings.SecurityScreen
import io.github.catchow0.d2n.ui.settings.SecurityViewModel
import io.github.catchow0.d2n.ui.settings.SettingsHome
import io.github.catchow0.d2n.ui.settings.SettingsPage
import io.github.catchow0.d2n.ui.settings.UsersScreen
import io.github.catchow0.d2n.ui.settings.UsersViewModel
import io.github.catchow0.d2n.ui.share.resolveShared
import io.github.catchow0.d2n.ui.stats.RecapStory
import io.github.catchow0.d2n.ui.stats.RecapViewModel
import io.github.catchow0.d2n.ui.stats.StatsEntityScreen
import io.github.catchow0.d2n.ui.stats.StatsEntityViewModel
import io.github.catchow0.d2n.ui.stats.StatsScreen
import io.github.catchow0.d2n.ui.stats.StatsViewModel
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.update.UpdateBanner
import io.github.catchow0.d2n.ui.update.UpdateViewModel
import kotlin.reflect.KClass
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

// The five tabs of the design, each with its own back stack.
@Serializable object DashboardTab

@Serializable object MadeForYouTab

@Serializable object StatsTab

@Serializable object ReleasesTab

@Serializable object MoreTab

@Serializable object DashboardRoute

@Serializable object SearchRoute

@Serializable data class AlbumRoute(val id: String, val title: String)

@Serializable data class ArtistRoute(val id: String, val name: String)

@Serializable data class PlaylistRoute(val id: String)

@Serializable data class NavidromePlaylistRoute(val account: String, val id: String, val name: String)

@Serializable object MadeForYouRoute

@Serializable object MixSettingsRoute

/** From Deezer, opened on a [io.github.catchow0.d2n.ui.madeforyou.DeezerTab] (the Dashboard's Add a playlist). */
@Serializable data class DeezerMixesRoute(val tab: String = "Mixes")

@Serializable object StatsRoute

@Serializable object ReleasesRoute

@Serializable object MoreRoute

// Above the tabs: reached from any of them (the top bar, a snackbar).
@Serializable object ActivityRoute

@Serializable data class StatsEntityRoute(val kind: String, val id: Long)

@Serializable object SettingsRoute

/** A page of Settings, by its [SettingsPage] name. */
@Serializable data class SettingsPageRoute(val page: String)

@Serializable object DuplicatesRoute

@Serializable object NotesRoute

@Serializable object HelpRoute

@Serializable data class HelpSectionRoute(val id: String)

@Serializable data class TaskRoute(val id: String)

const val UNREACHABLE_BANNER = "Can't reach the server — showing saved data. Changes wait until it is back."

private data class Tab(val route: Any, val type: KClass<*>, val root: Any, val label: String, val icon: Int)

private val TABS = listOf(
    Tab(DashboardTab, DashboardTab::class, DashboardRoute, "Dashboard", R.drawable.ic_home),
    Tab(MadeForYouTab, MadeForYouTab::class, MadeForYouRoute, "Made for you", R.drawable.ic_sparkle),
    Tab(StatsTab, StatsTab::class, StatsRoute, "Stats", R.drawable.ic_chart),
    Tab(ReleasesTab, ReleasesTab::class, ReleasesRoute, "Releases", R.drawable.ic_calendar),
    Tab(MoreTab, MoreTab::class, MoreRoute, "More", R.drawable.ic_more),
)

/** How many tasks run: the badge on the top bar's Activity button. */
class RunningTasksViewModel(deps: ScreenDeps) : D2nViewModel(deps) {
    private val _running = MutableStateFlow(0)
    val running: StateFlow<Int> = _running
    private var polling: Job? = null

    init {
        // A task just started: count it at once.
        viewModelScope.launch { deps.events.notices.collect { if (it.taskId != null) poll() } }
    }

    /** Whether a newer version's notes wait to be read: the dot on More. */
    fun checkNotes() {
        viewModelScope.launch {
            try {
                deps.events.unseenNotes.value = call { notes() }.unseen
            } catch (e: ApiFailure) {
                // The dot waits for the next start.
            }
        }
    }

    fun start() {
        if (polling?.isActive == true) return
        polling = viewModelScope.launch {
            while (true) {
                poll()
                delay(10_000)
            }
        }
    }

    fun stop() {
        polling?.cancel()
        polling = null
    }

    private suspend fun poll() {
        try {
            _running.value = call { tasks() }.tasks.count { !it.done }
        } catch (e: ApiFailure) {
            // The banner says the server is gone; the count waits.
        }
    }
}

/** The tab a screen is in, -1 for one over all of them (an album, Activity…). */
private fun tabOf(entry: NavBackStackEntry): Int = TABS.indexOfFirst { tab -> entry.destination.hierarchy.any { it.hasRoute(tab.type) } }

/** 1 from a tab to one further right, -1 to one further left, 0 within a tab. */
private fun tabStep(from: NavBackStackEntry, to: NavBackStackEntry): Int {
    val a = tabOf(from)
    val b = tabOf(to)
    return if (a >= 0 && b >= 0) b.compareTo(a) else 0
}

private fun NavHostController.openTab(tab: Tab, current: Tab?) {
    if (tab == current) {
        // The tab again: back to its first screen.
        popBackStack(tab.root, inclusive = false)
        return
    }
    navigate(tab.route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/**
 * Inside the app: the top bar with Activity and the profile, the banners
 * (server lost, an update), the five tabs, the snackbar and the mini player.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MainScaffold(graph: AppGraph, onSignedOut: (notice: String?) -> Unit, onOtherServer: () -> Unit, onMustChange: () -> Unit = {}) {
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
    val tasks: RunningTasksViewModel = viewModel { RunningTasksViewModel(graph.screens) }
    val sessionState by session.state.collectAsStateWithLifecycle()
    val online by graph.reachability.online.collectAsStateWithLifecycle()
    val update by updates.state.collectAsStateWithLifecycle()
    val running by tasks.running.collectAsStateWithLifecycle()
    val now by graph.player.now.collectAsStateWithLifecycle()
    val unseenNotes by graph.events.unseenNotes.collectAsStateWithLifecycle()
    val shared by graph.sharedLink.collectAsStateWithLifecycle()
    val stored by graph.store.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var errorShown by remember { mutableStateOf(false) }

    // The server is back: read what could not be read.
    LaunchedEffect(online) { session.onOnline(online) }
    // A 401 from any call: this phone was signed out on the server.
    LaunchedEffect(Unit) { graph.unauthorized.collect { session.onUnauthorized() } }
    LaunchedEffect(sessionState.signedOutMessage) { sessionState.signedOutMessage?.let(onSignedOut) }
    LaunchedEffect(sessionState.mustChange) { if (sessionState.mustChange) onMustChange() }
    // Back in front: look for an update, and finish one waiting for the permission.
    LifecycleEventEffect(Lifecycle.Event.ON_START) {
        // Also the first time: profiles may have changed on the web meanwhile.
        session.onStart()
        updates.check()
        if (update.needsPermission) updates.install()
    }
    // Leaving the app pauses the preview: it never plays in the background.
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { graph.player.pause() }
    LifecycleStartEffect(tasks) {
        tasks.checkNotes()
        tasks.start()
        onStopOrDispose { tasks.stop() }
    }

    val inner = rememberNavController()
    val entry by inner.currentBackStackEntryAsState()
    var lastTab by rememberSaveable { mutableIntStateOf(0) }
    val inTab = TABS.indexOfFirst { tab -> entry?.destination?.hierarchy?.any { it.hasRoute(tab.type) } == true }
    if (inTab >= 0 && inTab != lastTab) lastTab = inTab
    val currentTab = TABS[if (inTab >= 0) inTab else lastTab]

    // Messages from the screens; a started task can be opened from here.
    LaunchedEffect(Unit) {
        graph.events.notices.collect { notice ->
            errorShown = notice.error
            val result = snackbar.showSnackbar(
                notice.message,
                actionLabel = if (notice.taskId != null) "View" else null,
                withDismissAction = notice.taskId == null,
                duration = if (notice.taskId != null || notice.error) SnackbarDuration.Long else SnackbarDuration.Short,
            )
            if (result == SnackbarResult.ActionPerformed && notice.taskId != null) inner.navigate(TaskRoute(notice.taskId))
        }
    }
    // A link shared from Deezer or Spotify: the dashboard offers to add it.
    // Its first screen, even from deeper in the tab (a playlist): it shows the Add sheet.
    LaunchedEffect(shared) {
        if (shared != null) {
            inner.openTab(TABS[0], null)
            inner.popBackStack(DashboardRoute, inclusive = false)
        }
    }

    val ime = WindowInsets.isImeVisible
    CompositionLocalProvider(LocalOnline provides online, LocalServer provides stored.serverUrl?.toHttpUrlOrNull()) {
        Aurora {
            Column(Modifier.fillMaxSize()) {
                Row(
                    Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 8.dp, top = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Brand(Modifier.weight(1f))
                    IconButton({ inner.navigate(ActivityRoute) { launchSingleTop = true } }) {
                        BadgedBox(badge = { if (running > 0) Badge(containerColor = D2nColors.Violet) { Text("$running") } }) {
                            Icon(
                                painterResource(R.drawable.ic_activity),
                                contentDescription = if (running > 0) "Activity, $running running" else "Activity",
                                tint = D2nColors.Text,
                            )
                        }
                    }
                    ProfilePicker(sessionState.profiles, sessionState.selected, session::select)
                }
                Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!online) {
                        Banner(UNREACHABLE_BANNER, BannerTone.Warn, actionLabel = "Retry", onAction = graph.reachability::retryNow)
                    }
                    UpdateBanner(update, updates)
                }
                Box(Modifier.weight(1f).imePadding()) {
                    Tabs(graph, inner, updates, sessionState, onSignedOut, onOtherServer, shared)
                    SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(12.dp)) { data ->
                        Snackbar(
                            data,
                            containerColor = D2nColors.Ink2,
                            contentColor = if (errorShown) D2nColors.Miss else D2nColors.Text,
                            actionColor = D2nColors.Cyan,
                            dismissActionContentColor = D2nColors.Muted,
                        )
                    }
                }
                if (!ime) {
                    now?.let { MiniPlayer(it, graph.player::toggle, graph.player::stop) }
                    NavigationBar(containerColor = D2nColors.GlassStrong) {
                        val colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = D2nColors.Text,
                            selectedTextColor = D2nColors.Text,
                            indicatorColor = D2nColors.Violet.copy(alpha = 0.35f),
                            unselectedIconColor = D2nColors.Muted,
                            unselectedTextColor = D2nColors.Muted,
                        )
                        // The tabs' names grow with the font up to 115 %, all alike: past that,
                        // five names no longer fit across a phone.
                        val fontScale = LocalDensity.current.fontScale
                        val tabLabel = MaterialTheme.typography.labelSmall.let { it.copy(fontSize = it.fontSize * (minOf(fontScale, 1.15f) / fontScale)) }
                        TABS.forEach { tab ->
                            NavigationBarItem(
                                selected = tab == currentTab,
                                onClick = { inner.openTab(tab, currentTab.takeIf { inTab >= 0 }) },
                                icon = {
                                    if (tab.route == MoreTab && unseenNotes) {
                                        BadgedBox(badge = { Badge(containerColor = D2nColors.Cyan) }) { Icon(painterResource(tab.icon), contentDescription = "New notes") }
                                    } else {
                                        Icon(painterResource(tab.icon), contentDescription = null)
                                    }
                                },
                                label = { FitText(tab.label, tabLabel, minSize = 8.sp) },
                                colors = colors,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Tabs(
    graph: AppGraph,
    inner: NavHostController,
    updates: UpdateViewModel,
    sessionState: SessionViewModel.UiState,
    onSignedOut: (String?) -> Unit,
    onOtherServer: () -> Unit,
    shared: String?,
) {
    val deps = graph.screens
    val unseenNotes by deps.events.unseenNotes.collectAsStateWithLifecycle()
    val back: () -> Unit = { inner.popBackStack() }
    val openPlaylist: (String) -> Unit = { inner.navigate(PlaylistRoute(it)) }
    val openSettings: (SettingsPage) -> Unit = { page -> inner.navigate(SettingsPageRoute(page.name)) }
    NavHost(
        inner,
        startDestination = DashboardTab,
        enterTransition = { tabStep(initialState, targetState).let { if (it != 0) Motion.slideIn(it) else Motion.popIn } },
        exitTransition = { tabStep(initialState, targetState).let { if (it != 0) Motion.slideOut(it) else Motion.fadeAway } },
        popEnterTransition = { tabStep(initialState, targetState).let { if (it != 0) Motion.slideIn(it) else Motion.fadeBack } },
        popExitTransition = { tabStep(initialState, targetState).let { if (it != 0) Motion.slideOut(it) else Motion.popOut } },
    ) {
        navigation<DashboardTab>(startDestination = DashboardRoute) {
            composable<DashboardRoute> {
                DashboardScreen(
                    viewModel { DashboardViewModel(deps) { resolveShared(it, graph.bareClient) } },
                    onSearch = { inner.navigate(SearchRoute) },
                    onOpenPlaylist = openPlaylist,
                    onOpenNavidrome = { account, id, name -> inner.navigate(NavidromePlaylistRoute(account, id, name)) },
                    shared = shared,
                    onSharedTaken = { graph.sharedLink.value = null },
                    onFromDeezer = { inner.navigate(DeezerMixesRoute(DeezerTab.Yours.name)) },
                )
            }
            composable<SearchRoute> {
                SearchScreen(
                    viewModel { SearchViewModel(deps) },
                    graph.player,
                    onBack = back,
                    onAlbum = { id, title -> inner.navigate(AlbumRoute(id, title)) },
                    onArtist = { id, name -> inner.navigate(ArtistRoute(id, name)) },
                )
            }
            composable<PlaylistRoute> { entry ->
                val route = entry.toRoute<PlaylistRoute>()
                PlaylistScreen(viewModel { PlaylistViewModel(deps, route.id) }, graph.player, onBack = back)
            }
            composable<NavidromePlaylistRoute> { entry ->
                val route = entry.toRoute<NavidromePlaylistRoute>()
                NavidromePlaylistScreen(viewModel { NavidromePlaylistViewModel(deps, route.account, route.id) }, route.name, onBack = back)
            }
        }
        navigation<MadeForYouTab>(startDestination = MadeForYouRoute) {
            composable<MadeForYouRoute> {
                MadeForYouScreen(
                    viewModel { MadeForYouViewModel(deps) },
                    graph.player,
                    onSettings = { inner.navigate(MixSettingsRoute) },
                    onOpenPlaylist = openPlaylist,
                )
            }
            composable<MixSettingsRoute> { MixSettingsScreen(viewModel { MadeForYouViewModel(deps) }, onBack = back) }
        }
        navigation<StatsTab>(startDestination = StatsRoute) {
            composable<StatsRoute> {
                var recap by rememberSaveable { mutableStateOf<List<String>?>(null) }
                StatsScreen(
                    viewModel { StatsViewModel(deps) },
                    graph.player,
                    onEntity = { kind, id -> inner.navigate(StatsEntityRoute(kind, id)) },
                    onRecap = { kind, key -> recap = listOf(kind, key) },
                    onSettings = { openSettings(SettingsPage.Listening) },
                )
                recap?.let { (kind, key) ->
                    RecapStory(viewModel(key = "recap-$kind-$key") { RecapViewModel(deps, kind, key) }, graph.player, onClose = { recap = null })
                }
            }
        }
        navigation<ReleasesTab>(startDestination = ReleasesRoute) {
            composable<ReleasesRoute> {
                ReleasesScreen(viewModel { ReleasesViewModel(deps) }, onAlbum = { id, title -> inner.navigate(AlbumRoute(id, title)) }, onSettings = { openSettings(SettingsPage.Deezer) })
            }
        }
        navigation<MoreTab>(startDestination = MoreRoute) {
            composable<MoreRoute> {
                AboutScreen(
                    viewModel { AboutViewModel(graph::requireApi, graph.store, graph.own) },
                    updates,
                    sessionState,
                    onSignedOut = { onSignedOut(null) },
                    onOtherServer = onOtherServer,
                    onActivity = { inner.navigate(ActivityRoute) },
                    onSettings = { inner.navigate(SettingsRoute) },
                    onNotes = { inner.navigate(NotesRoute) },
                    onHelp = { inner.navigate(HelpRoute) },
                    unseenNotes = unseenNotes,
                )
            }
            composable<SettingsRoute> { SettingsHome(sessionState.isAdmin, onBack = back, onPage = openSettings) }
            composable<SettingsPageRoute> { entry ->
                when (SettingsPage.valueOf(entry.toRoute<SettingsPageRoute>().page)) {
                    SettingsPage.Music -> MusicSettingsScreen(viewModel { MusicSettingsViewModel(deps) }, onBack = back)
                    SettingsPage.Navidrome -> NavidromeAccountsScreen(viewModel { NavidromeAccountsViewModel(deps) }, onBack = back)
                    SettingsPage.Deezer -> DeezerAccountsScreen(viewModel { DeezerAccountsViewModel(deps) }, onBack = back)
                    SettingsPage.Listening -> ListeningStatsScreen(viewModel { ListeningStatsViewModel(deps) }, onBack = back)
                    SettingsPage.Security -> SecurityScreen(viewModel { SecurityViewModel(deps) }, onBack = back)
                    SettingsPage.Maintenance -> MaintenanceScreen(viewModel { MaintenanceViewModel(deps) }, sessionState.isAdmin, onBack = back, onDuplicates = { inner.navigate(DuplicatesRoute) })
                    SettingsPage.Users -> UsersScreen(viewModel { UsersViewModel(deps) }, onBack = back)
                    SettingsPage.Reset -> ResetScreen(viewModel { MaintenanceViewModel(deps) }, onBack = back)
                }
            }
            composable<DuplicatesRoute> { DuplicatesScreen(viewModel { DuplicatesViewModel(deps) }, onBack = back) }
            composable<NotesRoute> { NotesScreen(viewModel { NotesViewModel(deps) }, onBack = back) }
            composable<HelpRoute> { HelpScreen(viewModel { HelpViewModel(deps) }, onBack = back, onSection = { inner.navigate(HelpSectionRoute(it)) }) }
            composable<HelpSectionRoute> { entry ->
                // The sections are read once, on the Help screen's ViewModel.
                val help = inner.previousBackStackEntry?.takeIf { it.destination.hasRoute(HelpRoute::class) }
                val vm: HelpViewModel = if (help != null) viewModel(help) { HelpViewModel(deps) } else viewModel { HelpViewModel(deps) }
                HelpSectionScreen(vm, entry.toRoute<HelpSectionRoute>().id, onBack = back)
            }
        }
        composable<DeezerMixesRoute> { entry ->
            DeezerMixesScreen(viewModel { DeezerMixesViewModel(deps) }, DeezerTab.valueOf(entry.toRoute<DeezerMixesRoute>().tab), onBack = back)
        }
        composable<AlbumRoute> { entry ->
            val route = entry.toRoute<AlbumRoute>()
            AlbumScreen(viewModel { AlbumViewModel(deps, route.id) }, graph.player, route.title, onBack = back)
        }
        composable<ArtistRoute> { entry ->
            val route = entry.toRoute<ArtistRoute>()
            ArtistScreen(viewModel { ArtistViewModel(deps, route.id) }, route.name, onBack = back, onAlbum = { id, title -> inner.navigate(AlbumRoute(id, title)) })
        }
        composable<StatsEntityRoute> { entry ->
            val route = entry.toRoute<StatsEntityRoute>()
            StatsEntityScreen(viewModel { StatsEntityViewModel(deps, route.kind, route.id) }, graph.player, onBack = back)
        }
        composable<ActivityRoute> {
            ActivityScreen(viewModel { ActivityViewModel(graph::requireApi, graph.reachability) }, onBack = back) { id -> inner.navigate(TaskRoute(id)) }
        }
        composable<TaskRoute> { entry ->
            val id = entry.toRoute<TaskRoute>().id
            val base = graph.base() ?: return@composable
            TaskScreen(
                viewModel { TaskViewModel({ url, task, after -> graph.taskFollower.follow(url, task, after) }, graph::requireApi, base, id) },
                onBack = back,
            )
        }
    }
}

