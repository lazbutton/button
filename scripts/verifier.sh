#!/usr/bin/env bash
# Les vérifications de la CI, sur cette machine.
#   ./scripts/verifier.sh                  tout ce qui peut tourner ici
#   ./scripts/verifier.sh moteur console   seulement ces parties
# Parties : moteur, liquidsoap, console, services, nginx, deploy.
# Sans argument, une partie qui manque d'un outil (Docker…) est sautée.
# Nommée, elle échoue.
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
# Homebrew (macOS) : Poetry, Node et Docker y sont souvent installés.
[ -d /opt/homebrew/bin ] && export PATH="/opt/homebrew/bin:$PATH"

all=(moteur liquidsoap console services nginx deploy)
# Code de sortie d'une partie à qui il manque un outil.
absent=75

missing() {
  echo "$1" >&2
  return "$absent"
}

need_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 ||
    missing "Docker absent ou arrêté : lancer Docker, puis relancer."
}

check_moteur() {
  command -v poetry >/dev/null 2>&1 ||
    missing "Poetry absent : https://python-poetry.org/docs/#installation" || return
  cd "$root/engine"
  poetry run ruff check radiotomate tests
  poetry run ruff format --check radiotomate tests
  # Comme la CI : heure de Paris, sans les tests Playwright.
  TZ=Europe/Paris poetry run pytest -q -p no:cacheprovider -o addopts="" \
    tests --ignore=tests/e2e --ignore=tests/interface
}

check_liquidsoap() {
  need_docker || return
  # Le RTCONFIG minimal du job liquidsoap-check, passé sur l'entrée standard :
  # le dossier temporaire du Mac n'est pas toujours monté dans la VM Docker.
  docker run --rm -i --user root --entrypoint sh \
    -v "$root/engine/playout:/playout:ro" \
    docker.io/savonet/liquidsoap:v2.4.5 \
    -c 'cat > /tmp/rtconfig.yaml && RTCONFIG=/tmp/rtconfig.yaml liquidsoap --check /playout/radiotomate.liq' <<'YAML'
playout_process_config:
  input_name: "stream"
  input_min_buffer: 5.
  input_max_buffer: 30.
  token: "ci"
  start_sound: "/tmp/start.wav"
metadata_log:
  extra_fields: []
YAML
}

check_console() {
  command -v npm >/dev/null 2>&1 || missing "Node absent : installer Node 22." || return
  cd "$root/console"
  [ -d node_modules ] || { echo "Lancer d'abord : cd console && npm install" >&2; return 1; }
  npm test
  npm run build
}

check_services() {
  cd "$root/services/catalog"
  local python=${PYTHON:-python3}
  [ -x .venv/bin/python ] && python=.venv/bin/python
  if ! "$python" -c 'import mutagen, watchdog' 2>/dev/null; then
    echo "Dépendances du catalogue absentes. Une fois :" >&2
    echo "  python3 -m venv services/catalog/.venv" >&2
    echo "  services/catalog/.venv/bin/pip install -r services/catalog/requirements.txt" >&2
    return "$absent"
  fi
  # La liste des tests est celle de la CI.
  local tests
  tests=$(sed -nE 's/^ *- run: python (test_[a-z_]+\.py) *$/\1/p' "$root/.github/workflows/services.yml")
  [ -n "$tests" ] || { echo "Aucun test trouvé dans services.yml." >&2; return 1; }
  while IFS= read -r test; do
    echo "-- $test"
    "$python" "$test"
  done <<<"$tests"
}

check_nginx() {
  need_docker || return
  # Les fichiers de console/docker/ vont où le Dockerfile les met, puis le
  # script de démarrage de l'image les rend : le gabarit et ses en-têtes de
  # sécurité. Les relais pointent sur 127.0.0.1 : un nom inconnu ferait
  # échouer nginx -t. Le dépôt est monté, jamais le dossier temporaire du Mac.
  docker run --rm \
    -v "$root/console/docker:/button:ro" \
    -e AUTOMATE_BACKEND=http://127.0.0.1:6811 \
    -e CATALOG_UPSTREAM=http://127.0.0.1:30127 \
    -e TUSD_UPSTREAM=http://127.0.0.1:8080 \
    nginx:1.27-alpine sh -c '
      cp /button/nginx.conf.template /etc/nginx/nginx-default.conf.template &&
      cp /button/security-headers.conf.template /etc/nginx/security-headers.conf.template &&
      sh /button/docker-entrypoint.sh && nginx -t'
}

check_deploy() {
  need_docker || return
  cd "$root/deploy"
  docker compose --env-file .env.example -f compose.yml config --quiet
  docker compose --env-file .env.example -f compose.yml --profile share config --quiet
  echo "compose.yml : valide avec .env.example"
  if command -v shellcheck >/dev/null 2>&1; then
    shellcheck "$root"/scripts/*.sh "$root"/deploy/scripts/*.sh "$root"/deploy/share/entrypoint.sh
    echo "ShellCheck : propre"
  else
    echo "ShellCheck absent, scripts non vérifiés : brew install shellcheck" >&2
  fi
}

# Une partie tourne dans son propre processus : set -e l'y arrête au premier
# échec. Dans un « || » du même processus, bash ignorerait set -e.
if [ "${1:-}" = "--partie" ]; then
  "check_$2"
  exit
fi

if [ "$#" -eq 0 ]; then
  parts=("${all[@]}")
  strict=0
else
  parts=("$@")
  strict=1
fi

passed=""
skipped=""
failed=""
for part in "${parts[@]}"; do
  case $part in
    moteur | liquidsoap | console | services | nginx | deploy) ;;
    *)
      echo "Partie inconnue : $part. Parties : ${all[*]}." >&2
      exit 64
      ;;
  esac
  printf '\n== %s\n' "$part"
  status=0
  bash "$0" --partie "$part" || status=$?
  if [ "$status" -eq 0 ]; then
    passed="$passed $part"
  elif [ "$status" -eq "$absent" ] && [ "$strict" -eq 0 ]; then
    skipped="$skipped $part"
  else
    failed="$failed $part"
  fi
done

echo
if [ -n "$passed" ]; then echo "Bon :$passed"; fi
if [ -n "$skipped" ]; then echo "Sauté, outil absent :$skipped"; fi
if [ -n "$failed" ]; then
  echo "Échec :$failed" >&2
  exit 1
fi
