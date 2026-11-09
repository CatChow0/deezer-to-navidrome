"""Made for you of the profile: its versions, its settings and its quarantine."""
from routes import mixes as web
from routes.api_v1 import expose

expose("/mixes", web.state, name="mixes")
expose("/mixes/settings", web.settings, ("POST",), name="mixes_settings")
expose("/mixes/generate", web.generate, ("POST",), name="mixes_generate")
expose("/mixes/trial/keep-pending", web.keep_pending, ("POST",), name="mixes_trial_keep_pending")
expose("/mixes/trial/remove-pending", web.remove_pending, ("POST",), name="mixes_trial_remove_pending")
expose("/mixes/trial/empty-trash", web.empty_trash, ("POST",), name="mixes_trial_empty_trash")
expose("/mixes/trial/<deezer_id>/keep", web.keep, ("POST",), name="mixes_trial_keep")
expose("/mixes/trial/<deezer_id>/remove", web.remove, ("POST",), name="mixes_trial_remove")
expose("/mixes/trial/<deezer_id>/restore", web.restore, ("POST",), name="mixes_trial_restore")
expose("/mixes/trial/<deezer_id>/cover", web.cover, name="mixes_trial_cover")
