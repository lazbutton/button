#!/usr/bin/env bash
# Restaure une archive créée par backup-radiotomate.sh vers une cible vide.
set -euo pipefail

umask 077

usage() {
  echo "usage: restore-radiotomate.sh ARCHIVE EMPTY_TARGET" >&2
  exit 2
}

ARCHIVE="${1:-}"
TARGET="${2:-}"
[[ -n "$ARCHIVE" && -n "$TARGET" ]] || usage
[[ -f "$ARCHIVE" ]] || { echo "missing archive: $ARCHIVE" >&2; exit 1; }

if [[ -e "$TARGET" ]]; then
  if [[ ! -d "$TARGET" ]]; then
    echo "target exists and is not a directory: $TARGET" >&2
    exit 1
  fi
  if [[ -n "$(ls -A "$TARGET" 2>/dev/null || true)" ]]; then
    echo "refusing to restore into a non-empty directory: $TARGET" >&2
    exit 1
  fi
else
  mkdir -p "$TARGET"
fi

TARGET="$(cd "$TARGET" && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/radiotomate-restore.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

tar -xzf "$ARCHIVE" -C "$WORKDIR"
STAGE="$WORKDIR/radiotomate"
if [[ ! -d "$STAGE" ]]; then
  echo "archive does not contain a radiotomate/ directory" >&2
  exit 1
fi

hash_check() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c SHA256SUMS
  else
    shasum -a 256 -c SHA256SUMS
  fi
}

if [[ -f "$STAGE/SHA256SUMS" ]]; then
  (
    cd "$STAGE"
    hash_check >/dev/null
  )
else
  echo "warning: archive has no SHA256SUMS; skipping checksum verification" >&2
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 is required" >&2
  exit 1
fi

if [[ ! -f "$STAGE/radiotomate.db" ]]; then
  echo "archive is missing radiotomate.db" >&2
  exit 1
fi

integrity="$(sqlite3 "$STAGE/radiotomate.db" "PRAGMA integrity_check;")"
if [[ "$integrity" != "ok" ]]; then
  echo "sqlite integrity_check failed: $integrity" >&2
  exit 1
fi

cp -a "$STAGE"/. "$TARGET"/
chmod 600 "$TARGET/radiotomate.db" "$TARGET/radiotomate.yaml" 2>/dev/null || true

echo "$TARGET"
