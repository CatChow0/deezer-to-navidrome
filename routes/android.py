"""The Android app's APK, for the first install from a phone's browser."""
from flask import Blueprint, jsonify, send_file

from core import android_app

android_bp = Blueprint("android", __name__)


@android_bp.get("/app/android.apk")
def apk():
    path = android_app.apk_path()
    if path is None:
        return jsonify({"ok": False, "error": android_app.MISSING}), 404
    response = send_file(path, mimetype=android_app.MIME, as_attachment=True,
                         download_name=android_app.download_name(), conditional=True, etag=True, max_age=0)
    # Asked again each time: a new image brings a new APK under the same name.
    response.headers["Cache-Control"] = "private, no-cache"
    return response
