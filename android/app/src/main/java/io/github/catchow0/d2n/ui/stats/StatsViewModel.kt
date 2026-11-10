package io.github.catchow0.d2n.ui.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.StatsOverviewResponse
import io.github.catchow0.d2n.data.StatsPlaysResponse
import io.github.catchow0.d2n.data.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.time.temporal.WeekFields

data class StatsState(
    val period: String = "month",
    val key: String = "",
    val query: String = "",
    val page: Int = 1,
    val tz: String = "UTC",
    val loading: Boolean = false,
    val overview: StatsOverviewResponse? = null,
    val plays: StatsPlaysResponse? = null,
    val error: String? = null,
)

class StatsViewModel(private val api: () -> D2nApi) : ViewModel() {
    private val tz = java.util.TimeZone.getDefault().id
    private val _state = MutableStateFlow(StatsState(period = "month", key = monthKey(LocalDate.now(ZoneId.of(tz))), tz = tz))
    val state: StateFlow<StatsState> = _state.asStateFlow()

    init { loadOverview() }

    fun setPeriod(period: String) {
        _state.value = _state.value.copy(period = period, key = currentKey(period), overview = null)
        loadOverview()
    }

    fun prev() { _state.value = _state.value.copy(key = stepKey(_state.value.period, _state.value.key, -1)); loadOverview() }
    fun next() { _state.value = _state.value.copy(key = stepKey(_state.value.period, _state.value.key, 1)); loadOverview() }

    fun loadOverview() {
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            try {
                val resp = apiCall { api().statsOverview(period = s.period, key = s.key, tz = s.tz) }
                _state.value = _state.value.copy(loading = false, overview = resp)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }

    fun setQuery(q: String) { _state.value = _state.value.copy(query = q, page = 1); loadPlays() }

    fun setPage(p: Int) { _state.value = _state.value.copy(page = maxOf(1, p)); loadPlays() }

    fun loadPlays() {
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            try {
                val resp = apiCall { api().statsPlays(query = s.query.ifBlank { null }, page = s.page) }
                _state.value = _state.value.copy(loading = false, plays = resp)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = e.message ?: "Failed")
            }
        }
    }

    private fun currentKey(period: String): String {
        val now = LocalDate.now(ZoneId.of(tz))
        return when (period) {
            "week" -> weekKey(now)
            "month" -> monthKey(now)
            "year" -> yearKey(now)
            else -> ""
        }
    }

    private fun monthKey(d: LocalDate) = String.format("%04d-%02d", d.year, d.monthValue)
    private fun yearKey(d: LocalDate) = String.format("%04d", d.year)
    private fun weekKey(d: LocalDate): String {
        val wf = WeekFields.ISO
        val w = d.get(wf.weekOfWeekBasedYear())
        val y = d.get(wf.weekBasedYear())
        return String.format("%04d-W%02d", y, w)
    }

    private fun dateOfKey(period: String, key: String): LocalDate {
        return try {
            when (period) {
                "week" -> {
                    val parts = key.split("-W"); val y = parts[0].toInt(); val w = parts[1].toInt()
                    val fourth = LocalDate.of(y, 1, 4)
                    fourth.minusDays(((fourth.dayOfWeek.value + 6) % 7).toLong()).plusWeeks((w - 1).toLong())
                }
                "month" -> YearMonth.parse(key).atDay(1)
                "year" -> LocalDate.of(key.toInt(), 1, 1)
                else -> LocalDate.now(ZoneId.of(tz))
            }
        } catch (_: Exception) { LocalDate.now(ZoneId.of(tz)) }
    }

    private fun keyOfDate(period: String, date: LocalDate): String {
        return when (period) {
            "week" -> weekKey(date)
            "month" -> monthKey(date)
            "year" -> yearKey(date)
            else -> ""
        }
    }

    private fun stepKey(period: String, key: String, step: Int): String {
        val date = dateOfKey(period, key)
        val stepped = when (period) { "week" -> date.plusWeeks(step.toLong()); "month" -> date.plusMonths(step.toLong()); "year" -> date.plusYears(step.toLong()); else -> date }
        return keyOfDate(period, stepped)
    }
}