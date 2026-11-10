"""The Android app shipped inside this image: Jenkins, or the owner's build
script, puts the signed APK and what it is (app.json) in dist/android before
the image is built. The web interface offers it for the first install, and
the app reads /api/v1/app to update itself."""
import hashlib
import json
import threading
from pathlib import Path

DIST_DIR = Path(__file__).resolve().parent.parent / "dist" / "android"
APK_NAME = "deezer-to-navidrome.apk"
MIME = "application/vnd.android.package-archive"
MISSING = "This image was built without the Android app."

# (path, mtime, size) -> SHA-256: an APK is hashed once, and again when it changes.
_hashes = {}
_hashes_lock = threading.Lock()


def _sha256(path: Path, stat) -> str:
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _hashes_lock:
        cached = _hashes.get(key)
        if cached is None:
            digest = hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
            # Evict stale keys only under the lock, so concurrent callers never
            # observe a half-empty cache.
            _hashes.clear()
            _hashes[key] = digest.hexdigest()
            cached = _hashes[key]
    return cached


def info() -> dict:
    """What the app in this image is. Its size and hash come from the file
    itself, so a stale app.json cannot lie about them."""
    apk = DIST_DIR / APK_NAME
    try:
        meta = json.loads((DIST_DIR / "app.json").read_text(encoding="utf-8"))
        stat = apk.stat()
        return {
            "available": True,
            "version": str(meta["version"]),
            "version_code": int(meta["version_code"]),
            "build": {"commit": str(meta["commit"]), "built_at": str(meta["built_at"])},
            "size": stat.st_size,
            "sha256": _sha256(apk, stat),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"available": False, "reason": MISSING}


def apk_path() -> Path | None:
    return DIST_DIR / APK_NAME if info()["available"] else None


def download_name() -> str:
    return f"deezer-to-navidrome-{info().get('version', 'unknown')}.apk"
