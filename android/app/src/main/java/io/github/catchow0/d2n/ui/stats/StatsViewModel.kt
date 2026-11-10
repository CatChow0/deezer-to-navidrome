package io.github.catchow0.d2n.ui.stats

import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.PlaysPage
import io.github.catchow0.d2n.data.Recap
import io.github.catchow0.d2n.data.RecapIndex
import io.github.catchow0.d2n.data.StatsEntity
import io.github.catchow0.d2n.data.StatsOverview
import io.github.catchow0.d2n.ui.common.D2nViewModel
import io.github.catchow0.d2n.ui.common.Remote
import io.github.catchow0.d2n.ui.common.ScreenDeps
import java.time.LocalDate
import java.time.YearMonth
import java.time.temporal.IsoFields
import java.util.TimeZone
import kotlinx.coroutines.Job
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The periods of the web's Stats: a key names one of each ("2026-W45", "2026-11", "2026"). */
enum class Period(val api: String, val label: String) { Week("week", "Week"), Month("month", "Month"), Year("year", "Year"), All("all", "All time") }

object PeriodKeys {
    fun of(period: Period, date: LocalDate): String = when (period) {
        Period.Week -> "%04d-W%02d".format(date.get(IsoFields.WEEK_BASED_YEAR), date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR))
        Period.Month -> "%04d-%02d".format(date.year, date.monthValue)
        Period.Year -> "%04d".format(date.year)
        Period.All -> ""
    }

    /** The first day of the period [key] names. */
    fun dateOf(period: Period, key: String): LocalDate? = runCatching {
        when (period) {
            Period.Week -> {
                val (year, week) = key.split("-W").map(String::toInt)
                LocalDate.of(year, 1, 4)
                    .with(IsoFields.WEEK_OF_WEEK_BASED_YEAR, week.toLong())
                    .with(java.time.DayOfWeek.MONDAY)
            }
            Period.Month -> YearMonth.parse(key).atDay(1)
            Period.Year -> LocalDate.of(key.toInt(), 1, 1)
            Period.All -> null
        }
    }.getOrNull()

    fun step(period: Period, key: String, by: Long): String {
        val date = dateOf(period, key) ?: return key
        return of(
            period,
            when (period) {
                Period.Week -> date.plusWeeks(by)
                Period.Month -> date.plusMonths(by)
                Period.Year -> date.plusYears(by)
                Period.All -> date
            },
        )
    }

    /** The oldest key worth showing: the month of the first play, in this period. */
    fun earliest(period: Period, oldestMonth: String?): String? {
        oldestMonth ?: return null
        return when (period) {
            Period.Month -> oldestMonth
            Period.Year -> oldestMonth.take(4)
            Period.Week -> dateOf(Period.Month, oldestMonth)?.let { of(Period.Week, it) }
            Period.All -> null
        }
    }
}

/** "3 h 12 min", "45 min": the web's way. */
fun listening(seconds: Long): String {
    val minutes = ((seconds + 30) / 60).toInt()
    val hours = minutes / 60
    return when {
        hours == 0 -> "$minutes min"
        minutes % 60 == 0 -> "%,d h".format(hours)
        else -> "%,d h %d min".format(hours, minutes % 60)
    }
}

class StatsViewModel(deps: ScreenDeps, private val today: () -> LocalDate = LocalDate::now) : D2nViewModel(deps) {
    val tz: String = TimeZone.getDefault().id

    data class Choice(val period: Period, val key: String)

    private val _choice = MutableStateFlow(Choice(Period.Month, PeriodKeys.of(Period.Month, today())))
    val choice: StateFlow<Choice> = _choice

    private val _overview = MutableStateFlow(Remote<StatsOverview>())
    val overview: StateFlow<Remote<StatsOverview>> = _overview

    private val _index = MutableStateFlow(Remote<RecapIndex>())
    val index: StateFlow<Remote<RecapIndex>> = _index

