package io.github.catchow0.d2n.ui.content

import io.github.catchow0.d2n.data.ContentNotesResponse
import io.github.catchow0.d2n.testutil.FakeD2nApi
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ContentViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    @Test
    fun `load notes`() {
        val api = FakeD2nApi().apply { onContentNotes = { ContentNotesResponse() } }
        val vm = ContentViewModel({ api })
        vm.loadNotes()
        assertEquals(0, vm.state.value.notes?.notes?.size)
    }
}