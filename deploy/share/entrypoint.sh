#!/bin/sh
# Partage Finder. Refuse d'écouter sur toutes les interfaces, sauf demande explicite.
set -eu

if ! python3 -c 'import os, sys, apply_share
ok = apply_share.bind_ok(os.environ.get("SMB_BIND", ""), os.environ.get("SMB_ALLOW_PUBLIC") == "1")
sys.exit(0 if ok else 1)'; then
  echo "SMB_BIND refusé. Indique l'adresse Tailscale de la station. 0.0.0.0 exige SMB_ALLOW_PUBLIC=1." >&2
  exit 1
fi

python3 -c 'import apply_share; apply_share.write_smb_conf(); apply_share.sync_once()'

( while true; do
    python3 -c 'import apply_share; apply_share.sync_once()' || true
    sleep 15
  done ) &

exec smbd --foreground --no-process-group
