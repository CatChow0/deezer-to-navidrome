package io.github.catchow0.d2n.update

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import java.io.File
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow

/** What Android's installer answered. */
sealed interface InstallResult {
    /** Android wants the user to confirm; [confirmation] is the screen to show. */
    data class NeedsConfirmation(val confirmation: Any) : InstallResult
    data class Failed(val message: String, val aborted: Boolean) : InstallResult
    data object Succeeded : InstallResult
}

/** Hands a downloaded APK to Android. */
interface ApkInstaller {
    /** Android's answers about the install. */
    val results: Flow<InstallResult>

    /** Opens the confirmation screen Android asked for (an Intent). */
    fun confirm(confirmation: Any)

    /** Whether the user allowed this app to install apps. */
    fun canInstall(): Boolean

    /** Opens the setting that allows it. */
    fun openInstallSettings()

    fun install(apk: File)
}

/** What InstallResultReceiver hears, for the app's banner. */
internal object InstallEvents {
    val results = MutableSharedFlow<InstallResult>(extraBufferCapacity = 8)
}

/**
 * Installs through a PackageInstaller session. Android then asks the user to
 * confirm (InstallResultReceiver opens its screen), checks that the APK carries
 * the same signature as the installed app, and restarts the app updated.
 */
class PackageInstallerApkInstaller(private val context: Context) : ApkInstaller {
    override val results: Flow<InstallResult> = InstallEvents.results

    override fun confirm(confirmation: Any) {
        context.startActivity((confirmation as Intent).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    override fun canInstall(): Boolean = context.packageManager.canRequestPackageInstalls()

    override fun openInstallSettings() {
        context.startActivity(
            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    /**
     * The file must be this app, signed with the same key, and not older. The
     * SHA-256 checked before comes from the same server, so it only proves the
     * file arrived whole: a rogue server, or someone between, could hand any
     * APK. Android would refuse most of these; refused here, the reason is clear.
     */
    private fun check(apk: File) {
        val manager = context.packageManager
        @Suppress("DEPRECATION")
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val update = manager.getPackageArchiveInfo(apk.path, flags) ?: throw IOException("the file is not an Android app")
        val own = manager.getPackageInfo(context.packageName, flags)
        if (update.packageName != context.packageName) throw IOException("the file is another app (${update.packageName})")
        if (versionCode(update) < versionCode(own)) throw IOException("the file is an older version")
        val signers = signers(update)
        if (signers.isEmpty() || signers != signers(own)) throw IOException("the file is not signed with this app's key")
    }

    @Suppress("DEPRECATION")
    private fun versionCode(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    @Suppress("DEPRECATION")
    private fun signers(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        return signatures.orEmpty().map { it.toCharsString() }.toSet()
    }

    override fun install(apk: File) {
        check(apk)
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(context.packageName)
        val sessionId = installer.createSession(params)
        installer.openSession(sessionId).use { session ->
            try {
                session.openWrite("deezer-to-navidrome.apk", 0, apk.length()).use { output ->
                    apk.inputStream().use { it.copyTo(output) }
                    session.fsync(output)
                }
                // Mutable: Android adds the session's status to this intent.
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                val status = PendingIntent.getBroadcast(
                    context, sessionId, Intent(context, InstallResultReceiver::class.java).setPackage(context.packageName), flags,
                )
                session.commit(status.intentSender)
            } catch (e: Exception) {
                // A session left open would count against the app's limit.
                session.abandon()
                throw e
            }
        }
    }
}

/**
 * The installer's answers. The confirmation screen is opened at once, and also
 * handed to the app: Android may refuse to open it while the app is in the
 * background, and the banner then offers it again.
 */
class InstallResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(Intent.EXTRA_INTENT)
                } ?: return
                InstallEvents.results.tryEmit(InstallResult.NeedsConfirmation(confirm))
                runCatching { context.startActivity(Intent(confirm).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            }
            PackageInstaller.STATUS_SUCCESS -> InstallEvents.results.tryEmit(InstallResult.Succeeded)
            else -> InstallEvents.results.tryEmit(
                InstallResult.Failed(
                    intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "unknown error",
                    aborted = status == PackageInstaller.STATUS_FAILURE_ABORTED,
                ),
            )
        }
    }
}
