#!/bin/sh
# PUID / PGID: the app runs as this user and group instead of root, as with
# most self-hosted images. The data folder is given to them at start; the music
# and playlist folders must already be writable by them. Unset, the app runs
# as root, as before 1.19.
set -e
if [ "$(id -u)" = "0" ] && [ -n "${PUID:-}" ]; then
  PGID="${PGID:-$PUID}"
  getent group "$PGID" >/dev/null 2>&1 || addgroup -g "$PGID" d2n
  group="$(getent group "$PGID" | cut -d: -f1)"
  getent passwd "$PUID" >/dev/null 2>&1 || adduser -D -H -u "$PUID" -G "$group" d2n
  data="${DATA_DIR:-/data}"
  mkdir -p "$data"
  find "$data" \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown "$PUID:$PGID" {} +
  exec su-exec "$PUID:$PGID" "$@"
fi
exec "$@"
