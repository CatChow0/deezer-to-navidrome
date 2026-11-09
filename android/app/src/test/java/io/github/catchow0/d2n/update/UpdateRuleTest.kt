package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.AppBuild
import io.github.catchow0.d2n.data.AppInfo
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateRuleTest {
    private val own = BuildIdentity(11800, "1.18.0", "abc1234", "2026-11-09T12:00:00Z")

    private fun server(code: Int, commit: String = "abc1234", builtAt: String = "2026-11-09T12:00:00Z") =
        AppInfo(available = true, version = "1.18.0", versionCode = code, build = AppBuild(commit, builtAt), size = 10, sha256 = "x")

    @Test
    fun `a higher version code is offered`() = assertTrue(UpdateRule.shouldOffer(own, server(11801)))

    @Test
    fun `the same version from another commit is offered`() =
        assertTrue(UpdateRule.shouldOffer(own, server(11800, commit = "def5678")))

    @Test
    fun `the same commit rebuilt later is offered`() =
        assertTrue(UpdateRule.shouldOffer(own, server(11800, builtAt = "2026-11-09T13:00:00Z")))

    @Test
    fun `the very same build is not offered`() = assertFalse(UpdateRule.shouldOffer(own, server(11800)))

    @Test
    fun `a lower version code is never offered`() =
        assertFalse(UpdateRule.shouldOffer(own, server(11799, commit = "def5678", builtAt = "2026-11-10T00:00:00Z")))

    @Test
    fun `an image without the app offers nothing`() {
        assertFalse(UpdateRule.shouldOffer(own, AppInfo(available = false, reason = "This image was built without the Android app.")))
        // Even with numbers, an unavailable app is not offered.
        assertFalse(UpdateRule.shouldOffer(own, server(11900).copy(available = false)))
    }
}
