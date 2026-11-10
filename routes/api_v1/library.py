"""The library and what changes it: the index, the missing metadata, the
downloads and the duplicates."""
from routes import cache, dedup, search, system
from routes import mixes as made_for_you
from routes.api_v1 import COVERED, expose

expose("/library/stats", cache.library_stats_route, name="library_stats")
expose("/library/search", cache.library_search_route, name="library_search")
expose("/library/check", search.check_library_route, ("POST",), name="library_check")
expose("/library/refresh", cache.cache_incremental_start, ("POST",), name="library_refresh")
expose("/library/rebuild", cache.cache_full_start, ("POST",), name="library_rebuild")
# The web's older, blocking forms: the two tasks above do the same.
COVERED.update({cache.cache_refresh_route, cache.cache_rebuild_route})
expose("/library/metadata/fix", made_for_you.fix_metadata, ("POST",), name="library_metadata_fix")
expose("/library/metadata/undo", made_for_you.undo_metadata, ("POST",), name="library_metadata_undo")

expose("/downloads", system.deezer_dl_queue, name="downloads")
expose("/downloads", system.deezer_dl_download_start, ("POST",), name="downloads_start")
expose("/downloads/track/<track_id>", system.deezer_dl_track, ("POST",), name="downloads_track")
expose("/downloads/repair", system.repair_downloads_start, ("POST",), name="downloads_repair")

expose("/dedup/start", dedup.dedup_start, ("POST",), name="dedup_start")
expose("/dedup/report", dedup.dedup_report_route, name="dedup_report")
expose("/dedup/apply", dedup.dedup_apply_route, ("POST",), name="dedup_apply")
