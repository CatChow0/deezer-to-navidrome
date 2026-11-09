package io.github.catchow0.d2n.ui.update

import io.github.catchow0.d2n.data.AppBuild
import io.github.catchow0.d2n.data.AppInfo
import io.github.catchow0.d2n.testutil.MainDispatcherRule
import io.github.catchow0.d2n.update.ApkInstaller
import io.github.catchow0.d2n.update.DamagedDownload
import io.github.catchow0.d2n.update.InstallResult
import java.io.File
import java.io.IOException
import java.nio.file.Files
import kotlinx.coroutines.flow.MutableSharedFlow
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class UpdateViewModelTest {
    @get:Rule
    val main = MainDispatcherRule()

    private class FakeInstaller(var allowed: Boolean) : ApkInstaller {
        val installed = mutableListOf<File>()
        val confirmed = mutableListOf<Any>()
        var settingsOpened = 0
        var failure: Exception? = null
        override val results = MutableSharedFlow<InstallResult>(extraBufferCapacity = 8)
        override fun canInstall() = allowed
        override fun openInstallSettings() {
            settingsOpened++
        }
        override fun install(apk: File) {
            failure?.let { throw it }
            installed += apk
        }
        override fun confirm(confirmation: Any) {
            confirmed += confirmation
        }
    }

    private val offer = AppInfo(true, "1.18.1", 11801, AppBuild("def5678", "2026-11-10T09:00:00Z"), 10, "ab12")
    private val dir: File = Files.createTempDirectory("d2n-updates").toFile()
    private val apk = File(dir, "deezer-to-navidrome.apk")
    private val asked = mutableListOf<HttpUrl>()

    private fun model(installer: ApkInstaller, download: suspend (HttpUrl, File, String, (Long, Long) -> Unit) -> File = { url, _, sha, progress ->
        asked += url
        assertEquals("ab12", sha)
        progress(5, 10)
        progress(10, 10)
        apk
    }) = UpdateViewModel(
        check = { offer },
        download = download,
        installer = installer,
        base = { "https://music.example/d2n/".toHttpUrl() },
        dir = dir,
        enabled = true,
        io = main.dispatcher,
    )

    @Test
    fun `an offer shows the banner and a download installs it`() {
        val installer = FakeInstaller(allowed = true)
        val vm = model(installer)
        vm.check()
        assertEquals(11801, vm.state.value.offer?.versionCode)
        vm.download()
        assertEquals("/d2n/api/v1/app/apk", asked.single().encodedPath)
        assertEquals(listOf(apk), installer.installed)
        assertEquals(apk, vm.state.value.downloaded)
        assertNull(vm.state.value.progress)
    }

    @Test
    fun `without permission it asks for it first`() {
        val installer = FakeInstaller(allowed = false)
        val vm = model(installer)
        vm.check()
        vm.download()
        assertTrue(vm.state.value.needsPermission)
        assertTrue(installer.installed.isEmpty())
        vm.openInstallSettings()
        assertEquals(1, installer.settingsOpened)
        // Allowed, Update installs what was downloaded.
        installer.allowed = true
        vm.install()
        assertFalse(vm.state.value.needsPermission)
        assertEquals(listOf(apk), installer.installed)
    }

    @Test
    fun `a damaged download is said and nothing is installed`() {
        val installer = FakeInstaller(allowed = true)
        val vm = model(installer) { _, _, _, _ -> throw DamagedDownload() }
        vm.check()
        vm.download()
        assertEquals(DAMAGED, vm.state.value.error)
        assertTrue(installer.installed.isEmpty())
        assertNull(vm.state.value.progress)
    }

    @Test
    fun `an install that is cancelled can be tried again`() {
        val installer = FakeInstaller(allowed = true)
        val vm = model(installer)
        vm.check()
        vm.download()
        installer.results.tryEmit(InstallResult.Failed("Install aborted", aborted = true))
        assertEquals(NOT_INSTALLED, vm.state.value.error)
        assertEquals(apk, vm.state.value.downloaded)
        vm.install()
        assertEquals(listOf(apk, apk), installer.installed)
        assertNull(vm.state.value.error)
    }

    @Test
    fun `a confirmation that could not show is offered again`() {
        val installer = FakeInstaller(allowed = true)
        val vm = model(installer)
        vm.check()
        vm.download()
        val confirmation = Any()
        installer.results.tryEmit(InstallResult.NeedsConfirmation(confirmation))
        assertEquals(confirmation, vm.state.value.confirmation)
        vm.confirm()
        assertEquals(listOf(confirmation), installer.confirmed)
        installer.results.tryEmit(InstallResult.Failed("Install aborted", aborted = true))
        assertNull(vm.state.value.confirmation)
    }

    @Test
    fun `an install that fails is said, not a crash`() {
        val installer = FakeInstaller(allowed = true).apply { failure = IOException("No space left on device") }
        val vm = model(installer)
        vm.check()
        vm.download()
        assertEquals("The update did not install: No space left on device", vm.state.value.error)
        assertEquals(apk, vm.state.value.downloaded)
    }
}
