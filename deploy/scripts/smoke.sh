#!/usr/bin/env bash
# Contrôle après une installation ou une mise à jour : l'antenne tourne-t-elle ?
# Sans compte, depuis le dossier de la station, celui de compose.yml :
#   scripts/smoke.sh http://127.0.0.1:30126 http://127.0.0.1:18000/button.mp3
# Cinq points, dans l'ordre. Au premier qui échoue, le script le nomme, dit quel
# journal lire, et sort en 1. SMOKE_WAIT : l'attente de la santé du moteur, en
# secondes, 120 par défaut.
set -euo pipefail

usage() {
  echo "usage: smoke.sh CONSOLE_URL STREAM_URL" >&2
  echo "  depuis le dossier de la station : scripts/smoke.sh http://127.0.0.1:30126 http://127.0.0.1:18000/button.mp3" >&2
  exit 2
}

[[ $# -eq 2 && -n $1 && -n $2 ]] || usage
CONSOLE="${1%/}"
STREAM="$2"
WAIT="${SMOKE_WAIT:-120}"
case $WAIT in
  '' | *[!0-9]*)
    echo "SMOKE_WAIT vaut « $WAIT » : mettre un nombre de secondes, par exemple 300." >&2
    exit 2
    ;;
esac
# En base 10 : bash lirait 0120 en octal.
WAIT=$((10#$WAIT))
for tool in docker curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool est absent : l'installer, puis relancer." >&2
    exit 1
  fi
done

ENGINE=(radiotomate-playout radiotomate-interface radiotomate-scheduler)
# Assez pour être le flux, et non une page d'erreur. Icecast en envoie 64 Ko
# d'un coup à chaque auditeur qui arrive (burst-size).
AUDIO_BYTES=16384
# Dans un conteneur, sans curl : Python lit l'adresse. Rien si elle répond 200,
# sinon la raison, avec la réponse reçue.
READ='import sys, urllib.request
try:
    status = urllib.request.urlopen(sys.argv[1], timeout=5).status
except OSError as error:
    body = error.read().decode(errors="replace") if hasattr(error, "read") else ""
    sys.exit(f"{error} {body}".strip())
sys.exit(0 if status == 200 else f"HTTP {status}")'

fail() { # point, constat, quoi faire
  echo "Échec au point $1. $2" >&2
  echo "$3" >&2
  exit 1
}

# Une requête sans cookie, d'au plus $2 secondes : « code|octets|type|raison ».
# Code 000 : rien n'a répondu, et la raison dit pourquoi. --disable écarte
# ~/.curlrc, dont les réglages changeraient les réponses.
probe() {
  curl --disable --silent --output /dev/null --max-time "$2" \
    --write-out '%{http_code}|%{size_download}|%{content_type}|%{errormsg}' "$1" || true
}

# Pour un message : « répond 503 », ou « ne répond pas (raison) ».
answer() { # code, raison
  if [[ $1 == 000 ]]; then
    echo "ne répond pas ($2)"
  else
    echo "répond $1"
  fi
}

# Une adresse lue de l'intérieur d'un service, qui n'est pas forcément publié.
inside() { # service, adresse dans le conteneur
  docker compose exec -T "$1" python3 -c "$READ" "$2" </dev/null 2>&1
}

# 1. Les trois services du moteur sont healthy. Sans -a, docker compose ps ne
# liste que les conteneurs qui tournent ou redémarrent, sans ceux de
# docker compose run. Un service absent de la liste est arrêté : il ne repart
# pas seul, inutile de l'attendre.
deadline=$((SECONDS + WAIT))
waited=""
while :; do
  if ! states="$(docker compose ps --format '{{.Service}} {{.State}} {{.Health}}' "${ENGINE[@]}" 2>&1)"; then
    fail "1, moteur" "docker compose ps a échoué : $states" \
      "Lancer le script depuis le dossier de la station, celui de compose.yml, avec un compte qui a accès à Docker."
  fi
  stopped=""
  unwell=""
  names=""
  for service in "${ENGINE[@]}"; do
    read -r state health <<<"$(awk -v service="$service" '$1 == service { print $2, $3 }' <<<"$states")"
    case "$state $health" in
      "running healthy") continue ;;
      " ") stopped="$stopped, $service" ;;
      *) unwell="$unwell, $service (${health:-$state})" ;;
    esac
    names="$names $service"
  done
  if [[ -n $stopped ]]; then
    # Un playout qui n'est jamais en bonne santé laisse l'interface et le
    # scheduler non démarrés : la cause est nommée elle aussi.
    problem="À l'arrêt : ${stopped#, }."
    [[ -z $unwell ]] || problem="$problem Pas en bonne santé : ${unwell#, }."
    fail "1, moteur" "$problem" "Voir pourquoi : docker compose logs radiotomate-init$names"
  fi
  [[ -n $unwell ]] || break
  if ((SECONDS >= deadline)); then
    fail "1, moteur" "Pas en bonne santé au bout de $WAIT s : ${unwell#, }." "Voir : docker compose logs --since 10m$names"
  fi
  if [[ -z $waited ]]; then
    echo "1. Moteur : attente de la santé, $WAIT s au plus : ${unwell#, }."
    waited=1
  fi
  left=$((deadline - SECONDS))
  sleep $((left < 5 ? left : 5))
