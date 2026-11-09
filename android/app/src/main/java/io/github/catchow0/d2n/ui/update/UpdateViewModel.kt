package io.github.catchow0.d2n.ui.update

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.AppInfo
import io.github.catchow0.d2n.update.ApkInstaller
import io.github.catchow0.d2n.update.DamagedDownload
import io.github.catchow0.d2n.update.InstallResult
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl

const val DAMAGED = "The download is damaged: try again."
const val DOWNLOAD_STOPPED = "The download stopped: try again."
const val NEWEST = "This is the newest version."
const val NOT_INSTALLED = "The update was not installed."
const val INSTALL_FAILED = "The update did not install: %s"
private const val TAG = "D2N"

/**
 * The app's update from the server: the offer, its download, and Android's
 * installer. [check] and [download] are UpdateChecker.check and
 * ApkDownloader.download. Debug builds have another package, so they never
 * offer the server's app ([enabled] is false).
 *
 * Once handed to Android, the install can still fail, be cancelled, or wait
 * for a confirmation screen Android would not open: the downloaded file stays,
 * so the banner always has a way to try again.
 */
class UpdateViewModel(
    private val check: suspend (force: Boolean) -> AppInfo?,
    private val download: suspend (HttpUrl, File, String, (Long, Long) -> Unit) -> File,
    private val installer: ApkInstaller,
    private val base: () -> HttpUrl?,
    private val dir: File,
    private val enabled: Boolean,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : ViewModel() {
    data class UiState(
        val offer: AppInfo? = null,
        val checking: Boolean = false,
        /** What a check asked for by the user found. */
        val checked: String? = null,
        val progress: Float? = null,
        val downloaded: File? = null,
        val error: String? = null,
        val needsPermission: Boolean = false,
        /** Android's confirmation screen, when it could not open by itself. */
        val confirmation: Any? = null,
        /** Handed to Android, waiting for its answer. */
        val installing: Boolean = false,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    init {
        viewModelScope.launch {
            installer.results.collect { result ->
                when (result) {
                    is InstallResult.NeedsConfirmation -> _state.update { it.copy(confirmation = result.confirmation) }
                    is InstallResult.Failed -> _state.update {
                        it.copy(
                            installing = false, confirmation = null,
                            error = if (result.aborted) NOT_INSTALLED else INSTALL_FAILED.format(result.message),
                        )
                    }
                    InstallResult.Succeeded -> _state.update { it.copy(installing = false, confirmation = null) }
                }
            }
        }
    }

    /** [force]: asked from About, which shows the result and any failure. */
    fun check(force: Boolean = false) {
        if (!enabled || _state.value.checking) return
        _state.update { it.copy(checking = true, checked = null) }
        viewModelScope.launch {
            try {
                val offer = check.invoke(force)
                _state.update {
                    it.copy(
                        checking = false,
                        offer = offer ?: it.offer.takeUnless { force },
                        checked = if (force && offer == null) NEWEST else offer?.let { found -> "Version ${found.version} is ready." },
                    )
                }
            } catch (e: ApiFailure) {
                _state.update { it.copy(checking = false, checked = if (force) "Could not check: ${e.message}" else null) }
            }
        }
    }

    /** Downloads the offer, checks it, and hands it to Android at once. */
    fun download() {
        val offer = _state.value.offer ?: return
        val sha256 = offer.sha256 ?: return
        val url = base()?.resolve("api/v1/app/apk") ?: return
        _state.update { it.copy(progress = 0f, error = null) }
        viewModelScope.launch {
            try {
                val file = download.invoke(url, dir, sha256) { read, total ->
                    if (total > 0) _state.update { it.copy(progress = read.toFloat() / total) }
                }
                _state.update { it.copy(downloaded = file, progress = null) }
                install()
            } catch (e: DamagedDownload) {
                Log.w(TAG, "The update's download is damaged", e)
                _state.update { it.copy(progress = null, error = DAMAGED) }
            } catch (e: ApiFailure) {
                Log.w(TAG, "The update's download failed", e)
                _state.update { it.copy(progress = null, error = DOWNLOAD_STOPPED) }
            }
        }
    }

    fun install() {
        val file = _state.value.downloaded ?: return
        if (!installer.canInstall()) {
            _state.update { it.copy(needsPermission = true) }
            return
        }
        _state.update { it.copy(needsPermission = false, installing = true, error = null, confirmation = null) }
        viewModelScope.launch {
            try {
                // The APK is copied into Android's session: off the main thread.
                withContext(io) { installer.install(file) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "The update could not be handed to Android", e)
                _state.update { it.copy(installing = false, error = INSTALL_FAILED.format(e.message ?: e.javaClass.simpleName)) }
            }
        }
    }

    /** Opens Android's confirmation screen, which could not open by itself. */
    fun confirm() {
        val confirmation = _state.value.confirmation ?: return
        installer.confirm(confirmation)
    }

    fun openInstallSettings() = installer.openInstallSettings()
}
