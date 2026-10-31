#!/usr/bin/env bash
# Les vérifications de la CI, sur cette machine.
#   ./scripts/verifier.sh                  tout ce qui peut tourner ici
#   ./scripts/verifier.sh moteur console   seulement ces parties
# Parties : donnees, licences, moteur, liquidsoap, console, services, nginx,
# deploy, e2e.
# Sans argument, une partie qui manque d'un outil (Docker…) est sautée.
# Nommée, elle échoue.
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
# Homebrew (macOS) : Poetry, Node et Docker y sont souvent installés.
[ -d /opt/homebrew/bin ] && export PATH="/opt/homebrew/bin:$PATH"

all=(donnees licences moteur liquidsoap console services nginx deploy e2e)
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

# Les exceptions de la partie donnees : un fichier, ce qu'elle y laisse passer
# (un nom de motif de check_donnees), puis le motif (-E) des lignes concernées.
# Jamais un dossier, jamais une donnée de station : le motif décrit la ligne.
# Une exception qui ne laisse plus rien passer fait échouer la partie.
exceptions_donnees=(
  # Les tests de la limite des connexions par adresse : nginx sur un réseau
  # privé, et un pair qui n'est pas un proxy. Des adresses de test.
  engine/tests/scheduler/test_login_guard.py 'adresse IP privée' '"(::ffff:)?(10\.0\.0\.2|172\.18\.0\.5|192\.168\.1\.10|100\.64\.0\.1)"'
  engine/tests/scheduler/test_login_json.py 'adresse IP privée' '"172\.18\.0\.5"'
  # À retirer avec GEN-02 : le partage SMB de la station d'origine.
  console/public/brand.json 'adresse IP privée' '"smbHost": "'
  # À retirer avec GEN-02 : les adresses Tailscale de la station d'origine.
  console/public/brand.json 'nom en .ts.net' '"(url|stream|status|nowUrl|tailscaleBase)": "http://'
  # À retirer avec GEN-02 : le partage SMB et les adresses de la station
  # d'origine, sur son réseau local.
  engine/radiotomate/brand.json 'adresse IP privée' '"(smbHost|url|stream|status)": "'
  # À retirer avec GEN-02 : l'adresse Tailscale de la station d'origine.
  engine/radiotomate/brand.json 'nom en .ts.net' '"tailscaleBase": "'
  # À retirer avec GEN-02 : le NAS de la station d'origine, écouté sans tampon.
  console/src/lib/monitorPcm.ts 'adresse IP privée' 'host === "'
)

