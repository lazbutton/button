#!/bin/sh
# Banc local : interface du moteur en mode démo + console en dev.
# Aucun Liquidsoap, aucun service distant : tout reste sur cette machine.
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
radio=$root/engine
console=$root/console
# Homebrew (macOS) : Poetry et Node y sont souvent installés.
[ -d /opt/homebrew/bin ] && export PATH="/opt/homebrew/bin:$PATH"

if [ ! -d "$radio" ] || [ ! -d "$console" ]; then
  echo "Dossier manquant." >&2
  echo "  moteur  : $radio" >&2
  echo "  console : $console" >&2
  exit 1
fi

if lsof -nP -iTCP:6811 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Le port 6811 est déjà pris : l’interface tourne peut-être déjà." >&2
  exit 1
fi
if lsof -nP -iTCP:5175 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Le port 5175 est déjà pris : la console tourne peut-être déjà." >&2
  exit 1
fi

pids=""
cleanup() {
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Interface démo  http://127.0.0.1:6811"
( cd "$radio" && poetry run radiotomate -c radio_data/radiotomate.yaml interface --demo ) &
pids="$pids $!"

echo "Console         http://127.0.0.1:5175"
( cd "$console" && npm run dev ) &
pids="$pids $!"

wait
