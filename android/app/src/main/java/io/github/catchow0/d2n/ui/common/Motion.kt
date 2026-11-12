package io.github.catchow0.d2n.ui.common

import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally

/** How screens change. Navigation's own default is a 700 ms fade, slow to the
 * eye: a screen opened pops in, and pops out on the way back; the tabs slide
 * toward the one chosen. */
object Motion {
    private const val SLIDE_MS = 260
    private const val POP_IN_MS = 200
    private const val POP_OUT_MS = 150

    val popIn: EnterTransition = fadeIn(tween(POP_IN_MS)) + scaleIn(tween(POP_IN_MS), initialScale = 0.92f)

    /** What a screen opened over does: it steps back quickly. */
    val fadeAway: ExitTransition = fadeOut(tween(POP_OUT_MS))

    /** Back again: what was under comes forward. */
    val fadeBack: EnterTransition = fadeIn(tween(POP_IN_MS))

    val popOut: ExitTransition = fadeOut(tween(POP_OUT_MS)) + scaleOut(tween(POP_OUT_MS), targetScale = 0.96f)

    /** [step] is 1 toward a tab further right, -1 toward one further left. */
    fun slideIn(step: Int): EnterTransition = slideInHorizontally(tween(SLIDE_MS)) { it * step }

    fun slideOut(step: Int): ExitTransition = slideOutHorizontally(tween(SLIDE_MS)) { -it * step }
}
