"""The listening history of the profile: overview, recaps, details, plays, its
rebuild and its ListenBrainz token, with the covers and the audio."""
from routes import stats as web
from routes.api_v1 import COVERED, expose

expose("/stats/overview", web.overview, name="stats_overview")
# The Stats page: what it shows comes from the routes below.
COVERED.add(web.stats_view)
expose("/stats/recaps", web.recaps, name="stats_recaps")
expose("/stats/recap", web.recap, name="stats_recap")
expose("/stats/<any(artist, album, track):kind>/<int:entity_id>", web.entity, name="stats_entity")
expose("/stats/plays", web.plays, name="stats_plays")
expose("/stats/status", web.status, name="stats_status", cache=False)
expose("/stats/import", web.start_import, ("POST",), name="stats_import")
expose("/stats/import/preview", web.preview_import, ("POST",), name="stats_import_preview")
expose("/stats/token", web.make_token, ("POST",), name="stats_token_make")
expose("/stats/token", web.delete_token, ("DELETE",), name="stats_token_delete")
expose("/stats/cover/<any(track, album, artist):kind>/<int:item_id>", web.cover, name="stats_cover")
expose("/stats/audio/<int:track_id>", web.audio, name="stats_audio")
