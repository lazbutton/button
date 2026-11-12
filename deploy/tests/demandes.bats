#!/usr/bin/env bats
# Les tests de station requests, les demandes de la console (MAJ-07) : le
# bouton « Mettre à jour maintenant » écrit une demande dans le moteur, et la
# machine la prend chaque minute, par docker compose exec, puis lance station
# update. Sur une station installée par station install en 0.1.0, la même
# machine jouée par de faux outils que dans station.bats. Le faux docker joue
# le moteur des demandes, dans RT_DATA/updates : engine_updates. Depuis la
# racine du dépôt :
#   ./scripts/verifier.sh deploy

bats_require_minimum_version 1.5.0

setup_file() {
  load helpers
  make_release 0.1.0 "$BATS_FILE_TMPDIR/releases/v0.1.0"
  make_release 0.2.0 "$BATS_FILE_TMPDIR/releases/v0.2.0"
  cat >"$BATS_FILE_TMPDIR/CHANGELOG.md" <<'EOF'
# Journal des changements

## 1.0.0

**Mise en service.** Une station pose le nom de son mount public dans `.env`.

## 0.2.0

- Rien d'autre.
EOF
  RELEASE_CHANGELOG=$BATS_FILE_TMPDIR/CHANGELOG.md make_release 1.0.0 "$BATS_FILE_TMPDIR/releases/v1.0.0"
}

setup() {
  load helpers
  bats_load_library bats-support
  bats_load_library bats-assert
  setup_machine
  UNITS=$ROOT/etc/systemd/system
  REQUEST=abcdef012345
  # La demande ouverte, telle que le faux moteur la garde : « ID ÉTAT ».
  DEMANDE=$DIR/data/radiotomate/updates/demande
}

# Une station en 0.1.0 qui tourne, et une version plus haute publiée.
installed_then() { # la version qui paraît
  installed
  echo "$1" >"$FAKE_STATE/latest"
}

# « Mettre à jour maintenant » : la demande, comme le moteur l'écrit, dans
# l'état donné, pending sans lui.
console_asks() { # état
  mkdir -p "$DIR/data/radiotomate/updates"
  echo "{\"id\": \"$REQUEST\", \"state\": \"${1:-pending}\"}" >"$DIR/data/radiotomate/updates/request.json"
  echo "$REQUEST ${1:-pending}" >"$DEMANDE"
}

# Comment la demande a fini, pour le moteur : son résultat et ses options,
# puis son détail.
result() {
  sed -n 1p "$FAKE_STATE/resultat"
}

detail() {
  sed -n '2,$p' "$FAKE_STATE/resultat"
}

# Ce que la machine a dit d'elle au moteur, la dernière fois.
host_said() {
  cat "$DIR/data/radiotomate/updates/host.json"
}

# Combien de fois le moteur a reçu cette commande.
engine_calls() {
  grep -c "maintenance updates $1" "$FAKE_STATE/log" || true
}

# La ligne de updates.log, sans son heure.
last_update() {
  grep -v '^#' "$DIR/updates.log" | tail -n 1 | cut -f2-
}

# Une passage du minuteur, sous systemd.
by_timer() {
  run env INVOCATION_ID=essai bash "$STATION" requests
}

@test "install pose le minuteur des demandes : chaque minute, station requests" {
  installed
  grep -qxF "ExecStart=\"$DIR/station\" requests --dir \"$DIR\"" "$UNITS/button-demandes.service"
  grep -qxF "OnCalendar=minutely" "$UNITS/button-demandes.timer"
  grep -qxF "Environment=HOME=/root" "$UNITS/button-demandes.service"
  grep -qxF "LogLevelMax=notice" "$UNITS/button-demandes.service"
  # Arrêté en pleine mise à jour, le service laisse au retour arrière le temps
  # de finir.
  grep -qxF "TimeoutStopSec=30min" "$UNITS/button-demandes.service"
  install_station --domain radio.example
  assert_success
  logged "systemctl enable --now button-demandes.timer"
  # Relancée, l'installation ne les réécrit pas, et ne recharge pas systemd
  # pour eux.
  refute_output --partial "Demandes de la console : prises chaque minute"
}