done
echo "1. Moteur : playout, interface et scheduler en bonne santé."

# 2. La console répond, et relaie le moteur.
for path in / /health/ready; do
  IFS='|' read -r code _ _ why <<<"$(probe "$CONSOLE$path" 10)"
  if [[ $code != 200 ]]; then
    fail "2, console" "$CONSOLE$path $(answer "$code" "$why"), il faut 200." \
      "Vérifier l'adresse, puis voir : docker compose logs --since 10m console radiotomate-interface"
  fi
done
echo "2. Console : / et /health/ready répondent 200."

# 3. Le scheduler n'est pas publié : son /health/ready se lit de l'intérieur.
if ! why="$(inside radiotomate-scheduler http://127.0.0.1:6822/health/ready)"; then
  fail "3, scheduler" "/health/ready ne répond pas 200 : $why" \
    "Voir : docker compose logs --since 10m radiotomate-scheduler"
fi
echo "3. Scheduler : /health/ready répond 200."

# 4. Sans compte, la médiathèque ne répond pas.
IFS='|' read -r code _ _ why <<<"$(probe "$CONSOLE/library/search?q=a" 10)"
if [[ $code != 401 ]]; then
  fail "4, catalogue" "Sans cookie, $CONSOLE/library/search?q=a $(answer "$code" "$why"), il faut 401." \
    "La médiathèque ne doit répondre qu'à un compte. Voir : docker compose logs --since 10m console"
fi
echo "4. Catalogue : sans cookie, la recherche répond 401."

# 5. Le flux public envoie de l'audio, et now.json répond. Un flux ne finit
# jamais : la lecture s'arrête au bout de 5 s.
IFS='|' read -r code bytes type why <<<"$(probe "$STREAM" 5)"
if [[ $code != 200 ]]; then
  problem="$STREAM $(answer "$code" "$why"), il faut 200"
elif [[ $type != audio/* && $type != application/ogg* ]]; then
  problem="$STREAM répond en ${type:-type inconnu}, pas en audio"
elif ((bytes < AUDIO_BYTES)); then
  problem="$STREAM n'a envoyé que $bytes octets, il en faut $AUDIO_BYTES"
else
  problem=""
fi
if [[ -n $problem ]]; then
  fail "5, flux" "$problem." "Voir : docker compose logs --since 10m radiotomate-playout icecast"
fi
if ! why="$(inside nowplaying http://127.0.0.1:6820/now.json)"; then
  fail "5, flux" "now.json ne répond pas 200 : $why" "Voir : docker compose logs --since 10m nowplaying"
fi
echo "5. Flux : de l'audio ($type, $bytes octets), et now.json répond."
echo "Contrôle réussi : l'antenne tourne."
