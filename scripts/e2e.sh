#!/usr/bin/env bash
# Les parcours de la console dans un vrai navigateur (Playwright).
#   ./scripts/e2e.sh                        tous les parcours
#   ./scripts/e2e.sh e2e/antenne.spec.ts    les arguments vont à Playwright
# Le banc tient dans un dossier du lancement, .e2e/<date>-<pid>/ : moteur de
# démo semé par engine/tests/e2e/seed.py, faux catalogue et faux tusd, build
# de la console servi par vite preview. Chacun prend un port libre : deux
# lancements, ou un lancement et scripts/dev.sh, tournent ensemble. Le dossier
# est effacé si tout passe ; sinon il garde les journaux et les traces.
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
engine=$root/engine
console=$root/console
# Homebrew (macOS) : Poetry et Node y sont souvent installés.
[ -d /opt/homebrew/bin ] && export PATH="/opt/homebrew/bin:$PATH"
# Comme la CI et la station : l'heure de Paris.
export TZ=Europe/Paris

command -v node >/dev/null 2>&1 || { echo "Node absent : installer Node 22." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl absent : l'installer." >&2; exit 1; }
command -v poetry >/dev/null 2>&1 ||
  { echo "Poetry absent : https://python-poetry.org/docs/#installation" >&2; exit 1; }
[ -x "$console/node_modules/.bin/playwright" ] ||
  { echo "Lancer d'abord : cd console && npm install" >&2; exit 1; }
venv=$(cd "$engine" && poetry env info --path 2>/dev/null) || venv=""
[ -n "$venv" ] && [ -x "$venv/bin/radiotomate" ] ||
  { echo "Lancer d'abord : cd engine && poetry install" >&2; exit 1; }

run=$root/.e2e/$(date +%Y%m%d-%H%M%S)-$$
mkdir -p "$run"
pids=""
passed=0

cleanup() {
  local pid alive _
  # Un second Ctrl-C n'interrompt pas le ménage.
  trap '' INT TERM
  set +e
  for pid in $pids; do kill "$pid" 2>/dev/null; done
  # Le moteur s'arrête proprement sur TERM ; au-delà de 5 s, on tranche, et
  # seulement les processus encore là : un PID libéré peut servir à un autre.
  for _ in $(seq 50); do
    alive=""
    for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive="$alive $pid"; done
    [ -z "$alive" ] && break
    sleep 0.1
  done
  for pid in $alive; do kill -9 "$pid" 2>/dev/null; done
  wait 2>/dev/null
  if [ "$passed" -eq 1 ]; then
    rm -rf "$run"
    rmdir "$root/.e2e" 2>/dev/null
  else
    echo "Journaux, données et traces du lancement : ${run#"$root"/}" >&2
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# Démarre un service en arrière-plan depuis un dossier, son journal dans le
# dossier du lancement. Son PID reste dans $last.
start() {
  local name=$1 dir=$2
  shift 2
  (cd "$dir" && exec "$@") >"$run/$name.log" 2>&1 &
  last=$!
  pids="$pids $last"
}

# Attend qu'une adresse réponde, tant que son service tourne.
wait_for() {
  local name=$1 pid=$2 url=$3 method=${4:-GET} _
  for _ in $(seq 120); do
    curl -fsS -o /dev/null -X "$method" "$url" 2>/dev/null && return
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$name s'est arrêté au démarrage. Si son journal dit que le port est pris, relancer :" >&2
      tail -n 20 "$run/$name.log" >&2
      exit 1
    fi
    sleep 0.25
  done
  echo "$name ne répond pas sur $url après 30 s :" >&2
  tail -n 20 "$run/$name.log" >&2
  exit 1
}

echo "Banc des parcours : ${run#"$root"/}"
(cd "$engine" && "$venv/bin/python" -m tests.e2e.seed "$run") >"$run/semis.log" 2>&1 ||
  { echo "Semis impossible :" >&2; tail -n 20 "$run/semis.log" >&2; exit 1; }
(cd "$console" && node_modules/.bin/vite build --outDir "$run/console" --emptyOutDir --logLevel error) ||
  { echo "Build de la console impossible." >&2; exit 1; }

# Quatre ports libres et distincts, donnés par le système, jamais ceux du banc
# de dev ni de la station : scripts/dev.sh peut tourner en même temps.
read -r port_engine port_catalog port_tusd port_console < <(node -e '
  const net = require("node:net");
  const station = new Set([5175, 5176, 6800, 6811, 6822, 6833, 8080, 30127]);
  const open = () => new Promise((done) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => done(server));
  });
  (async () => {
    const servers = [];
    const free = () => servers.map((s) => s.address().port).filter((p) => !station.has(p));
    while (free().length < 4) servers.push(await open());
    console.log(free().slice(0, 4).join(" "));
    for (const server of servers) server.close();
  })();
') || { echo "Aucun port libre trouvé pour le banc." >&2; exit 1; }

# Les quatre services démarrent ensemble : leurs ports restent libres le moins
# longtemps possible. Les faux services n'appellent le moteur qu'à la demande.
engine_url=http://127.0.0.1:$port_engine
stub=(node --disable-warning=ExperimentalWarning --experimental-strip-types)
start moteur "$run" env MEDIA_ROOT="$run/media" "$venv/bin/radiotomate" \
  -c "$run/radio_data/radiotomate.yaml" interface --demo --port "$port_engine"
pid_engine=$last
start catalogue "$console" "${stub[@]}" e2e/stubs/catalogue.ts "$port_catalog" "$run/media" "$engine_url"
pid_catalog=$last
start tusd "$console" "${stub[@]}" e2e/stubs/tusd.ts "$port_tusd" "$run/envois" "$engine_url"
pid_tusd=$last
start console "$console" env \
  E2E_MOTEUR="$engine_url" \
  E2E_CATALOGUE="http://127.0.0.1:$port_catalog" \
  E2E_TUSD="http://127.0.0.1:$port_tusd" \
  node_modules/.bin/vite preview --config e2e/vite.config.ts --outDir "$run/console" \
  --port "$port_console" --strictPort
pid_console=$last

# Si ce script meurt sans pouvoir faire le ménage (kill -9), ses services ne
# lui survivent pas plus d'une seconde.
(
  while kill -0 $$ 2>/dev/null; do sleep 1; done
  for pid in $pids; do kill "$pid" 2>/dev/null; done
) &
pids="$pids $!"

wait_for moteur "$pid_engine" "$engine_url/health/ready"
wait_for catalogue "$pid_catalog" "http://127.0.0.1:$port_catalog/health"
wait_for tusd "$pid_tusd" "http://127.0.0.1:$port_tusd/tus/" OPTIONS
wait_for console "$pid_console" "http://127.0.0.1:$port_console/health/ready"

# La chaîne entière, console, relais et moteur, avec un compte semé. Un port
# pris au même moment par un autre lancement mènerait à son moteur : les
# comptes de ce lancement-ci le disent ici, pas au milieu d'un parcours.
node -e '
  const { password, accounts } = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
  fetch(process.argv[2], {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: accounts.admin, password }),
  }).then((response) => process.exit(response.ok ? 0 : 1), () => process.exit(1));
' "$run/comptes.json" "http://127.0.0.1:$port_console/login.json" || {
  echo "La console ne connecte pas le compte admin semé (voir moteur.log et console.log)." >&2
  echo "Si un autre banc démarrait au même moment, il a pu prendre un de ses ports : relancer." >&2
  exit 1
}

# Le navigateur de Playwright, téléchargé une fois par machine, hors du dépôt.
(cd "$console" && node_modules/.bin/playwright install chromium)
if (cd "$console" &&
  E2E_CONSOLE="http://127.0.0.1:$port_console" \
    E2E_COMPTES="$run/comptes.json" \
    E2E_RESULTATS="$run/resultats" \
    node_modules/.bin/playwright test "$@"); then
  passed=1
fi
[ "$passed" -eq 1 ]
