"""What comes from Deezer: the release feed of the profile's Deezer account, its
mixes, the search and the 30-second previews."""
from routes import account as deezer
from routes import playlists, search
from routes.api_v1 import COVERED, expose

expose("/releases", deezer.releases_route, name="releases")
# The Releases page: its feed is the route above.
COVERED.add(playlists.releases_view)
expose("/releases/refresh", deezer.refresh_releases_route, ("POST",), name="releases_refresh")
expose("/releases/mute", deezer.mute_artist_route, ("POST",), name="releases_mute")
expose("/deezer/mixes", deezer.mixes_route, name="deezer_mixes")
expose("/deezer/mixes/follow", deezer.follow_mix_route, ("POST",), name="deezer_mixes_follow")

expose("/search", search.search_route, name="search")
expose("/search/album/<album_id>", search.search_album_detail_route, name="search_album")
expose("/search/artist/<artist_id>", search.search_artist_detail_route, name="search_artist")
expose("/preview/<track_id>", search.preview_route, name="preview")
