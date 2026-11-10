package io.github.catchow0.d2n

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import io.github.catchow0.d2n.ui.Navigation
import io.github.catchow0.d2n.ui.theme.D2nTheme

class MainActivity : ComponentActivity() {
    private val graph get() = (application as D2nApplication).graph

    override fun onCreate(savedInstanceState: Bundle?) {
        // The app is always dark: light icons on transparent bars, whatever the phone's theme.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) takeShared(intent)
        setContent { D2nTheme { Navigation(graph) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeShared(intent)
    }

    /** Share from Deezer or Spotify: the playlist's link, to add. */
    private fun takeShared(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND || intent.type?.startsWith("text/") != true) return
        intent.getStringExtra(Intent.EXTRA_TEXT)?.takeIf { it.isNotBlank() }?.let { graph.sharedLink.value = it }
    }
}
