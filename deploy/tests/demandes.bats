#!/usr/bin/env bats
# Les tests de station requests, les demandes de la console (MAJ-07) : le
# bouton « Mettre à jour maintenant » écrit une demande dans le moteur, et la
# machine la prend chaque minute, par docker compose exec, puis lance station
# update. Sur une station installée par station install en 0.1.0, la même
# machine jouée par de faux outils que dans station.bats. Le faux docker joue
# le moteur des demandes : engine_updates. Depuis la racine du dépôt :
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
}

# Une station en 0.1.0 qui tourne, et une version plus haute publiée.
installed_then() { # la version qui paraît
  installed
  echo "$1" >"$FAKE_STATE/latest"
}

# « Mettre à jour maintenant » : la demande, comme le moteur l'écrit.
console_asks() {
  mkdir -p "$DIR/data/radiotomate/updates"
  echo "{\"id\": \"$REQUEST\", \"state\": \"pending\"}" >"$DIR/data/radiotomate/updates/request.json"
  echo "$REQUEST pending" >"$FAKE_STATE/demande"
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

@test "install pose le minuteur des demandes : chaque minute, station requests" {
  installed
  grep -qxF "ExecStart=\"$DIR/station\" requests --dir \"$DIR\"" "$UNITS/button-demandes.service"
  grep -qxF "OnCalendar=minutely" "$UNITS/button-demandes.timer"
  grep -qxF "Environment=HOME=/root" "$UNITS/button-demandes.service"
  grep -qxF "LogLevelMax=notice" "$UNITS/button-demandes.service"
  install_station --domain radio.example
  assert_success
  logged "systemctl enable --now button-demandes.timer"
  # Relancée, l'installation ne les réécrit pas, et ne recharge pas systemd
  # pour eux.
  refute_output --partial "Demandes de la console : prises chaque minute"
}

@test "sans demande, un passage ne dit au moteur que ce qui change, ou au bout d'une heure" {
  installed
  # Par le minuteur, sous systemd : rien au journal.
  run env INVOCATION_ID=essai bash "$STATION" requests
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
  # La mise à jour de la station, comme une personne la lance.
  [ ! -e "$DIR/demande-en-cours" ]
  [ ! -e "$FAKE_STATE/demande" ]
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
  [ "$(cat "$FAKE_STATE/demande")" = "$REQUEST pending" ]
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

@test "arrêtée par l'antenne une fois sa sauvegarde faite, la demande attend de nouveau" {
  installed_then 0.2.0
  console_asks
  # Libre pour station requests, puis pour station update, puis prise, une
  # fois la sauvegarde faite.
  echo "occupée : QG, un direct, commence à 20:00, dans 25 min" >"$FAKE_STATE/window-later"
  echo 2 >"$FAKE_STATE/window-later-reads"
  station requests
  assert_success
  [ "$(last_update | cut -f3)" = "arrêtée" ]
  grep -qF "Arrêtée par l'antenne, sa sauvegarde faite : QG, un direct, commence à 20:00, dans 25 min." "$FAKE_STATE/attente"
  [ "$(cat "$FAKE_STATE/demande")" = "$REQUEST pending" ]
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

@test "une majeure ne part pas d'une demande : rien ne change, et la commande la cite" {
  installed_then 1.0.0
  console_asks
  station requests
  assert_success
  [ "$(result)" = "$REQUEST failed" ]
  detail | grep -qF "Rien n'a changé."
  detail | grep -qF "update --major"
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
  [ "$(cat "$FAKE_STATE/demande")" = "$REQUEST running" ]
  # Le passage suivant le lui dit, d'après updates.log.
  station requests
  assert_success
  [ "$(result)" = "$REQUEST done --from 0.1.0 --to 0.2.0" ]
  [ ! -e "$DIR/demande-en-cours" ]

  # Une machine qui redémarre en pleine mise à jour : rien dans updates.log.
  console_asks
  echo "$REQUEST running" >"$FAKE_STATE/demande"
  printf '%s\t%s\t%s\n' "$REQUEST" "$(date +%s)" "$(wc -l <"$DIR/updates.log")" >"$DIR/demande-en-cours"
  station requests
  assert_success
  [ "$(result)" = "$REQUEST interrupted" ]
  detail | grep -qF "La mise à jour s'est arrêtée sans rien noter"
  [ ! -e "$DIR/demande-en-cours" ]

  # Sans marque, la machine n'en a pas trace : des données remises, par exemple.
  console_asks
  echo "$REQUEST running" >"$FAKE_STATE/demande"
  station requests
  assert_success
  [ "$(result)" = "$REQUEST interrupted" ]
  detail | grep -qF "La machine n'a pas trace de cette mise à jour"
}

@test "un moteur d'avant les demandes : rien ne se passe, rien n'échoue" {
  installed
  touch "$FAKE_STATE/updates-unknown"
  console_asks
  run env INVOCATION_ID=essai bash "$STATION" requests
  assert_success
  assert_output ""
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
}

@test "config --console-requests no les coupe, et le dit au moteur ; yes les rallume" {
  installed_then 0.2.0
  touch "$FAKE_STATE/engine-running"
  console_asks
  station config --console-requests no
  assert_success
  assert_output --partial "Demandes de la console : coupées."
  [ "$(env_of BUTTON_CONSOLE_REQUESTS)" = no ]
  logged "systemctl disable --now button-demandes.timer"
  host_said | grep -qF '"requests":"no"'
  # Le minuteur reste, arrêté.
  [ -e "$UNITS/button-demandes.timer" ]
  station requests
  assert_success
  assert_output --partial "Les demandes de la console sont coupées : BUTTON_CONSOLE_REQUESTS=no"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  run env INVOCATION_ID=essai bash "$STATION" requests
  assert_output ""
  station config
  assert_output --partial "Demandes de la console : coupées (station config --console-requests yes les rallume)"
  station status
  assert_output --partial "Depuis la console, Réglages → Mises à jour : coupées"
  station config --console-requests yes
  assert_success
  assert_output --partial "Demandes de la console : prises chaque minute."
  logged "systemctl enable --now button-demandes.timer"
  host_said | grep -qF '"requests":"yes"'
  station config --console-requests oui
  assert_failure 2
  assert_output --partial "--console-requests « oui » : yes ou no."
}

@test "coupées à la main dans .env : le minuteur le dit au moteur, une fois, sans rien au journal" {
  installed
  station requests
  echo "BUTTON_CONSOLE_REQUESTS=no" >>"$DIR/.env"
  run env INVOCATION_ID=essai bash "$STATION" requests
  assert_success
  assert_output ""
  host_said | grep -qF '"requests":"no"'
  [ "$(engine_calls host)" = 2 ]
  run env INVOCATION_ID=essai bash "$STATION" requests
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

@test "une restauration refuse la demande venue avec les données" {
  installed
  station backup "$BATS_TEST_TMPDIR/sauvegarde.tar"
  assert_success
  console_asks
  station restore "$BATS_TEST_TMPDIR/sauvegarde.tar" --yes
  assert_success
  [ "$(result)" = "$REQUEST refused" ]
  detail | grep -qF "La station a été remise d'une sauvegarde"
}

@test "uninstall retire le minuteur ; une commande d'avant les demandes aussi" {
  installed
  station uninstall --yes
  assert_success
  [ ! -e "$UNITS/button-demandes.timer" ]
  [ ! -e "$UNITS/button-demandes.service" ]

  # La commande d'une version d'avant, remise par un retour arrière : elle ne
  # connaît pas les demandes, et leur minuteur s'en va.
  installed
  [ -e "$UNITS/button-demandes.timer" ]
  grep -v '^cmd_requests()' "$STATION" >"$DIR/station"
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; dir=$2; env_file=$2/.env; requests_timer keep' _ "$STATION" "$DIR"
  assert_success
  [ ! -e "$UNITS/button-demandes.timer" ]
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
