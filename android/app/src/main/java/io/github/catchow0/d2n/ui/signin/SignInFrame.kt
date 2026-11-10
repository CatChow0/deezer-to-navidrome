package io.github.catchow0.d2n.ui.signin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.ui.components.Aurora
import io.github.catchow0.d2n.ui.components.GlassCard

/** The web's sign-in page: one glass card in the middle of the aurora,
 * scrolling when the keyboard takes the room. */
@Composable
fun SignInFrame(content: @Composable ColumnScope.() -> Unit) {
    Aurora {
        BoxWithConstraints(Modifier.fillMaxSize().systemBarsPadding().imePadding()) {
            Column(
                Modifier
                    .verticalScroll(rememberScrollState())
                    .heightIn(min = maxHeight)
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 24.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                GlassCard(Modifier.fillMaxWidth().widthIn(max = 460.dp), content = content)
            }
        }
    }
}
