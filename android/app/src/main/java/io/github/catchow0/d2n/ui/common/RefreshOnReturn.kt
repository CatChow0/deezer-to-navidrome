package io.github.catchow0.d2n.ui.common

import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.LifecycleStartEffect

/** Reads again when the screen comes back in front, not when it first opens. */
@Composable
fun RefreshOnReturn(vm: D2nViewModel, refresh: () -> Unit) {
    LifecycleResumeEffect(vm) {
        vm.onScreenResumed(refresh)
        onPauseOrDispose { }
    }
}

/** While the screen is in front, a task that ends makes it read again. */
@Composable
fun RefreshWhenTasksEnd(vm: D2nViewModel, refresh: () -> Unit) {
    LifecycleStartEffect(vm) {
        vm.watchTasks(refresh)
        onStopOrDispose { vm.stopWatchingTasks() }
    }
}
