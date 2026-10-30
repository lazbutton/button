#!/usr/bin/env bash
# Restaure une archive créée par backup-radiotomate.sh vers une cible vide.
# Ou remet une copie de la base seule, comme celles que `radiotomate update` fait
# avant une migration, à la place de radiotomate.db : moteur arrêté.
set -euo pipefail

umask 077

usage() {
  echo "usage: restore-radiotomate.sh ARCHIVE EMPTY_TARGET" >&2
  echo "       restore-radiotomate.sh COPY.db DATA_ROOT" >&2
  exit 2
}

ARCHIVE="${1:-}"
TARGET="${2:-}"
[[ -n "$ARCHIVE" && -n "$TARGET" ]] || usage
if [[ ! -f "$ARCHIVE" ]]; then
  echo "missing archive, or not readable: $ARCHIVE. Check the path, or run as root." >&2
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 is required: install it (apt install sqlite3), then retry." >&2
  exit 1
fi

# Sans ~/.sqliterc : ses réglages changeraient la sortie comparée plus bas.
sql() {
  sqlite3 -batch -noheader -init /dev/null "$@"
}

check_integrity() {
  local result
  result="$(sql "$1" "PRAGMA integrity_check;" 2>&1 || true)"
  if [[ "$result" != "ok" ]]; then
    echo "sqlite integrity_check failed, choose another backup: $result" >&2
    exit 1
  fi
}

if [[ "$ARCHIVE" == *.db ]]; then
  if [[ ! -f "$TARGET/radiotomate.yaml" ]]; then
    echo "not a data folder, radiotomate.yaml is missing: $TARGET. Give the engine's data folder, RT_DATA." >&2
    exit 1
  fi
  TARGET="$(cd "$TARGET" && pwd)"
  DB="$TARGET/radiotomate.db"
  # Déjà en place, sauf si un journal porte des écritures faites depuis.
  if [[ -f "$DB" && ! -e "$DB-wal" && ! -e "$DB-journal" ]] && cmp -s "$ARCHIVE" "$DB"; then
    echo "already in place: $DB" >&2
    echo "$DB"
    exit 0
  fi
  # La copie est vérifiée là où elle sera posée : un mv final, sans risque de
  # base à moitié copiée.
  INCOMING="$DB.restore"
  ASIDE="$TARGET/backups/avant-restauration-$(date -u +%Y%m%dT%H%M%SZ).db"
  if [[ -e "$INCOMING" ]]; then
    echo "already exists: $INCOMING. Another restore may be running; if none is, remove it, then retry." >&2
    exit 1
  fi
  trap 'rm -f "$INCOMING" "$ASIDE.part"' EXIT
  cp "$ARCHIVE" "$INCOMING"
  check_integrity "$INCOMING"
  version="$(sql "$INCOMING" "SELECT value FROM settings WHERE key='SCHEMA_VERSION';" 2>/dev/null || true)"
  if [[ -z "$version" ]]; then
    echo "not a Radiotomate database, no schema version: $ARCHIVE. Choose a copy in RT_DATA/backups/." >&2
    exit 1
  fi

  # Quitter le mode WAL demande que plus personne n'ait la base ouverte : refusé
  # tant que le moteur tourne. Sinon, le WAL rejoint la base mise de côté.
  if [[ -f "$DB" && "$(sql "$DB" "PRAGMA journal_mode=DELETE;" 2>/dev/null || true)" != "delete" ]]; then
    echo "database in use or unreadable: $DB" >&2
    echo "stop the engine first: docker compose stop radiotomate-scheduler radiotomate-interface radiotomate-playout radiotomate-dropbox" >&2
    echo "if it is stopped and the database is damaged, move radiotomate.db and its -wal away by hand, then retry." >&2
    exit 1
  fi
  # Un journal resté sans sa base serait rejoué sur la copie.
  for orphan in "$DB-wal" "$DB-journal"; do
    if [[ -e "$orphan" ]]; then
      echo "left without its database: $orphan. Move it away with the database it belongs to, then retry." >&2
      exit 1
    fi
  done
  if [[ -f "$DB" ]]; then
    if [[ -e "$ASIDE" ]]; then
      echo "already exists: $ASIDE. Wait a second, then retry." >&2
      exit 1
    fi
    mkdir -p "$TARGET/backups"
    # Un lien, sinon une copie, puis un seul mv : même interrompu, le script ne
    # laisse jamais le dossier sans base.
    if ! ln "$DB" "$ASIDE" 2>/dev/null; then
      if ! cp -p "$DB" "$ASIDE.part"; then
        echo "could not keep the current database in $TARGET/backups/: free some space, then retry." >&2
        exit 1
      fi
      mv "$ASIDE.part" "$ASIDE"
    fi
    echo "replaced database kept as $ASIDE" >&2
  fi
  rm -f "$DB-shm"
  mv "$INCOMING" "$DB"
  echo "restored schema version: $version. Pin the engine image of that version (RT_TAG) before starting it, or radiotomate-init migrates it again." >&2
  echo "$DB"
  exit 0
fi

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

if [[ ! -f "$STAGE/radiotomate.db" ]]; then
  echo "archive is missing radiotomate.db" >&2
  exit 1
fi

check_integrity "$STAGE/radiotomate.db"

cp -a "$STAGE"/. "$TARGET"/
chmod 600 "$TARGET/radiotomate.db" "$TARGET/radiotomate.yaml" 2>/dev/null || true

echo "$TARGET"