@test "le dépôt d'un fork suit la mise à jour demandée, dans le service" {
  BUTTON_REPO=moi/fork install_station --domain radio.example
  assert_success
  grep -qxF "Environment=BUTTON_REPO=moi/fork" "$UNITS/button-demandes.service"
}

@test "sans demande, un passage ne dit au moteur que ce qui change, ou au bout d'une heure" {
  installed
  # Par le minuteur, sous systemd : rien au journal.
  by_timer
  assert_success
  assert_output ""
  [ "$(engine_calls host)" = 1 ]
  # À la main, la commande le dit.
  station requests
  assert_success
  assert_output "Aucune demande de la console n'attend."
  host_said | grep -qF '"requests":"yes","command":"0.1.0","version":"0.1.0","repo":"lazbutton/button","hold":"","updates":[]'
  host_said | grep -qF '"nightly":"auto","time":"04:00","zone":"Europe/Paris"'
  # Rien de neuf : rien ne part au moteur, pas même une question.
  station requests
  assert_success
  [ "$(engine_calls host)" = 1 ]
  [ "$(engine_calls show)" = 0 ]
  # HOLD posé : le moteur le sait au passage suivant.
  station hold essai de la console
  station requests
  [ "$(engine_calls host)" = 2 ]
  host_said | grep -qF 'Raison : essai de la console'
  # Au bout d'une heure, la machine se redit, même sans rien de neuf.
  sed -i "1s/.*/$(($(date +%s) - 3601))/" "$ROOT/run/button-demandes.etat"
  station requests
  [ "$(engine_calls host)" = 3 ]
  # Une restauration remplace host.json : le moteur réentend la machine.
  rm "$DIR/data/radiotomate/updates/host.json"
  station requests
  [ "$(engine_calls host)" = 4 ]
}

@test "une demande met la station à jour, puis le moteur reçoit le résultat" {
  installed_then 0.2.0
  station requests
  console_asks
  station requests
  assert_success
  assert_output --partial "Demande de la console : mise à jour de la station de $DIR, de 0.1.0 à la plus haute version publiée."
  assert_output --partial "La station est à jour : 0.2.0, au lieu de 0.1.0. Le contrôle passe."
  assert_output --partial "Demande de la console : faite."
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  [ "$(last_update | cut -f1-3)" = "$(printf '0.1.0\t0.2.0\tfaite')" ]
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  detail | grep -Eqx 'redémarrée et contrôlée en [0-9]+ s'
  logged "maintenance updates start $REQUEST"
  [ ! -e "$DIR/demande-en-cours" ]
  [ ! -e "$DEMANDE" ]
  # Puis le moteur sait la nouvelle version, et la ligne de updates.log.
  host_said | grep -qF '"version":"0.2.0"'
  host_said | grep -qF '\t0.1.0\t0.2.0\tfaite\t'
  # Une demande à la fois : un second passage n'en trouve plus.
  : >"$FAKE_STATE/log"
  station requests
  assert_success
  run ! logged "maintenance updates start"
}

@test "une demande attend la fin d'un direct, et dit pourquoi" {
  installed_then 0.2.0
  console_asks
  echo "occupée : QG, un direct, en cours jusqu'à 22:00" >"$FAKE_STATE/window"
  station requests
  assert_success
  [ "$(cat "$FAKE_STATE/attente")" = "QG, un direct, en cours jusqu'à 22:00" ]
  [ "$(cat "$DEMANDE")" = "$REQUEST pending" ]
  run ! logged "maintenance updates start"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  # La fenêtre libre, au passage suivant, elle part.
  station requests
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  [ "$(result | cut -d' ' -f2)" = "done" ]
}

