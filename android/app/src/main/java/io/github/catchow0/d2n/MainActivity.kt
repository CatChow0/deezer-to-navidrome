package io.github.catchow0.d2n

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import io.github.catchow0.d2n.ui.Navigation
import io.github.catchow0.d2n.ui.theme.D2nTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // The app is always dark: light icons on transparent bars, whatever the phone's theme.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        val graph = (application as D2nApplication).graph
        setContent { D2nTheme { Navigation(graph) } }
    }
}
