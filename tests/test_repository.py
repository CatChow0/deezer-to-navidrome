"""What git keeps: the Android app's sources must never be ignored, while the
server's data folder, the build outputs and the signing keys always are."""
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


@unittest.skipUnless((REPO / ".git").exists(), "not a git checkout")
class Repository(unittest.TestCase):
    def test_no_source_of_the_android_app_is_ignored(self):
        ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", "--",
                      "android/app/src", "android/gradle", "android/scripts").stdout.split()
        self.assertEqual(ignored, [], "sources a commit would leave out")

    def test_data_build_outputs_and_keys_stay_ignored(self):
        for path in ("data/config.json", "dist/android/deezer-to-navidrome.apk", "android/app/build/out.apk",
                     "android/local.properties", "android/keystore.properties", "release.jks"):
            self.assertEqual(git("check-ignore", "-q", path).returncode, 0, path)


if __name__ == "__main__":
    unittest.main()
