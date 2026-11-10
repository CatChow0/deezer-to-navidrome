package io.github.catchow0.d2n.ui.stats

import io.github.catchow0.d2n.data.StatsOverviewResponse
import io.github.catchow0.d2n.data.StatsPlaysResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class StatsViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `loads overview and plays`() {
        val api = FakeD2nApi().apply {
            onStatsOverview = { _, _, _ -> StatsOverviewResponse(totals = io.github.catchow0.d2n.data.StatsTotals(plays = 3)) }
            onStatsPlays = { _, _ -> StatsPlaysResponse() }
        }
        val vm = StatsViewModel({ api })
        vm.loadOverview()
        assertEquals(3, vm.state.value.overview?.totals?.plays)
        vm.loadPlays()
        assertEquals(0, vm.state.value.plays?.plays?.size)
    }
}
