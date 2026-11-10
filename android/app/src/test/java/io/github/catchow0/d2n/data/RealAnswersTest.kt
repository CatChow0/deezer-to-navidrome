package io.github.catchow0.d2n.data

import java.io.File
import kotlinx.serialization.KSerializer
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * Decodes answers saved from a real server: run with D2N_REAL_ANSWERS set to a
 * folder of <endpoint>.json files (a throwaway server's, never someone's data
 * in the repository). Skipped otherwise. The fixtures are written from the
 * server's code; this catches what a real library adds to them (a duration in
 * decimals, a missing field).
 */
class RealAnswersTest {
    private val folder = System.getenv("D2N_REAL_ANSWERS")?.let(::File)

    private val decoders: List<Pair<String, KSerializer<*>>> = listOf(
        "stats_overview" to StatsOverview.serializer(),
        "stats_recaps" to RecapIndex.serializer(),
        "stats_recap_" to Recap.serializer(),
        "stats_artist_" to StatsEntity.serializer(),
        "stats_album_" to StatsEntity.serializer(),
        "stats_track_" to StatsEntity.serializer(),
        "stats_plays" to PlaysPage.serializer(),
        "stats_status" to StatsStatus.serializer(),
        "releases" to ReleasesAnswer.serializer(),
        "settings" to SettingsAnswer.serializer(),
        "navidrome_accounts" to NavidromeProfilesAnswer.serializer(),
        "deezer_accounts" to DeezerProfilesAnswer.serializer(),
        "security" to SecurityAnswer.serializer(),
        "devices" to DevicesAnswer.serializer(),
        "notes" to NotesAnswer.serializer(),
        "help" to HelpAnswer.serializer(),
        "dedup_report" to DuplicateReportAnswer.serializer(),
        "mixes" to MixesAnswer.serializer(),
        "playlists" to PlaylistsAnswer.serializer(),
        "library_stats" to LibraryStats.serializer(),
    )

    @Test
    fun `every saved answer decodes`() {
        val dir = folder
        assumeTrue("D2N_REAL_ANSWERS is not set", dir != null && dir.isDirectory)
        val failures = mutableListOf<String>()
        var decoded = 0
        dir!!.listFiles { f -> f.extension == "json" }!!.sortedBy { it.name }.forEach { file ->
            val name = file.nameWithoutExtension
            val serializer = decoders.firstOrNull { (prefix, _) -> name == prefix || (prefix.endsWith("_") && name.startsWith(prefix)) || name.startsWith("${prefix}_") }?.second
                ?: return@forEach
            try {
                D2nJson.decodeFromString(serializer, file.readText())
                decoded++
            } catch (e: Exception) {
                failures += "$name: ${e.message?.lineSequence()?.take(2)?.joinToString(" ")}"
            }
        }
        println("decoded $decoded real answers")
        if (failures.isNotEmpty()) throw AssertionError(failures.joinToString("\n"))
    }
}