@test "une demande attend une autre commande station, comme la sauvegarde de la nuit" {
  installed_then 0.2.0
  console_asks
  flock "$ROOT/run/button-station.lock" sleep 3 &
  sleep 0.5
  station requests
  assert_success
  grep -qF "Une autre commande station tourne sur la machine, comme la sauvegarde de la nuit" "$FAKE_STATE/attente"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  wait
  station requests
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
}

@test "une commande qui trouve le verrou pris sort avec son code ; pris un instant, il attend" {
  installed_then 0.2.0
  run flock "$ROOT/run/button-station.lock" bash "$STATION" update --yes
  [ "$status" -eq 75 ]
  assert_output --partial "Une autre commande station tourne déjà sur cette machine."
  # Pris un instant, comme quand station requests regarde s'il est libre :
  # la commande attend une seconde.
  flock "$ROOT/run/button-station.lock" sleep 0.5 &
  sleep 0.1
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; lock_station essai && echo pris' _ "$STATION"
  assert_success
  assert_output "pris"
  wait
  # Le code dit à station requests que la mise à jour attend.
  console_asks running
  : >"$FAKE_STATE/attente"
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; dir=$2; env_file=$2/.env; request_id=$3; started=$(date +%s); lines=$(updates_lines)
    requests_outcome 75 /dev/null 0.2.0' _ "$STATION" "$DIR" "$REQUEST"
  assert_success
  grep -qF "Une autre commande station tourne sur la machine" "$FAKE_STATE/attente"
  [ "$(cat "$DEMANDE")" = "$REQUEST pending" ]
}

@test "arrêtée par l'antenne une fois sa sauvegarde faite, la demande attend une heure, sans faire de place dans backups/" {
  installed_then 0.2.0
  # Les sauvegardes de station backup, plus que la mise à jour n'en garde.
  mkdir -p "$DIR/backups"
  for day in 1 2 3 4 5 6; do
    touch "$DIR/backups/button-2026010${day}T030000Z.tar"
  done
  console_asks
  # Libre pour station requests, puis pour station update, puis prise, une
  # fois la sauvegarde faite.
  echo "occupée : QG, un direct, commence à 20:00, dans 25 min" >"$FAKE_STATE/window-later"
  echo 2 >"$FAKE_STATE/window-later-reads"
  station requests
  assert_success
  [ "$(last_update | cut -f3)" = "arrêtée" ]
  grep -qF "Arrêtée par l'antenne, sa sauvegarde faite : QG, un direct, commence à 20:00, dans 25 min." "$FAKE_STATE/attente"
  [ "$(cat "$DEMANDE")" = "$REQUEST pending" ]
  [ ! -e "$DIR/demande-en-cours" ]
  [ ! -e "$FAKE_STATE/resultat" ]
  # Aucune sauvegarde ne s'en va : six d'avant, et celle de la tentative.
  [ "$(find "$DIR/backups" -name 'button-*.tar' | wc -l)" -eq 7 ]

  # Le moteur, qui dit la fenêtre, ne fait pas refaire une sauvegarde chaque
  # minute : la suivante attend une heure.
  : >"$FAKE_STATE/log"
  station requests
  assert_success
  grep -qF "La dernière tentative s'est arrêtée devant l'antenne, sa sauvegarde faite : la suivante part au plus tôt le" "$FAKE_STATE/attente"
  run ! logged "maintenance updates start"
  # Une heure après, elle part, et ne garde alors que les cinq dernières.
  awk -F '\t' -v OFS='\t' -v made=$(($(date +%s) - 3601)) '$4 == "arrêtée" { $1 = made } { print }' \
    "$DIR/updates.log" >"$BATS_TEST_TMPDIR/updates.log"
  cp "$BATS_TEST_TMPDIR/updates.log" "$DIR/updates.log"
  station requests
  assert_success
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  [ "$(find "$DIR/backups" -name 'button-*.tar' | wc -l)" -eq 5 ]
}

