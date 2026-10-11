#!/usr/bin/env bash
# Snapshot cohérent d’une instance Radiotomate (SQLite WAL via .backup).
set -euo pipefail

umask 077

usage() {
  echo "usage: backup-radiotomate.sh DATA_ROOT [DEST_ARCHIVE]" >&2
  exit 2
}

DATA_ROOT="${1:-}"
[[ -n "$DATA_ROOT" ]] || usage
DATA_ROOT="$(cd "$DATA_ROOT" && pwd)"

DB="$DATA_ROOT/radiotomate.db"
YAML="$DATA_ROOT/radiotomate.yaml"
[[ -f "$DB" ]] || { echo "missing database: $DB" >&2; exit 1; }
[[ -f "$YAML" ]] || { echo "missing config: $YAML" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${2:-$DATA_ROOT/backups/radiotomate-$STAMP.tar.gz}"
mkdir -p "$(dirname "$DEST")"
DEST="$(cd "$(dirname "$DEST")" && pwd)/$(basename "$DEST")"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/radiotomate-backup.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

STAGE="$WORKDIR/radiotomate"
mkdir -p "$STAGE"

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 is required" >&2
  exit 1
fi

sqlite3 "$DB" ".backup '$STAGE/radiotomate.db'"
cp -p "$YAML" "$STAGE/radiotomate.yaml"

copy_tree() {
  local name="$1"
  if [[ -e "$DATA_ROOT/$name" ]]; then
    cp -a "$DATA_ROOT/$name" "$STAGE/$name"
  fi
}

copy_tree carts
copy_tree Beets
copy_tree Music
copy_tree MusicDropbox
if [[ -f "$DATA_ROOT/start.wav" ]]; then
  cp -p "$DATA_ROOT/start.wav" "$STAGE/start.wav"
fi

(
  cd "$STAGE"
  if command -v sha256sum >/dev/null 2>&1; then
    find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  else
    find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
  fi
)

tar -C "$WORKDIR" -czf "$DEST" radiotomate
chmod 600 "$DEST"

echo "$DEST"
