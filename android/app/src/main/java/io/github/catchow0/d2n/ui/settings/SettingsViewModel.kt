package io.github.catchow0.d2n.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.SettingsResponse
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.data.ClearSettingsResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.contentOrNull

data class SettingsState(
    val loading: Boolean = false,
    val settings: JsonObject = JsonObject(emptyMap()),
    val choices: JsonObject? = null,
    val working: Map<String, Any?> = emptyMap(),
    val message: String? = null,
    val error: String? = null,
)

class SettingsViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val _state = MutableStateFlow(SettingsState())
    val state: StateFlow<SettingsState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val resp: SettingsResponse = apiCall { api().settings() }
                _state.value = SettingsState(loading = false, settings = resp.settings, choices = resp.choices, working = (resp.settings.asAny() as? Map<String, Any?>) ?: emptyMap(), message = _state.value.message)
            } catch (e: Exception) { _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed") }
        }
    }

    fun choose(key: String, value: Any?) {
        val s = _state.value
        val working = s.working + (key to value)
        _state.value = s.copy(working = working)
        save(working)
    }

    fun cycle(key: String) {
        val choices = (_state.value.choices?.get(key) as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.asInt() } ?: return
        val current = _state.value.working[key] as? Number
        val currentIndex = choices.indexOf(current?.toInt() ?: choices.firstOrNull())
        val next = if (currentIndex < 0 || currentIndex == choices.lastIndex) choices.firstOrNull() else choices[currentIndex + 1]
        if (next != null) choose(key, next)
    }

    private fun save(values: Map<String, Any?>) {
        viewModelScope.launch {
            try { val resp: SettingsResponse = apiCall { api().saveSettings(values) }; _state.value = settingsState(resp, _state.value.message) } catch (e: Exception) { _state.value = _state.value.copy(error = e.message ?: "Failed") }
        }
    }

    fun clear(what: String) {
        viewModelScope.launch {
            try { val resp: ClearSettingsResponse = apiCall { api().clearSettings(what) }; _state.value = _state.value.copy(message = resp.message, error = null) } catch (e: Exception) { _state.value = _state.value.copy(error = e.message ?: "Failed") }
        }
    }

    fun JsonElement.asAny(): Any? = when (this) {
        is JsonObject -> entries.associate { (k, v) -> k to v.asAny() }
        is JsonArray -> map { it.asAny() }
        is JsonPrimitive -> when { isString -> contentOrNull; booleanOrNull != null -> booleanOrNull; doubleOrNull != null -> doubleOrNull; else -> contentOrNull }
        else -> null
    }
    private fun JsonPrimitive.asInt() = doubleOrNull?.toInt() ?: contentOrNull?.toIntOrNull()
    private fun settingsState(resp: SettingsResponse, message: String?) = SettingsState(loading = false, settings = resp.settings, choices = resp.choices, working = (resp.settings.asAny() as? Map<String, Any?>) ?: emptyMap(), message = message ?: _state.value.message)
}