@test "le texte de la fenêtre ne forge pas de ligne de updates.log" {
  installed_then 0.2.0
  console_asks
  printf 'occupée : QG\n%s\t0.1.0\t0.2.0\tfaite\t-\tforgée\e[31m\n' "$(date +%s)" >"$FAKE_STATE/window-later"
  echo 2 >"$FAKE_STATE/window-later-reads"
  station requests
  assert_success
  [ "$(grep -vc '^#' "$DIR/updates.log")" -eq 1 ]
  [ "$(last_update | cut -f3,5)" = "$(printf 'arrêtée\tQG')" ]
  [ "$(cat "$DEMANDE")" = "$REQUEST pending" ]
  [ ! -e "$FAKE_STATE/resultat" ]
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
}

@test "arrêtée, et le moteur ne prend pas l'attente : le passage suivant la lui redit" {
  installed_then 0.2.0
  console_asks
  echo "occupée : QG, un direct, commence à 20:00, dans 25 min" >"$FAKE_STATE/window-later"
  echo 2 >"$FAKE_STATE/window-later-reads"
  touch "$FAKE_STATE/wait-fails"
  station requests
  assert_success
  [ "$(cat "$DEMANDE")" = "$REQUEST running" ]
  [ "$(cut -f4 "$DIR/demande-en-cours")" = attente ]
  station requests
  assert_success
  [ "$(cat "$DEMANDE")" = "$REQUEST pending" ]
  [ ! -e "$DIR/demande-en-cours" ]
  [ ! -e "$FAKE_STATE/resultat" ]
}

@test "HOLD refuse la demande, avec sa raison" {
  installed_then 0.2.0
  station hold une raison de la radio
  console_asks
  station requests
  assert_success
  assert_output --partial "Demande de la console : refusée."
  [ "$(result)" = "$REQUEST refused" ]
  detail | grep -qF "Les mises à jour sont bloquées sur la machine, par HOLD : Bloquées par station hold"
  detail | grep -qF "Raison : une raison de la radio"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  run ! logged "maintenance updates start"
}

@test "une station à jour : rien à faire" {
  installed_then 0.1.0
  console_asks
  station requests
  assert_success
  [ "$(result)" = "$REQUEST up_to_date" ]
  detail | grep -qF "La station est déjà en 0.1.0. Rien à faire."
}

@test "une majeure ne part pas d'une demande : elle est refusée, avant rien" {
  installed_then 1.0.0
  console_asks
  station requests
  assert_success
  [ "$(result)" = "$REQUEST refused" ]
  detail | grep -qF "La mise à jour passe la 1.0.0, une version majeure"
  detail | grep -qF "sudo station update --major"
  run ! logged "maintenance updates start"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
}

@test "une mise à jour que le contrôle refuse revient seule : la demande dit qu'elle est annulée" {
  installed_then 0.2.0
  console_asks
  touch "$FAKE_STATE/smoke-fails"
  station requests
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ -f "$DIR/HOLD" ]
  [ "$(result)" = "$REQUEST rolled_back --from 0.1.0 --to 0.2.0" ]
  detail | grep -qF "pendant le contrôle ; revenue en 0.1.0"
  # Le moteur sait HOLD, que la console montre.
  host_said | grep -qF '"hold":"Bloquées par station update'
}

@test "la machine s'arrête pendant la mise à jour : le passage suivant le dit au moteur" {
  installed_then 0.2.0
  console_asks
  # La mise à jour faite, mais le moteur, qui redémarre, ne prend pas le
  # résultat : la marque reste.
  touch "$FAKE_STATE/finish-fails"
  station requests
  assert_success
  assert_output --partial "le moteur ne prend pas le résultat de la demande (done)"
  [ -f "$DIR/demande-en-cours" ]
  [ "$(cat "$DEMANDE")" = "$REQUEST running" ]
  # Le passage suivant le lui dit, d'après updates.log.
  station requests
  assert_success
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  [ ! -e "$DIR/demande-en-cours" ]

  # Une machine qui redémarre en pleine mise à jour : rien dans updates.log.
  console_asks running
  printf '%s\t%s\t%s\n' "$REQUEST" "$(date +%s)" "$(wc -l <"$DIR/updates.log")" >"$DIR/demande-en-cours"
  station requests
  assert_success
  [ "$(result)" = "$REQUEST interrupted" ]
  detail | grep -qF "La mise à jour s'est arrêtée sans rien noter"
  [ ! -e "$DIR/demande-en-cours" ]

  # Sans marque, la machine n'en a pas trace : des données remises, par exemple.
  console_asks running
  station requests
  assert_success
  [ "$(result)" = "$REQUEST interrupted" ]
  detail | grep -qF "La machine n'a pas trace de cette mise à jour"
}

