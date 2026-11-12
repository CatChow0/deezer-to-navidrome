package io.github.catchow0.d2n.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import io.github.catchow0.d2n.AppGraph
import io.github.catchow0.d2n.data.StoredSession
import io.github.catchow0.d2n.ui.common.Motion
import io.github.catchow0.d2n.ui.main.MainScaffold
import io.github.catchow0.d2n.ui.signin.FirstPasswordScreen
import io.github.catchow0.d2n.ui.signin.FirstPasswordViewModel
import io.github.catchow0.d2n.ui.signin.ForgotScreen
import io.github.catchow0.d2n.ui.signin.ForgotViewModel
import io.github.catchow0.d2n.ui.signin.ServerScreen
import io.github.catchow0.d2n.ui.signin.ServerViewModel
import io.github.catchow0.d2n.ui.signin.SetupScreen
import io.github.catchow0.d2n.ui.signin.SetupViewModel
import io.github.catchow0.d2n.ui.signin.SignInScreen
import io.github.catchow0.d2n.ui.signin.SignInViewModel
import io.github.catchow0.d2n.ui.signin.probeServer
import io.github.catchow0.d2n.ui.theme.D2nColors
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
object ServerRoute

@Serializable
object SignInRoute

@Serializable
object SetupRoute

@Serializable
object MainRoute

@Serializable
object FirstPasswordRoute

@Serializable
object ForgotRoute

/** Where the app opens: the server, sign-in, or inside. */
fun startOf(session: StoredSession): Any = when {
    session.serverUrl == null -> ServerRoute
    session.token == null && !session.authDisabled -> SignInRoute
    else -> MainRoute
}

private fun NavHostController.goTo(route: Any) = navigate(route) { popUpTo(graph.id) { inclusive = true } }

@Composable
fun Navigation(graph: AppGraph) {
    val session by graph.store.state.collectAsStateWithLifecycle()
    if (!session.ready) {
        Box(Modifier.fillMaxSize().background(D2nColors.Ink))
        return
    }
    val start = remember { startOf(session) }
    val nav = rememberNavController()
    // Why the phone is back on Sign-in, when the server signed it out.
    var notice by rememberSaveable { mutableStateOf<String?>(null) }
    NavHost(
        nav,
        startDestination = start,
        enterTransition = { Motion.popIn },
        exitTransition = { Motion.fadeAway },
        popEnterTransition = { Motion.fadeBack },
        popExitTransition = { Motion.popOut },
    ) {
        composable<ServerRoute> {
            ServerScreen(viewModel { ServerViewModel({ probeServer(graph.bareClient, it) }, graph.store) }) { next ->
                nav.goTo(
                    when (next) {
                        ServerViewModel.Next.SignIn -> SignInRoute
                        ServerViewModel.Next.Setup -> SetupRoute
                        ServerViewModel.Next.Main -> MainRoute
                    },
                )
            }
        }
        composable<SignInRoute> {
            SignInScreen(
                viewModel { SignInViewModel(graph::requireApi, graph.store, graph.defaultDevice) },
                server = session.serverUrl,
                notice = notice,
                onNext = { next ->
                    notice = null
                    nav.goTo(
                        when (next) {
                            SignInViewModel.Next.Setup -> SetupRoute
                            SignInViewModel.Next.FirstPassword -> FirstPasswordRoute
                            SignInViewModel.Next.Main -> MainRoute
                        },
                    )
                },
                onOtherServer = { nav.goTo(ServerRoute) },
                onForgot = { nav.navigate(ForgotRoute) },
            )
        }
        composable<ForgotRoute> {
            ForgotScreen(viewModel { ForgotViewModel(graph::requireApi) }, onBack = { nav.goTo(SignInRoute) })
        }
        composable<FirstPasswordRoute> {
            FirstPasswordScreen(
                viewModel { FirstPasswordViewModel(graph::requireApi, graph.store, graph.defaultDevice) },
                onDone = { nav.goTo(MainRoute) },
                onSignOut = {
                    graph.scope.launch { graph.store.setToken(null) }
                    nav.goTo(SignInRoute)
                },
            )
        }
        composable<SetupRoute> {
            SetupScreen(
                viewModel { SetupViewModel(graph::requireApi, graph.store, graph.defaultDevice) },
                server = session.serverUrl,
                onNext = { nav.goTo(MainRoute) },
                onOtherServer = { nav.goTo(ServerRoute) },
            )
        }
        composable<MainRoute> {
            MainScaffold(
                graph,
                onSignedOut = { message ->
                    notice = message
                    nav.goTo(SignInRoute)
                },
                onOtherServer = { nav.goTo(ServerRoute) },
                onMustChange = { nav.goTo(FirstPasswordRoute) },
            )
        }
    }
}
