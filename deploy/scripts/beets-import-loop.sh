#!/bin/sh
# Indexe sur place 10-rotation et 20-archives (pas de move Beets).
set -eu
MEDIA="${MEDIA_ROOT:-/media}"
INTERVAL="${BEETS_IMPORT_INTERVAL:-45}"
while true; do
  if [ -f /refresh_volume.py ]; then
    python3 /refresh_volume.py || true
  fi
  if [ -f /promote-inbox.sh ]; then
    sh /promote-inbox.sh || true
  fi
  if [ -d "$MEDIA/10-rotation" ]; then
    beet import -A -q "$MEDIA/10-rotation" || true
    beet modify -y grouping=rotation "path:$MEDIA/10-rotation" || true
  fi
  # Chaque dossier de 20-archives est une banque ; son nom devient le grouping.
  for dir in "$MEDIA"/20-archives/*/; do
    [ -d "$dir" ] || continue
    dir=${dir%/}
    ed=$(basename "$dir")
    case "$ed" in .*|_*) continue ;; esac
    beet import -A -q "$dir" || true
    beet modify -y grouping="$ed" genre=Archive "path:$dir" || true
  done
  if [ -f /export_share_roles.py ]; then
    python3 /export_share_roles.py || true
  fi
  sleep "$INTERVAL"
done
