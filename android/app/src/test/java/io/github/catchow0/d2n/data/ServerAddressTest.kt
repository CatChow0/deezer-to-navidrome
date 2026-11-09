package io.github.catchow0.d2n.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerAddressTest {
    @Test
    fun `a bare host gets https and a trailing slash`() =
        assertEquals("https://dzr-to-navi.phylumm.fr/", ServerAddress.normalize("  dzr-to-navi.phylumm.fr ")?.toString())

    @Test
    fun `a sub-path is kept`() =
        assertEquals("https://host.example/d2n/", ServerAddress.normalize("https://Host.Example/d2n")?.toString())

    @Test
    fun `http is kept and flagged`() {
        val address = ServerAddress.normalize("http://192.168.1.10:8080")!!
        assertEquals("http://192.168.1.10:8080/", address.toString())
        assertTrue(address.isCleartext)
        assertFalse(ServerAddress.normalize("dzr-to-navi.phylumm.fr")!!.isCleartext)
    }

    @Test
    fun `a short local name works with a scheme or a port`() {
        assertEquals("http://nas:8097/", ServerAddress.normalize("http://nas:8097")?.toString())
        assertEquals("https://nas:8097/", ServerAddress.normalize("nas:8097")?.toString())
        assertEquals("http://myserver/", ServerAddress.normalize("http://MyServer")?.toString())
    }

    @Test
    fun `nonsense is refused`() {
        assertNull(ServerAddress.normalize("not an address"))
        assertNull(ServerAddress.normalize(""))
        assertNull(ServerAddress.normalize("intranet"))
        assertNull(ServerAddress.normalize("ftp://host.example"))
    }
}
