package io.github.catchow0.d2n.ui.update

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import io.github.catchow0.d2n.ui.components.Banner
import io.github.catchow0.d2n.ui.components.BannerTone

/** The app's update, under the top bar: offered, downloading, waiting for the
 * permission or the confirmation, or failed. Each state has its way forward. */
@Composable
fun UpdateBanner(state: UpdateViewModel.UiState, vm: UpdateViewModel, modifier: Modifier = Modifier) {
    val offer = state.offer
    val progress = state.progress
    when {
        state.needsPermission -> Banner(
            "Allow D2N to install apps: the update is ready to install.", BannerTone.Warn, modifier,
            actionLabel = "Allow", onAction = vm::openInstallSettings,
        )
        progress != null -> Banner("Downloading the update… ${(progress * 100).toInt()} %", BannerTone.Info, modifier)
        state.error != null -> if (state.downloaded != null) {
            Banner(state.error, BannerTone.Error, modifier, actionLabel = "Install", onAction = vm::install)
        } else {
            Banner(state.error, BannerTone.Error, modifier, actionLabel = "Try again", onAction = vm::download)
        }
        state.confirmation != null -> Banner(
            "The update is ready to install.", BannerTone.Info, modifier,
            actionLabel = "Install", onAction = vm::confirm,
        )
        state.installing -> Banner("Installing the update…", BannerTone.Info, modifier)
        state.downloaded != null -> Banner(
            "The update is downloaded.", BannerTone.Info, modifier,
            actionLabel = "Install", onAction = vm::install,
        )
        offer != null -> Banner(
            "Version ${offer.version} is ready.", BannerTone.Info, modifier,
            actionLabel = "Update", onAction = vm::download,
        )
    }
}