@test "reprise : le résultat est la ligne de la mise à jour lancée, pas une ligne venue après" {
  installed_then 0.2.0
  touch "$FAKE_STATE/smoke-fails"
  # Pas « lines » : run la remplit de la sortie de la commande.
  local before=0
  [[ ! -f $DIR/updates.log ]] || before=$(wc -l <"$DIR/updates.log")
  station update --yes
  assert_failure
  # Puis un retour arrière à la main, avant que le moteur ait le résultat.
  printf '%s\t0.2.0\t0.1.0\tretour arrière\t-\tà la main\n' "$(date +%s)" >>"$DIR/updates.log"
  console_asks running
  printf '%s\t%s\t%s\n' "$REQUEST" "$(date +%s)" "$before" >"$DIR/demande-en-cours"
  station requests
  assert_success
  [ "$(result)" = "$REQUEST rolled_back --from 0.1.0 --to 0.2.0" ]
}

@test "coupées, les demandes finissent quand même une mise à jour que la machine avait lancée" {
  installed_then 0.2.0
  # Pas « lines » : run la remplit de la sortie de la commande.
  local before=0
  [[ ! -f $DIR/updates.log ]] || before=$(wc -l <"$DIR/updates.log")
  station update --yes
  assert_success
  echo "BUTTON_CONSOLE_REQUESTS=no" >>"$DIR/.env"
  console_asks running
  printf '%s\t%s\t%s\n' "$REQUEST" "$(date +%s)" "$before" >"$DIR/demande-en-cours"
  by_timer
  assert_success
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  # Une demande qui attend ne part pas.
  console_asks
  : >"$FAKE_STATE/log"
  station requests
  assert_success
  run ! logged "maintenance updates start"
}

@test "un moteur d'avant les demandes : rien ne se passe, rien n'échoue" {
  installed
  touch "$FAKE_STATE/updates-unknown"
  console_asks
  by_timer
  assert_success
  assert_output ""
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
}

@test "config --console-requests no les coupe, et le dit au moteur ; yes les rallume" {
  installed_then 0.2.0
  console_asks
  station config --console-requests no
  assert_success
  assert_output --partial "Demandes de la console : coupées."
  [ "$(env_of BUTTON_CONSOLE_REQUESTS)" = no ]
  host_said | grep -qF '"requests":"no"'
  # Le minuteur tourne encore : il ne fait plus que le dire au moteur.
  logged "systemctl enable --now button-demandes.timer"
  run ! logged "systemctl disable --now button-demandes.timer"
  station requests
  assert_success
  assert_output --partial "Les demandes de la console sont coupées : BUTTON_CONSOLE_REQUESTS=no"
  run ! logged "maintenance updates start"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  by_timer
  assert_output ""
  station config
  assert_output --partial "Demandes de la console : coupées (station config --console-requests yes les rallume)"
  station status
  assert_output --partial "Depuis la console, Réglages → Mises à jour : coupées"
  station config --console-requests yes
  assert_success
  assert_output --partial "Demandes de la console : prises chaque minute."
  host_said | grep -qF '"requests":"yes"'
  station config --console-requests oui
  assert_failure 2
  assert_output --partial "--console-requests « oui » : yes ou no."
}

