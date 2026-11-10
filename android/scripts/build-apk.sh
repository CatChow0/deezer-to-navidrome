#!/usr/bin/env bash
# Builds and signs the Android app in Docker into dist/android/ (the APK and
# app.json), which the server image then picks up. Jenkins runs it; on the
# owner's PC, build-apk.ps1 runs it with the saved key.
#   D2N_KEYSTORE_FILE      the signing key (release.jks)
#   D2N_KEYSTORE_PASSWORD  its password
#   D2N_VERSION            another version than VERSION: for the update tests only
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
# docker.exe needs a Windows path in Git Bash; pwd -W gives one, and fails on Linux.
root="$(cd "$here/../.." && { pwd -W 2>/dev/null || pwd; })"
out="$root/dist/android"

# Whatever fails below, no APK from an earlier build stays to be shipped.
rm -rf "$out"

if [ -z "${D2N_KEYSTORE_FILE:-}" ] || [ ! -f "$D2N_KEYSTORE_FILE" ]; then
  echo "build-apk: set D2N_KEYSTORE_FILE to the signing key (release.jks)." >&2
  exit 2
fi
if [ -z "${D2N_KEYSTORE_PASSWORD:-}" ]; then
  echo "build-apk: set D2N_KEYSTORE_PASSWORD to the key's password." >&2
  exit 2
fi
# docker reads the password from its own environment (--secret …,env=).
export D2N_KEYSTORE_PASSWORD

version="${D2N_VERSION:-$(tr -d '[:space:]' < "$root/VERSION")}"
commit="$(git -C "$root" rev-parse --short=7 HEAD 2>/dev/null || echo dev)"
built_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker buildx build \
  --file "$root/android/Dockerfile" \
  --target out \
  --output "type=local,dest=$out" \
  --secret "id=keystore,src=$D2N_KEYSTORE_FILE" \
  --secret "id=keystore_password,env=D2N_KEYSTORE_PASSWORD" \
  --build-arg "D2N_VERSION=$version" \
  --build-arg "D2N_COMMIT=$commit" \
  --build-arg "D2N_BUILT_AT=$built_at" \
  "$root/android"

for file in deezer-to-navidrome.apk app.json; do
  if [ ! -f "$out/$file" ]; then
    echo "build-apk: $out/$file is missing." >&2
    exit 1
  fi
done
echo "build-apk: $out holds the app $version ($commit, built $built_at)."
