package io.github.catchow0.d2n

import android.content.Context
import android.os.Build
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.core.handlers.ReplaceFileCorruptionHandler
import androidx.datastore.preferences.preferencesDataStoreFile
import io.github.catchow0.d2n.data.ApiFailure
import io.github.catchow0.d2n.data.ApiProvider
import io.github.catchow0.d2n.data.D2nApi
import io.github.catchow0.d2n.data.DataStoreSettingsStore
import io.github.catchow0.d2n.data.NotThisServer
import io.github.catchow0.d2n.data.RequestHeaders
import io.github.catchow0.d2n.data.SettingsStore
import io.github.catchow0.d2n.data.TinkSecretBox
import io.github.catchow0.d2n.data.apiCall
import io.github.catchow0.d2n.data.buildHttpClient
import io.github.catchow0.d2n.tasks.TaskFollower
import io.github.catchow0.d2n.ui.main.Reachability
import io.github.catchow0.d2n.update.ApkDownloader
import io.github.catchow0.d2n.update.ApkInstaller
import io.github.catchow0.d2n.update.BuildIdentity
import io.github.catchow0.d2n.update.PackageInstallerApkInstaller
import io.github.catchow0.d2n.update.UpdateChecker
import java.io.File
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient

/** The app's pieces, made once and wired together by hand. */
class AppGraph(context: Context) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val store: SettingsStore = DataStoreSettingsStore(
        PreferenceDataStoreFactory.create(
            corruptionHandler = ReplaceFileCorruptionHandler { emptyPreferences() },
            scope = scope,
        ) { context.preferencesDataStoreFile("d2n") },
        TinkSecretBox(context),
        scope,
    )

    val own = BuildIdentity.current()
    val userAgent = "D2N/${own.versionName} (Android ${Build.VERSION.SDK_INT})"
    val defaultDevice: String = Build.MODEL?.takeIf { it.isNotBlank() } ?: "Android phone"

    private val _unauthorized = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** The server refused this phone's token: signed out from the web, or a new password. */
    val unauthorized: SharedFlow<Unit> = _unauthorized

    /** Every call to the server: the token and the profile ride along. */
    val client: OkHttpClient = buildHttpClient(
        File(context.cacheDir, "net"),
        { store.state.value.let { RequestHeaders(it.token, it.profile) } },
        userAgent,
    ) { _unauthorized.tryEmit(Unit) }

    /** For an address not trusted yet: never carries a token. */
    val bareClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .addInterceptor { it.proceed(it.request().newBuilder().header("User-Agent", userAgent).build()) }
        .build()

    private val apis = ApiProvider(client)

    fun base(): HttpUrl? = store.state.value.serverUrl?.toHttpUrlOrNull()

    fun api(): D2nApi? = base()?.let(apis::forServer)

    fun requireApi(): D2nApi = api() ?: throw NotThisServer("No server address yet.")

    fun apiFor(base: HttpUrl): D2nApi = apis.forServer(base)

    /** Whether the server answers; shared by every screen's banner. */
    val reachability = Reachability(
        probe = {
            try {
                apiCall { requireApi().authStatus() }
                true
            } catch (e: ApiFailure) {
                false
            }
        },
        scope = scope,
    )

    val taskFollower = TaskFollower(client, apis::forServer)

    // The app's updates come from the server it talks to.
    val updateChecker = UpdateChecker(::api, store, own, System::currentTimeMillis)
    val downloader = ApkDownloader(client)
    val installer: ApkInstaller = PackageInstallerApkInstaller(context.applicationContext)
    val updatesDir = File(context.cacheDir, "updates")

    /** A debug build has another package: the server's app would install beside it. */
    val updatesEnabled = !BuildConfig.DEBUG
}
