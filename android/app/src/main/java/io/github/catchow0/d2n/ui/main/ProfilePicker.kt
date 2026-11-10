package io.github.catchow0.d2n.ui.main

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.catchow0.d2n.data.Profile
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** The profile this phone shows: the Navidrome account its requests are about. */
@Composable
fun ProfilePicker(profiles: List<Profile>, selected: Profile?, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedButton(
            onClick = { open = true },
            enabled = profiles.isNotEmpty(),
            shape = D2nShapes.Chip,
            border = BorderStroke(1.dp, D2nColors.LineStrong),
            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = D2nColors.Text),
        ) {
            Text("${selected?.label ?: "Profile"}  ▾", style = MaterialTheme.typography.labelLarge)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = D2nColors.Ink2) {
            profiles.forEach { profile ->
                DropdownMenuItem(
                    text = {
                        Text(
                            profile.label + if (profile.isDefault) " · default" else "",
                            color = if (profile.id == selected?.id) D2nColors.Cyan else D2nColors.Text,
                        )
                    },
                    onClick = {
                        open = false
                        onSelect(profile.id)
                    },
                )
            }
        }
    }
}
