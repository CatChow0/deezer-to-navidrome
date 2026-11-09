package io.github.catchow0.d2n.update

import io.github.catchow0.d2n.data.ApiError
import io.github.catchow0.d2n.data.Unreachable
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request

/** The download is not the file the server described: it is never installed. */
class DamagedDownload : Exception("The download is damaged: try again.")

/**
 * Downloads the server's APK into [dir]: first as a .part file, renamed only
 * once its SHA-256 matches. A cut or a wrong hash leaves nothing behind, so a
 * partial file can never reach the installer.
 */
class ApkDownloader(private val client: OkHttpClient) {
    suspend fun download(url: HttpUrl, dir: File, expectedSha256: String, onProgress: (read: Long, total: Long) -> Unit): File =
        withContext(Dispatchers.IO) {
            dir.mkdirs()
            val part = File(dir, "$NAME.part")
            val target = File(dir, NAME)
            part.delete()
            target.delete()
            try {
                val digest = MessageDigest.getInstance("SHA-256")
                client.newCall(Request.Builder().url(url).build()).execute().use { response ->
                    if (!response.isSuccessful) {
                        throw ApiError(response.code, "download_failed", "The server answered ${response.code}.", null)
                    }
                    val total = response.body.contentLength()
                    var read = 0L
                    val buffer = ByteArray(64 * 1024)
                    response.body.byteStream().use { input ->
                        part.outputStream().use { output ->
                            while (true) {
                                coroutineContext.ensureActive()
                                val count = input.read(buffer)
                                if (count == -1) break
                                output.write(buffer, 0, count)
                                digest.update(buffer, 0, count)
                                read += count
                                onProgress(read, total)
                            }
                        }
                    }
                }
                val sha256 = digest.digest().joinToString("") { "%02x".format(it) }
                if (!sha256.equals(expectedSha256, ignoreCase = true)) throw DamagedDownload()
                if (!part.renameTo(target)) throw IOException("Could not keep the download.")
                target
            } catch (e: IOException) {
                part.delete()
                throw Unreachable(e)
            } catch (e: Throwable) {
                part.delete()
                throw e
            }
        }

    private companion object {
        const val NAME = "deezer-to-navidrome.apk"
    }
}
