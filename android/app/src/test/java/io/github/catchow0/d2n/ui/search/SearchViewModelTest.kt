package io.github.catchow0.d2n.ui.search

import io.github.catchow0.d2n.data.LibraryCheckResponse
import io.github.catchow0.d2n.data.LibraryCheckResult
import io.github.catchow0.d2n.data.SearchResponse
import io.github.catchow0.d2n.data.SearchResult
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class SearchViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `submit searches and records in-library badges`() {
        val api = FakeD2nApi().apply {
            onSearch = { _, _ -> SearchResponse(results = listOf(SearchResult(id = "1", type = "track", title = "Song", artist = "A"))) }
            onLibraryCheck = { _ -> LibraryCheckResponse(results = mapOf("track:1" to LibraryCheckResult(owned = true))) }
        }
        // FakeD2nApi has callback hooks names; ensure names below.
        val vm = SearchViewModel({ api })
        vm.onQuery("song")
        vm.submit()
        assertEquals(1, vm.state.value.results.size)
        assertTrue(vm.state.value.inLibrary["track:1"] == true)
    }
}