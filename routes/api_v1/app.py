"""The Android app in this image: what it is, for the app's update check, and
its APK."""
from core import android_app
from routes import android
from routes.api_v1 import api_v1_bp, expose, ok


@api_v1_bp.get("/app")
def app_info():
    """{available, version, version_code, build: {commit, built_at}, size,
    sha256}, or {available: false, reason}."""
    return ok(android_app.info(), cache=True)


expose("/app/apk", android.apk, name="app_apk")
