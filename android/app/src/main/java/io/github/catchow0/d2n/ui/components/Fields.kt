package io.github.catchow0.d2n.ui.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.sp
import io.github.catchow0.d2n.ui.theme.D2nColors
import io.github.catchow0.d2n.ui.theme.D2nShapes

/** "Deezer → Navidrome", as at the top of the web's pages. */
@Composable
fun Brand(modifier: Modifier = Modifier) {
    FitText(
        buildAnnotatedString {
            append("Deezer ")
            withStyle(SpanStyle(color = D2nColors.Cyan)) { append("→") }
            append(" Navidrome")
        },
        MaterialTheme.typography.titleMedium,
        modifier,
        color = D2nColors.Text,
        minSize = 12.sp,
    )
}

/** The web's form field: a label, the value, and a hint under it. */
@Composable
fun D2nTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    supporting: String? = null,
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    onIme: () -> Unit = {},
    enabled: Boolean = true,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth(),
        enabled = enabled,
        singleLine = true,
        label = { Text(label) },
        placeholder = placeholder?.let { { Text(it, color = D2nColors.Faint) } },
        supportingText = supporting?.let { { Text(it, color = D2nColors.Muted) } },
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (password) KeyboardType.Password else keyboardType,
            imeAction = imeAction,
            autoCorrectEnabled = false,
        ),
        keyboardActions = KeyboardActions(onAny = { onIme() }),
        shape = D2nShapes.Control,
        colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = D2nColors.Text,
            unfocusedTextColor = D2nColors.Text,
            focusedContainerColor = D2nColors.GlassRaised,
            unfocusedContainerColor = D2nColors.GlassRaised,
            focusedBorderColor = D2nColors.Violet,
            unfocusedBorderColor = D2nColors.LineStrong,
            focusedLabelColor = D2nColors.Violet,
            unfocusedLabelColor = D2nColors.Muted,
            cursorColor = D2nColors.Violet,
        ),
    )
}