    private val _hero = MutableStateFlow<Recap?>(null)

    /** The latest complete month's recap, for the card at the top. */
    val hero: StateFlow<Recap?> = _hero

    private val _query = MutableStateFlow("")
    val query: StateFlow<String> = _query

    private val _plays = MutableStateFlow(Remote<PlaysPage>())
    val plays: StateFlow<Remote<PlaysPage>> = _plays

    private var reading: Job? = null
    private var searching: Job? = null
    private var page = 1

    init {
        followProfile { load() }
    }

    private suspend fun load() = coroutineScope {
        launch { loadIndex() }
        launch { readOverview() }
        launch { readPlays() }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    private suspend fun loadIndex() {
        _index.fill { recaps(tz) }
        val latest = _index.value.value?.latestComplete
        _hero.value = latest?.let {
            try {
                call { recap("month", it, tz) }
            } catch (e: ApiFailure) {
                null
            }
        }
    }

    private suspend fun readOverview() {
        val asked = _choice.value
        _overview.fill { statsOverview(asked.period.api, asked.key, tz) }
    }

    fun setPeriod(period: Period) {
        if (period == _choice.value.period) return
        _choice.value = Choice(period, PeriodKeys.of(period, today()))
        reread()
    }

    /** One period back or on, within the history and never past now. */
    fun step(by: Long) {
        val current = _choice.value
        if (!canStep(by)) return
        _choice.value = current.copy(key = PeriodKeys.step(current.period, current.key, by))
        reread()
    }

    fun canStep(by: Long): Boolean {
        val (period, key) = _choice.value
        if (period == Period.All) return false
        val date = PeriodKeys.dateOf(period, key) ?: return false
        return if (by < 0) {
            val earliest = PeriodKeys.earliest(period, _index.value.value?.months?.lastOrNull()?.key)
                ?.let { PeriodKeys.dateOf(period, it) } ?: return false
            date.isAfter(earliest)
        } else {
            date.isBefore(PeriodKeys.dateOf(period, PeriodKeys.of(period, today())))
        }
    }

    private fun reread() {
        // A slower answer for a period already left never replaces the new one.
        reading?.cancel()
        reading = viewModelScope.launch { readOverview() }
    }

    /** The plays matching [text], a moment after typing stops. */
    fun search(text: String) {
        _query.value = text
        page = 1
        searching?.cancel()
        searching = viewModelScope.launch {
            delay(SEARCH_DELAY_MILLIS)
            readPlays()
        }
    }

    fun page(to: Int) {
        page = to.coerceAtLeast(1)
        searching?.cancel()
        searching = viewModelScope.launch { readPlays() }
    }

    private suspend fun readPlays() {
        val text = _query.value.trim()
        val asked = page
        _plays.fill { plays(text, asked) }
    }

    private companion object {
        const val SEARCH_DELAY_MILLIS = 300L
    }
}

/** An artist, an album or a track of the history. */
class StatsEntityViewModel(deps: ScreenDeps, private val kind: String, private val id: Long) : D2nViewModel(deps) {
    private val tz = TimeZone.getDefault().id
    private val _entity = MutableStateFlow(Remote<StatsEntity>())
    val entity: StateFlow<Remote<StatsEntity>> = _entity

    init {
        followProfile { _entity.fill { statsEntity(kind, id, tz) } }
    }

    fun refresh() {
        viewModelScope.launch { _entity.fill { statsEntity(kind, id, tz) } }
    }
}

/** One recap, played as a story. */
class RecapViewModel(deps: ScreenDeps, private val kind: String, private val key: String) : D2nViewModel(deps) {
    private val tz = TimeZone.getDefault().id
    private val _recap = MutableStateFlow(Remote<Recap>())
    val recap: StateFlow<Remote<Recap>> = _recap

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _recap.update { it.copy(loading = true) }
            _recap.fill { recap(kind, key, tz) }
        }
    }
}