check_donnees() {
  git -C "$root" rev-parse --git-dir >/dev/null 2>&1 ||
    missing "git absent, ou pas de dépôt git : aucun fichier suivi à lire." || return
  cd "$root"
  # Ce qui n'entre jamais dans le dépôt : un nom, puis un motif étendu, sans
  # tenir compte de la casse. Les adresses privées : celles de la RFC 1918, et
  # celles de Tailscale, dans la plage de la RFC 6598 ou sous son préfixe IPv6.
  # Pas de \b, que git grep -E ignore sur macOS : ce qui borde le motif est
  # écrit. Une adresse ne prolonge pas un nombre pointé, comme une version,
  # mais peut finir un nom, comme chez nip.io. Aucun motif ne doit se trouver
  # lui-même dans ce fichier.
  local motifs=(
    'adresse IP privée' '(^\.?|[^0-9.]|[^0-9]\.)(10\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])|192\.168|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7]))\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)|fd7a:115c:a1e0:[0-9a-f:]'
    'nom en .ts.net' '[a-z0-9-]\.ts\.net([^a-z0-9-]|$)'
    'clé privée' '-----BEGIN [A-Z ]*PRIVATE KEY'
    'jeton GitHub' 'gh[pousr]_[a-z0-9]{36}|github_pat_[a-z0-9_]{22,}'
    'jeton GitLab' 'glpat-[a-z0-9_-]{20,}'
  )
  # Ceux d'une station sont dans .motifs-station, ignoré par git : leur liste
  # est elle-même une donnée de la station. Un motif par ligne, # commente.
  # Un worktree sans motif à lui prend ceux de la copie principale.
  local station lus=""
  for station in "$root/.motifs-station" \
    "$(git worktree list --porcelain | sed -n '1s/^worktree //p')/.motifs-station"; do
    [ -f "$station" ] || continue
    lus=$(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; /^(#|$)/d; s/.*/(&)/' "$station" |
      paste -sd '|' -)
    [ -z "$lus" ] || break
  done
  if [ -n "$lus" ]; then
    motifs+=('motif de la station' "$lus")
    echo "Motifs de la station : $station"
  else
    echo "Aucun motif propre à la station : voir docs/developpement.md."
  fi

  # Une plage privée entière, comme dans une liste de proxys de confiance,
  # n'est l'adresse de personne : une ligne ne compte que s'il lui reste une
  # adresse, ces plages ôtées.
  local plages='(^|[^0-9.])(10\.0\.0\.0/8|172\.16\.0\.0/12|192\.168\.0\.0/16|100\.64\.0\.0/10)([^0-9]|$)'

  # Les fichiers suivis, et ceux que git n'ignore pas mais ne suit pas encore,
  # sauf ceux qu'il tient pour binaires. Le rapport donne le fichier, la ligne
  # et ce qui est trouvé, jamais la donnée : le journal de la CI est public.
  local trouvees=0 servie=" " lignes ligne chemin reste nette i j
  for ((i = 0; i < ${#motifs[@]}; i += 2)); do
    lignes=$(git -c core.quotePath=false grep --no-color --no-column -n -I -i -E \
      --untracked -e "${motifs[i + 1]}") || [ $? -eq 1 ] || return
    while IFS= read -r ligne; do
      [ -n "$ligne" ] || continue
      chemin=${ligne%%:*}
      reste=${ligne#*:}
      if [ "${motifs[i]}" = 'adresse IP privée' ]; then
        nette=$(sed -E -e ':a' -e "s#$plages#\\1\\3#" -e 'ta' <<<"${reste#*:}")
        # Une erreur de grep (2) garde la ligne : rien ne passe en silence.
        grep -q -i -E -e "${motifs[i + 1]}" <<<"$nette" || [ $? -eq 2 ] || continue
      fi
      for ((j = 0; j < ${#exceptions_donnees[@]}; j += 3)); do
        if [ "$chemin" = "${exceptions_donnees[j]}" ] &&
          [ "${motifs[i]}" = "${exceptions_donnees[j + 1]}" ] &&
          [[ ${reste#*:} =~ ${exceptions_donnees[j + 2]} ]]; then
          servie="$servie$j "
          continue 2
        fi
      done
      [ "$trouvees" -gt 0 ] || echo "Données de station dans les fichiers du dépôt :" >&2
      echo "  $chemin:${reste%%:*} : ${motifs[i]}" >&2
      trouvees=$((trouvees + 1))
    done <<<"$lignes"
  done
  [ "$trouvees" -eq 0 ] ||
    echo "Les retirer. Pour un exemple : radio.example, change-me, ou une adresse de 192.0.2.0/24 (RFC 5737)." >&2
  local perimees=0
  for ((j = 0; j < ${#exceptions_donnees[@]}; j += 3)); do
    case $servie in
      *" $j "*) continue ;;
    esac
    [ "$perimees" -gt 0 ] || echo "Exceptions sans objet, à retirer de scripts/verifier.sh :" >&2
    echo "  ${exceptions_donnees[j]} (${exceptions_donnees[j + 1]}) : ${exceptions_donnees[j + 2]}" >&2
    perimees=$((perimees + 1))
  done
  [ $((trouvees + perimees)) -eq 0 ] || return 1
  echo "Rien d'une station dans les fichiers du dépôt. Exceptions : $((${#exceptions_donnees[@]} / 3))."
}

check_licences() {
  python3 -c 'import tomllib' 2>/dev/null ||
    missing "Python 3.11 ou plus absent : installer Python 3.13, celui de la CI." || return
  cd "$root"
  # Comme licences.yml. Le moteur et le catalogue se lisent dans leur
  # environnement : s'il manque, le reste est contrôlé, puis la partie sautée.
  python3 scripts/test_licences.py
  python3 scripts/licences.py npm console/package-lock.json engine/sass/package-lock.json
  local manque=0
  if command -v poetry >/dev/null 2>&1; then
    (cd engine && poetry run python ../scripts/licences.py poetry poetry.lock)
  else
    echo "Poetry absent, moteur non contrôlé : https://python-poetry.org/docs/#installation" >&2
    manque=1
  fi
  local catalogue=services/catalog/.venv/bin/python
  if "$catalogue" -c 'import mutagen, watchdog' 2>/dev/null; then
    "$catalogue" scripts/licences.py pip
  else
    echo "Dépendances du catalogue absentes, catalogue non contrôlé. Une fois :" >&2
    echo "  python3 -m venv services/catalog/.venv" >&2
    echo "  services/catalog/.venv/bin/pip install -r services/catalog/requirements.txt" >&2
    manque=1
  fi
  [ "$manque" -eq 0 ] || return "$absent"
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
    nginx:1.30-alpine sh -c '
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

check_e2e() {
  command -v node >/dev/null 2>&1 || missing "Node absent : installer Node 22." || return
  command -v poetry >/dev/null 2>&1 ||
    missing "Poetry absent : https://python-poetry.org/docs/#installation" || return
  command -v curl >/dev/null 2>&1 || missing "curl absent : l'installer." || return
  # Les parcours sur leur propre banc, comme le job e2e de la CI. Il prend des
  # ports libres : scripts/dev.sh peut tourner à côté.
  "$root/scripts/e2e.sh"
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
    donnees | licences | moteur | liquidsoap | console | services | nginx | deploy | e2e) ;;
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
