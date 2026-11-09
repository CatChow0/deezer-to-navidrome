package io.github.catchow0.d2n.testutil

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.emptyPreferences
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** A DataStore in memory, for JVM tests on Windows: DataStore's file storage
 * renames over its file, which Java refuses there (File.renameTo never
 * replaces). The app runs on Android, where it works. */
class MemoryDataStore : DataStore<Preferences> {
    private val current = MutableStateFlow(emptyPreferences())
    private val mutex = Mutex()

    override val data: Flow<Preferences> = current

    override suspend fun updateData(transform: suspend (t: Preferences) -> Preferences): Preferences =
        mutex.withLock { transform(current.value).also { current.value = it } }
}
