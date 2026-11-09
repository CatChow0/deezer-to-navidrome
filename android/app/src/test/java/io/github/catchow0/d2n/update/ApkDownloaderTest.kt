package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.RequestHeaders
import io.github.catchow0.d2n.data.Unreachable
import io.github.catchow0.d2n.data.buildHttpClient
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.SocketEffect
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test

class ApkDownloaderTest {
    private val server = MockWebServer()
    private val apk = ByteArray(200_000) { (it * 31).toByte() }
    private val sha256 = MessageDigest.getInstance("SHA-256").digest(apk).joinToString("") { "%02x".format(it) }
    private lateinit var dir: File
    private lateinit var downloader: ApkDownloader

    @Before
    fun setUp() {
        server.start()
        dir = Files.createTempDirectory("d2n-updates").toFile()
        downloader = ApkDownloader(buildHttpClient(null, { RequestHeaders("d2n_x", null) }, "D2N/test"))
    }

    @After
    fun tearDown() {
        server.close()
        dir.deleteRecursively()
    }

    private fun whole() = MockResponse.Builder().code(200).body(Buffer().write(apk)).build()

    @Test
    fun `the file is kept when its hash matches`() = runBlocking {
        server.enqueue(whole())
        var progress = 0L to 0L
        val file = downloader.download(server.url("/api/v1/app/apk"), dir, sha256) { read, total -> progress = read to total }
        assertEquals("deezer-to-navidrome.apk", file.name)
        assertArrayEquals(apk, file.readBytes())
        assertEquals(apk.size.toLong() to apk.size.toLong(), progress)
        assertEquals(listOf("deezer-to-navidrome.apk"), dir.list()!!.toList())
        assertEquals("Bearer d2n_x", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `a damaged file is refused and deleted`() {
        server.enqueue(whole())
        assertThrows(DamagedDownload::class.java) {
            runBlocking { downloader.download(server.url("/api/v1/app/apk"), dir, "0".repeat(64)) { _, _ -> } }
        }
        assertEquals(emptyList<String>(), dir.list()!!.toList())
    }

    @Test
    fun `a second update through the app's cache gets the new file`() = runBlocking {
        // The app's client keeps an HTTP cache: the previous APK sits in it.
        val cacheDir = Files.createTempDirectory("d2n-http").toFile()
        val cached = ApkDownloader(buildHttpClient(cacheDir, { RequestHeaders("d2n_x", null) }, "D2N/test"))
        val first = ByteArray(150_000) { (it * 7).toByte() }
        val second = ByteArray(160_000) { (it * 11).toByte() }
        fun apkResponse(bytes: ByteArray, etag: String) = MockResponse.Builder().code(200)
            .addHeader("Content-Type", "application/vnd.android.package-archive")
            .addHeader("ETag", etag).addHeader("Cache-Control", "private, no-cache")
            .body(Buffer().write(bytes)).build()
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        server.enqueue(apkResponse(first, "\"one\""))
        server.enqueue(apkResponse(second, "\"two\""))
        assertArrayEquals(first, cached.download(server.url("/api/v1/app/apk"), dir, sha(first)) { _, _ -> }.readBytes())
        assertArrayEquals(second, cached.download(server.url("/api/v1/app/apk"), dir, sha(second)) { _, _ -> }.readBytes())
        cacheDir.deleteRecursively()
        Unit
    }

    @Test
    fun `a cut in the middle leaves no file`() {
        server.enqueue(MockResponse.Builder().code(200).body(Buffer().write(apk)).onResponseBody(SocketEffect.CloseSocket()).build())
        assertThrows(Unreachable::class.java) {
            runBlocking { downloader.download(server.url("/api/v1/app/apk"), dir, sha256) { _, _ -> } }
        }
        assertEquals(emptyList<String>(), dir.list()!!.toList())
        // A new try works.
        server.enqueue(whole())
        val file = runBlocking { downloader.download(server.url("/api/v1/app/apk"), dir, sha256) { _, _ -> } }
        assertArrayEquals(apk, file.readBytes())
    }
}
