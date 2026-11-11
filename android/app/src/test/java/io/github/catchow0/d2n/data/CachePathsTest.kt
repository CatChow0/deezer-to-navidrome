package io.github.catchow0.d2n.data

import io.github.catchow0.d2n.ui.content.decodeEntities
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CachePathsTest {
    @Test
    fun `a task's stream is never written to the cache`() =
        assertTrue(cacheFreePath("/api/v1/tasks/abc/stream"))

    @Test
    fun `answers holding a secret are never written to the cache`() {
        assertTrue(cacheFreePath("/api/v1/settings/security"))
        assertTrue(cacheFreePath("/api/v1/stats/status"))
    }

    @Test
    fun `ordinary reads are kept for offline use`() {
        assertFalse(cacheFreePath("/api/v1/playlists"))
        assertFalse(cacheFreePath("/api/v1/stats/overview"))
    }

    @Test
    fun `an entity past the last code point is left as written`() {
        assertEquals("&#x110000; é", decodeEntities("&#x110000; &#233;"))
        assertEquals("&#99999999;", decodeEntities("&#99999999;"))
    }
}