@test "coupées à la main dans .env : le minuteur le dit au moteur, une fois, sans rien au journal" {
  installed
  station requests
  echo "BUTTON_CONSOLE_REQUESTS=no" >>"$DIR/.env"
  by_timer
  assert_success
  assert_output ""
  host_said | grep -qF '"requests":"no"'
  [ "$(engine_calls host)" = 2 ]
  by_timer
  [ "$(engine_calls host)" = 2 ]
}

@test "status dit les demandes, et un minuteur qui ne tourne pas" {
  installed
  station status
  assert_output --partial "Depuis la console, Réglages → Mises à jour : prises chaque minute."
  touch "$FAKE_STATE/timers-stopped"
  station status
  assert_output --partial "le minuteur des demandes de la console ne tourne pas"
}

@test "une restauration refuse la demande ouverte, avant d'échanger les données" {
  installed
  station backup "$BATS_TEST_TMPDIR/sauvegarde.tar"
  assert_success
  console_asks
  station restore "$BATS_TEST_TMPDIR/sauvegarde.tar" --yes
  assert_success
  [ "$(result)" = "$REQUEST refused" ]
  detail | grep -qF "La station a été remise d'une sauvegarde"
  # Les données d'avant, avec leurs demandes, sont à côté.
  [ ! -e "$DEMANDE" ]
}

@test "uninstall refuse la demande ouverte, et une réinstallation celle restée dans les données" {
  installed_then 0.2.0
  console_asks
  station uninstall --yes
  assert_success
  [ "$(result)" = "$REQUEST refused" ]
  detail | grep -qF "La station a été désinstallée"
  [ ! -e "$UNITS/button-demandes.timer" ]
  [ ! -e "$UNITS/button-demandes.service" ]

  # Restée dans les données, le moteur arrêté à la désinstallation : la
  # réinstallation la refuse, et la station ne change pas de version seule.
  rm "$FAKE_STATE/resultat"
  console_asks
  install_station --domain radio.example --version 0.1.0
  assert_success
  [ "$(result)" = "$REQUEST refused" ]
  detail | grep -qF "La station a été réinstallée, ou réparée"
  station requests
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]

  # La commande d'une version d'avant, remise par un retour arrière : elle ne
  # connaît pas les demandes, et leur minuteur s'en va.
  [ -e "$UNITS/button-demandes.timer" ]
  grep -v '^cmd_requests()' "$STATION" >"$DIR/station"
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; dir=$2; env_file=$2/.env; requests_timer keep' _ "$STATION" "$DIR"
  assert_success
  [ ! -e "$UNITS/button-demandes.timer" ]
}

@test "versions.json s'écrit par un conteneur du moteur : root ne suit pas un lien posé dans RT_DATA" {
  installed_then 0.2.0
  local victime=$BATS_TEST_TMPDIR/victime
  echo "à root" >"$victime"
  ln -s "$victime" "$DIR/data/radiotomate/versions.json.part"
  console_asks
  station requests
  assert_success
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  [ "$(cat "$victime")" = "à root" ]
  logged "--entrypoint python3 radiotomate-init -"
  grep -qF '"version":"0.2.0"' "$DIR/data/radiotomate/versions.json"
  # Un conteneur qui n'écrit pas : la commande avertit, sans échouer.
  touch "$FAKE_STATE/versions-fails"
  install_station --domain radio.example
  assert_success
  assert_output --partial "la version des services ne s'écrit pas dans versions.json"
}

@test "--from prend la version d'une archive, comme station update --from" {
  installed
  console_asks
  station requests --from "$FAKE_STATE/releases/v0.2.0/station.tar.gz"
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  station requests --from "$BATS_TEST_TMPDIR/absente.tar.gz"
  assert_failure 2
  assert_output --partial "--from : $BATS_TEST_TMPDIR/absente.tar.gz n'existe pas."
}

@test "station help dit les demandes de la console" {
  run bash "$STATION" help
  assert_output --partial "requests       prendre les demandes de la console"
  run bash "$STATION" help requests
  assert_output --partial "Usage : station requests [--from ARCHIVE] [--dir DOSSIER]"
  run bash "$STATION" help config
  assert_output --partial "--console-requests yes|no"
}
