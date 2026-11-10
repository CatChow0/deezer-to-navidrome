package io.github.catchow0.d2n.ui.components

import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.os.PersistableBundle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

/**
 * Copies text. [sensitive] (a token) keeps it out of the clipboard's preview
 * on Android 13 and later.
 */
@Composable
fun rememberCopy(): (label: String, text: String, sensitive: Boolean) -> Unit {
    val context = LocalContext.current
    return remember(context) {
        { label, text, sensitive ->
            val clip = ClipData.newPlainText(label, text)
            if (sensitive && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                clip.description.extras = PersistableBundle().apply { putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true) }
            }
            context.getSystemService(Context.CLIPBOARD_SERVICE).let { it as ClipboardManager }.setPrimaryClip(clip)
        }
    }
}
