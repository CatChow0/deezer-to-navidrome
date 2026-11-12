package io.github.catchow0.d2n.ui

import io.github.catchow0.d2n.data.AddPlaylistAnswer
import io.github.catchow0.d2n.data.D2nJson
import io.github.catchow0.d2n.data.DeezerMixesAnswer
import io.github.catchow0.d2n.data.LinkRequest
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.testutil.TestDeps
import io.github.catchow0.d2n.ui.madeforyou.DeezerMixesViewModel
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/** From Deezer: the account's own playlists next to the mixes and recommendations. */
class FromDeezerViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private val answer = D2nJson.decodeFromString(
        DeezerMixesAnswer.serializer(),
        """{"ok": true, "mixes": [],
            "playlists": [{"id": "900", "title": "Chill", "group": "For you", "followed": false}],
            "yours": [{"id": "777", "title": "Loved Tracks", "group": "Loved tracks", "tracks": 412, "followed": false},
                      {"id": "900", "title": "Chill", "subtitle": "Deezer Editors", "group": "Favorites", "tracks": 80, "followed": false}]}""",
    )

    @Test
    fun `the account's own playlists read with their group and size`() {
        assertEquals(listOf("Loved tracks", "Favorites"), answer.yours.map { it.group })
        assertEquals(412, answer.yours.first().tracks)
        assertEquals("no list", D2nJson.decodeFromString(DeezerMixesAnswer.serializer(), """{"yours_error": "no list"}""").yoursError)
    }

    @Test
    fun `adding one of yours adds it as any playlist, marked wherever it shows`() = runTest(main.dispatcher) {
        val t = TestDeps(backgroundScope)
        t.reply("deezerMixes", answer)
        t.reply("addPlaylist", AddPlaylistAnswer(message = "Playlist added"))
        val vm = DeezerMixesViewModel(t.deps)
        vm.add(answer.yours[1])
        assertEquals(LinkRequest("900"), t.api.calls.first { it.first == "addPlaylist" }.second.single())
        val shown = vm.found.value.value!!
        assertTrue(shown.yours.first { it.id == "900" }.followed && shown.playlists.single().followed)
    }
}
