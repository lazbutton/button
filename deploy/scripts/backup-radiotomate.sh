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

# sqlite3, sinon Python et son module sqlite3, par la même API de sauvegarde :
# l'image du moteur n'a que Python, et station backup y lance ce script.
if sqlite3 -version >/dev/null 2>&1; then
  backup_db() {
    sqlite3 "$1" ".backup '$2'"
  }
elif command -v python3 >/dev/null 2>&1; then
  backup_db() {
    python3 - "$1" "$2" <<'PY'
import sqlite3
import sys
from contextlib import closing

with closing(sqlite3.connect(sys.argv[1])) as source, closing(sqlite3.connect(sys.argv[2])) as copy:
    source.backup(copy)
PY
  }
else
  echo "sqlite3 is required: install it (apt install sqlite3), then retry." >&2
  exit 1
fi
backup_db "$DB" "$STAGE/radiotomate.db"
cp -p "$YAML" "$STAGE/radiotomate.yaml"

copy_tree() {
  local name="$1"
  if [[ -e "$DATA_ROOT/$name" ]]; then
    cp -a "$DATA_ROOT/$name" "$STAGE/$name"
  fi
}

copy_tree carts
copy_tree Beets
# La bibliothèque de Beets change pendant l'antenne, quand il indexe un envoi :
# elle se copie comme la base, sans son journal.
if [[ -f "$DATA_ROOT/Beets/library.db" ]]; then
  rm -f "$STAGE/Beets/library.db"{,-journal,-wal,-shm}
  backup_db "$DATA_ROOT/Beets/library.db" "$STAGE/Beets/library.db"
fi
copy_tree Music
copy_tree MusicDropbox
# Le son de démarrage, sous le nom que lui donne radiotomate install.
for sound in default_start_sound.wav start.wav; do
  if [[ -f "$DATA_ROOT/$sound" ]]; then
    cp -p "$DATA_ROOT/$sound" "$STAGE/$sound"
  fi
done

(
  cd "$STAGE"
  # find écarte SHA256SUMS, que la redirection crée en même temps : rien ne le lit.
  # shellcheck disable=SC2094
  if command -v sha256sum >/dev/null 2>&1; then
    find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  else
    find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
  fi
)

tar -C "$WORKDIR" -czf "$DEST" radiotomate
chmod 600 "$DEST"

echo "$DEST"
