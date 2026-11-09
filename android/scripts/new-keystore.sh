#!/usr/bin/env bash
# Creates the Android app's signing key, once (Linux or macOS; on Windows, use
# new-keystore.ps1). Keep the key and its password: phones can only update the
# app with this same key. Without them, the app must be uninstalled on every
# phone.
#   new-keystore.sh [folder]   default: ~/.d2n-android
set -euo pipefail

dir="${1:-$HOME/.d2n-android}"
key="$dir/release.jks"
if [ -e "$key" ]; then
  echo "A key already exists in $dir. Keep it: phones can only update the app with this same key, and losing it means reinstalling the app on every phone." >&2
  exit 1
fi

read -rsp "Choose the key's password (12 characters or more): " first; echo
read -rsp "Type it again: " second; echo
if [ "$first" != "$second" ]; then echo "The two passwords differ." >&2; exit 1; fi
if [ "${#first}" -lt 12 ]; then echo "Use 12 characters or more." >&2; exit 1; fi

mkdir -p "$dir"
chmod 700 "$dir"
# keytool reads the password from this variable, never from its command line.
D2N_KS_PASS="$first" keytool -genkeypair -keystore "$key" -storetype PKCS12 -storepass:env D2N_KS_PASS \
  -alias d2n -keyalg RSA -keysize 4096 -validity 10950 -dname "CN=Deezer to Navidrome, O=CatChow0"
chmod 600 "$key"

echo
echo "The key is in $key. Back it up now with its password, somewhere safe off this machine."
echo "To build: D2N_KEYSTORE_FILE=$key D2N_KEYSTORE_PASSWORD=… android/scripts/build-apk.sh"
echo "Jenkins needs them too: credentials android-keystore (secret file) and android-keystore-password (secret text)."
