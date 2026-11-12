#!/usr/bin/env bats
# Les tests du retour arrière : celui d'une mise à jour qui ne redémarre pas,
# ou que le contrôle refuse, et station rollback, à la main. Sur une station
# installée par station install en 0.1.0, la même machine jouée par de faux
# outils que dans station.bats et mise-a-jour.bats. Depuis la racine du dépôt :
#   ./scripts/verifier.sh deploy

bats_require_minimum_version 1.5.0

setup_file() {
  load helpers
  make_release 0.1.0 "$BATS_FILE_TMPDIR/releases/v0.1.0"
  make_release 0.2.0 "$BATS_FILE_TMPDIR/releases/v0.2.0"
}

setup() {
  load helpers
  bats_load_library bats-support
  bats_load_library bats-assert
  setup_machine
}

# Une station en 0.1.0 qui tourne, et une version plus haute publiée.
installed_then() { # la version qui paraît
  installed
  echo "$1" >"$FAKE_STATE/latest"
}

# La ligne de updates.log, sans son heure.
last_update() {
  grep -v '^#' "$DIR/updates.log" | tail -n 1 | cut -f2-
}

# Les fichiers de la station, hors des données, des sauvegardes et des
# journaux : ceux de sa version, .env compris.
station_files() {
  snapshot | grep -v -e ' \./data/' -e ' \./backups/' -e ' \./backups\.log$' -e ' \./updates\.log$' \
    -e ' \./updates-failed\.log$' -e ' \./HOLD$'
}

# Combien de fois le journal des faux outils a cette ligne.
times_logged() {
  grep -cF -- "$1" "$FAKE_STATE/log" || true
}

# La base de la station, une ligne « schema=N », puis une autre, qui la dit
# elle-même.
database() {
  cat "$DIR/data/radiotomate/radiotomate.db"
}

# --- Le retour arrière d'une mise à jour ---

@test "un contrôle raté : la station revient seule à la version d'avant, et HOLD bloque la suite" {
  installed_then 0.2.0
  station_files >"$BATS_TEST_TMPDIR/avant"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  assert_output --partial "Le contrôle de la station a échoué en 0.2.0 : voir plus haut."
  assert_output --partial "Attention : la mise à jour s'annule : la station revient en 0.1.0."
  assert_output --partial "Retour arrière : la station repart en 0.1.0."
  assert_output --partial "La station est revenue en 0.1.0 : le contrôle passe. La mise à jour vers 0.2.0 est annulée."
  assert_output --partial "  Les journaux de la 0.2.0, pour voir pourquoi : $DIR/updates-failed.log."
  # La commande lancée, qui a unhold : celle de la station, revenue, ne l'a
  # peut-être pas, comme celle d'une 0.2.0.
  assert_output --regexp "  Les mises à jour sont bloquées par $DIR/HOLD\. Les débloquer, une fois la cause trouvée : bash [^ ]*/station unhold, ou rm $DIR/HOLD\."
  # Les fichiers d'avant, .env compris, tels qu'ils étaient.
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  diff "$BATS_TEST_TMPDIR/avant" <(station_files)
  [ -z "$(find "$DIR" -name '*.local-*' -o -name '*.station-*')" ]
  # Le moteur recréé deux fois, ensemble : la mise à jour, puis le retour.
  [ "$(times_logged "docker compose up -d --force-recreate radiotomate-playout radiotomate-interface radiotomate-scheduler (dans $DIR)")" = 2 ]
  [ "$(times_logged "smoke https://radio.example")" = 2 ]
  # updates.log, HOLD et l'alerte le disent.
  local archive
  archive=$(find "$DIR/backups" -name 'button-*.tar')
  [ "$(last_update | cut -f1-4)" = "$(printf '0.1.0\t0.2.0\tannulée\t%s' "$archive")" ]
  [ "$(last_update | cut -f5)" = "pendant le contrôle ; revenue en 0.1.0" ]
  grep -q "^Bloquées par station update, le " "$DIR/HOLD"
  grep -qF "Raison : la mise à jour de 0.1.0 à 0.2.0 a échoué pendant le contrôle, et la station est revenue en 0.1.0. Les journaux de la 0.2.0 : $DIR/updates-failed.log." "$DIR/HOLD"
  grep -qF "logger -t button -p user.warning -- Mise à jour annulée : la mise à jour de 0.1.0 à 0.2.0 a échoué pendant le contrôle : la station est revenue en 0.1.0, et HOLD bloque les suivantes." \
    "$FAKE_STATE/alerts"
  # Les journaux des conteneurs, gardés avant de les recréer.
  [ "$(stat -c %a "$DIR/updates-failed.log")" = 600 ]
  grep -q "les journaux de la station" "$DIR/updates-failed.log"
  logged "logs --no-color --timestamps --since "
  # Puis plus de mise à jour, tant que HOLD est là ; status le dit.
  station update
  assert_failure
  assert_output --partial "Attention : les mises à jour sont bloquées, par $DIR/HOLD :"
  station status
  assert_output --regexp "  La dernière : le [0-9/]+ à [0-9:]+, de 0\.1\.0 à 0\.2\.0, annulée, pendant le contrôle ; revenue en 0\.1\.0\."
  assert_output --partial "  Bloquées, par $DIR/HOLD :"
}

@test "un moteur qui ne redémarre pas revient seul à la version d'avant" {
  installed_then 0.2.0
  station_files >"$BATS_TEST_TMPDIR/avant"
  touch "$FAKE_STATE/up-fails"
  station update
  assert_failure
  assert_output --partial "Le moteur ne repart pas en 0.2.0 : voir le message de docker compose plus haut."
  assert_output --partial "La station est revenue en 0.1.0 : le contrôle passe. La mise à jour vers 0.2.0 est annulée."
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  diff "$BATS_TEST_TMPDIR/avant" <(station_files)
  [ "$(last_update | cut -f3,5)" = "$(printf 'annulée\tpendant le redémarrage ; revenue en 0.1.0')" ]
  [ -f "$DIR/HOLD" ]
}

@test "une migration ratée à mi-chemin : la base d'avant la mise à jour revient, par le script de la version nouvelle" {
  # Comme une 0.2.0 : son script de restauration demande sqlite3, que l'image
  # du moteur n'a pas.
  mkdir -p "$BATS_TEST_TMPDIR/ancienne/scripts"
  cat >"$BATS_TEST_TMPDIR/ancienne/scripts/restore-radiotomate.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
command -v sqlite3 >/dev/null 2>&1 || {
  echo "sqlite3 is required" >&2
  exit 1
}
EOF
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/ancienne make_release 0.1.0 "$FAKE_STATE/releases/v0.1.0"
  # La 0.1.0 lit le schéma v18 ; la 0.2.0 en apporte trois, dont la deuxième
  # échoue.
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 21 >"$FAKE_STATE/schema-0.2.0"
  echo 20 >"$FAKE_STATE/migration-fails"
  installed_then 0.2.0
  database >"$BATS_TEST_TMPDIR/base-avant"
  station update
  assert_failure
  assert_output --partial "Le moteur ne repart pas en 0.2.0"
  assert_output --partial "Retour arrière : la base d'avant la mise à jour, au schéma v18, est remise."
  assert_output --partial "La station est revenue en 0.1.0 : le contrôle passe."
  assert_output --regexp "  Avec la base d'avant la mise à jour : ce qui s'est écrit depuis le [0-9/]+ à [0-9:]+ est perdu ; la base de la 0\.2\.0 reste à côté, dans $DIR/data/radiotomate/backups\."
  # La base est celle d'avant ; celle d'après la v19 reste à côté.
  diff "$BATS_TEST_TMPDIR/base-avant" <(database)
  grep -qx "schema=19" "$DIR"/data/radiotomate/backups/avant-restauration-*.db
  # Remise la station arrêtée, avec le script de la 0.2.0, avant que la 0.1.0
  # ne redémarre : elle ne lit pas le schéma v19.
  grep -Eq -- "-v /[^ ]+/files/scripts/restore-radiotomate.sh:/restore-radiotomate.sh:ro --entrypoint bash radiotomate-init /restore-radiotomate.sh /data/backups/avant-v19-[0-9]{8}T[0-9]{6}Z\.db /data" \
    "$FAKE_STATE/log"
  local stop restored up
  stop=$(grep -n "stop (dans $DIR)" "$FAKE_STATE/log" | tail -n 1 | cut -d: -f1)
  restored=$(grep -n "^restaurée : /data/backups/avant-v19-" "$FAKE_STATE/log" | cut -d: -f1)
  up=$(grep -n "docker compose up -d --force-recreate" "$FAKE_STATE/log" | tail -n 1 | cut -d: -f1)
  ((stop < restored && restored < up))
  [ "$(last_update | cut -f3)" = annulée ]
  last_update | cut -f5 | grep -Eqx "pendant le redémarrage ; revenue en 0\.1\.0, avec la base d'avant la mise à jour : ce qui s'est écrit depuis le [0-9/]+ à [0-9:]+ est perdu"
}

@test "la première migration ratée ne laisse rien : la base reste telle quelle" {
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  echo 19 >"$FAKE_STATE/migration-fails"
  installed_then 0.2.0
  database >"$BATS_TEST_TMPDIR/base-avant"
  station update
  assert_failure
  assert_output --partial "Retour arrière : la base est restée au schéma v18, que la version 0.1.0 lit."
  assert_output --partial "La station est revenue en 0.1.0 : le contrôle passe."
  diff "$BATS_TEST_TMPDIR/base-avant" <(database)
  [ -z "$(find "$DIR/data/radiotomate/backups" -name 'avant-restauration-*')" ]
  run ! logged "restaurée : "
  [ "$(last_update | cut -f5)" = "pendant le redémarrage ; revenue en 0.1.0" ]
}

@test "une mise à jour qui migre, puis rate son contrôle : la base d'avant revient aussi" {
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  installed_then 0.2.0
  database >"$BATS_TEST_TMPDIR/base-avant"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  logged "migration : v18 → v20"
  assert_output --partial "Retour arrière : la base d'avant la mise à jour, au schéma v18, est remise."
  diff "$BATS_TEST_TMPDIR/base-avant" <(database)
  grep -qx "schema=20" "$DIR"/data/radiotomate/backups/avant-restauration-*.db
  last_update | cut -f5 | grep -q "^pendant le contrôle ; revenue en 0\.1\.0, avec la base d'avant la mise à jour : "
}

@test "un retour arrière qui rate lui aussi se dit, bloque, alerte, et station rollback le reprend" {
  installed_then 0.2.0
  echo 2 >"$FAKE_STATE/up-fails"
  station update
  assert_failure
  assert_output --partial "Attention : le retour en 0.1.0 a échoué : Le moteur ne repart pas en 0.1.0 : voir le message de docker compose plus haut."
  assert_output --regexp "  La station est peut-être coupée\. Voir son état : bash [^ ]*/station status ; les journaux de la 0\.2\.0 : $DIR/updates-failed\.log\."
  assert_output --regexp "  Une fois la cause réglée, bash [^ ]*/station rollback refait le retour en 0\.1\.0\."
  refute_output --partial "le contrôle passe"
  [ "$(last_update | cut -f3)" = échouée ]
  [ "$(last_update | cut -f5)" = "pendant le redémarrage ; le retour en 0.1.0 a échoué : Le moteur ne repart pas en 0.1.0 : voir le message de docker compose plus haut." ]
  grep -qF "Raison : la mise à jour de 0.1.0 à 0.2.0 a échoué pendant le redémarrage, et le retour en 0.1.0 aussi :" "$DIR/HOLD"
  grep -qF -- "-- Mise à jour ratée, station à réparer : la mise à jour de 0.1.0 à 0.2.0 a échoué pendant le redémarrage, et le retour en 0.1.0 aussi" \
    "$FAKE_STATE/alerts"
  # Les fichiers sont revenus ; reste à redémarrer.
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  station rollback --yes
  assert_success
  assert_output --partial "La station est revenue en 0.1.0, au lieu de 0.2.0 : le contrôle passe."
  [ "$(last_update | cut -f1-3)" = "$(printf '0.2.0\t0.1.0\tretour arrière')" ]
}

@test "un fichier que la station avait changé revient tel quel ; un fichier nouveau de la version s'en va" {
  mkdir -p "$BATS_TEST_TMPDIR/suivante/scripts"
  echo "# nouveau en 0.2.0" >"$BATS_TEST_TMPDIR/suivante/scripts/nouveau.sh"
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/suivante make_release 0.2.0 "$FAKE_STATE/releases/v0.2.0"
  installed_then 0.2.0
  echo "# un réglage de la station" >>"$DIR/Caddyfile"
  station_files >"$BATS_TEST_TMPDIR/avant"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  assert_output --partial "La station est revenue en 0.1.0 : le contrôle passe."
  grep -qx "# un réglage de la station" "$DIR/Caddyfile"
  [ ! -e "$DIR/scripts/nouveau.sh" ]
  diff "$BATS_TEST_TMPDIR/avant" <(station_files)
  [ -z "$(find "$DIR" -name '*.local-*')" ]
}

@test "Caddy, que la mise à jour a recréé pour son Caddyfile, repart avec celui d'avant" {
  mkdir -p "$BATS_TEST_TMPDIR/suivante"
  { cat "$DEPLOY/Caddyfile"; echo "# changé en 0.2.0"; } >"$BATS_TEST_TMPDIR/suivante/Caddyfile"
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/suivante make_release 0.2.0 "$FAKE_STATE/releases/v0.2.0"
  installed_then 0.2.0
  printf 'id-caddy\n' >"$FAKE_STATE/containers"
  printf 'id-caddy|caddy|%s \n' "$DIR/Caddyfile" >"$FAKE_STATE/inspect-mounts"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  cmp "$DIR/Caddyfile" "$DEPLOY/Caddyfile"
  [ "$(times_logged "up -d --force-recreate --no-deps caddy (dans $DIR)")" = 2 ]
}

@test "les services d'un autre profil repartent au retour arrière" {
  installed_then 0.2.0
  printf 'caddy\nradiotomate-playout\nshare\n' >"$FAKE_STATE/services-running"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  [ "$(times_logged "docker compose --profile cloud --profile share --profile vps up -d share (dans $DIR)")" = 2 ]
}

@test "un échec pendant la pose des fichiers les remet, sans redémarrer la station" {
  installed_then 0.2.0
  # Un dossier de données qui ne se crée pas : make_data_dirs échoue, et set -e
  # arrête la mise à jour au milieu de ses fichiers.
  echo "MEILI_DATA=./data/fichier/meili" >>"$DIR/.env"
  : >"$DIR/data/fichier"
  station_files >"$BATS_TEST_TMPDIR/avant"
  station update
  assert_failure
  assert_output --partial "Attention : la mise à jour s'annule : la station revient en 0.1.0."
  assert_output --partial "La station tourne toujours en 0.1.0, qui n'a pas redémarré : ses fichiers sont revenus. La mise à jour vers 0.2.0 est annulée."
  run ! logged "docker compose up"
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  diff "$BATS_TEST_TMPDIR/avant" <(station_files)
  [ "$(last_update | cut -f3,5)" = "$(printf 'annulée\tpendant les fichiers ; revenue en 0.1.0')" ]
  [ -f "$DIR/HOLD" ]
  [ ! -e "$DIR/updates-failed.log" ]
}

@test "revenue à une version d'avant ICECAST_MOUNT, la station se contrôle sur button.mp3, qu'elle sert" {
  # Comme la 0.2.0 : son compose.yml ne passe pas ICECAST_MOUNT, et le flux
  # public est en dur, button.mp3.
  mkdir -p "$BATS_TEST_TMPDIR/ancienne"
  grep -v ICECAST_MOUNT "$DEPLOY/compose.yml" >"$BATS_TEST_TMPDIR/ancienne/compose.yml"
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/ancienne make_release 0.1.0 "$FAKE_STATE/releases/v0.1.0"
  installed_then 0.2.0
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  assert_output --partial "La station est revenue en 0.1.0 : le contrôle passe."
  # Le contrôle de la 0.2.0, sur son mount ; puis celui de la 0.1.0, sur le sien.
  [ "$(grep '^smoke ' "$FAKE_STATE/log" | head -n 1 | cut -d' ' -f3)" = https://radio.example/radio.mp3 ]
  [ "$(grep '^smoke ' "$FAKE_STATE/log" | tail -n 1 | cut -d' ' -f3)" = https://radio.example/button.mp3 ]
}

@test "une copie de la base abîmée : rien ne se défait, la station reste à la nouvelle version, et le dit" {
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  installed_then 0.2.0
  touch "$FAKE_STATE/smoke-fails" "$FAKE_STATE/copy-corrupt"
  station update
  assert_failure
  assert_output --regexp "Attention : le retour en 0\.1\.0 a échoué : La copie de la base d'avant la mise à jour, avant-v19-[0-9]{8}T[0-9]{6}Z\.db, est abîmée : database disk image is malformed\. La base ne peut pas revenir\."
  assert_output --partial "  La station reste en 0.2.0, qui tourne, mais que le contrôle refuse."
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  run ! logged "restaurée : "
  run ! logged " stop (dans $DIR)"
  [ "$(last_update | cut -f3)" = échouée ]
  [ -f "$DIR/HOLD" ]
}

@test "la place manque pour remettre la base d'avant : rien ne se défait" {
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  installed_then 0.2.0
  touch "$FAKE_STATE/smoke-fails"
  echo 1000 >"$FAKE_STATE/free-kb-data"
  station update
  assert_failure
  assert_output --partial "Il manque de la place à côté de la base pour y remettre celle d'avant la mise à jour"
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  run ! logged "restaurée : "
}

@test "une base qui ne se remet pas laisse la station arrêtée, et le dit ; rollback la reprend, par un script qui se passe de sqlite3" {
  # La 0.1.0, comme la 0.2.0 : son script de restauration demande sqlite3.
  mkdir -p "$BATS_TEST_TMPDIR/ancienne/scripts"
  cat >"$BATS_TEST_TMPDIR/ancienne/scripts/restore-radiotomate.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
command -v sqlite3 >/dev/null 2>&1 || {
  echo "sqlite3 is required" >&2
  exit 1
}
EOF
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/ancienne make_release 0.1.0 "$FAKE_STATE/releases/v0.1.0"
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  installed_then 0.2.0
  database >"$BATS_TEST_TMPDIR/base-avant"
  touch "$FAKE_STATE/smoke-fails" "$FAKE_STATE/restore-fails"
  station update
  assert_failure
  assert_output --partial "Attention : le retour en 0.1.0 a échoué : La base d'avant la mise à jour, avant-v19-"
  assert_output --partial "  La station est arrêtée. Voir son état :"
  # Les fichiers sont revenus : le dossier porte le script de la 0.1.0, que
  # l'image du moteur refuse. La reprise prend celui de la version quittée.
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  station rollback --yes
  assert_success
  assert_output --partial "La station est revenue en 0.1.0, au lieu de 0.2.0 : le contrôle passe."
  diff "$BATS_TEST_TMPDIR/base-avant" <(database)
}

@test "un service venu avec la mise à jour s'en va au retour arrière ; les autres restent" {
  installed_then 0.2.0
  printf 'id-nouveau\nid-caddy\n' >"$FAKE_STATE/containers"
  printf 'id-nouveau|nouveau-service\nid-caddy|caddy\n' >"$FAKE_STATE/inspect-services"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  assert_output --partial "Retour arrière : retirés, venus avec la mise à jour : nouveau-service."
  logged "docker rm -f id-nouveau"
  run ! logged "docker rm -f id-caddy"
}

@test "une connexion coupée en plein contrôle : la station revient quand même" {
  installed_then 0.2.0
  touch "$FAKE_STATE/smoke-hangs"
  bash "$STATION" update >"$BATS_TEST_TMPDIR/sortie" 2>&1 &
  local pid=$! status=0 tries=0
  until logged "smoke https://"; do
    ((tries++ < 300))
    sleep 0.1
  done
  kill -HUP "$pid"
  rm "$FAKE_STATE/smoke-hangs"
  wait "$pid" || status=$?
  [ "$status" -eq 129 ]
  grep -qF "Attention : la mise à jour s'annule : la station revient en 0.1.0." "$BATS_TEST_TMPDIR/sortie"
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ "$(last_update | cut -f3,5)" = "$(printf 'annulée\tpendant le contrôle ; revenue en 0.1.0')" ]
  [ -f "$DIR/HOLD" ]
}

@test "une mise à jour contrôlée reste faite, même quand updates.log ne s'écrit pas" {
  installed_then 0.2.0
  # Un dossier à sa place : rien ne s'y écrit, comme sur un disque plein.
  mkdir "$DIR/updates.log"
  station update
  assert_success
  assert_output --partial "Attention : updates.log ne s'écrit pas : la mise à jour, faite, n'y est pas notée."
  assert_output --partial "La station est à jour : 0.2.0, au lieu de 0.1.0. Le contrôle passe."
  refute_output --partial "s'annule"
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ ! -e "$DIR/HOLD" ]
}

# --- station rollback ---

@test "rollback défait la dernière mise à jour, et bloque les suivantes" {
  installed_then 0.2.0
  station_files >"$BATS_TEST_TMPDIR/avant"
  station update
  assert_success
  : >"$FAKE_STATE/log"
  station rollback --yes
  assert_success
  assert_output --partial "Retour arrière : de 0.2.0 à 0.1.0."
  assert_output --partial "La station est revenue en 0.1.0, au lieu de 0.2.0 : le contrôle passe."
  assert_output --partial "  Les mises à jour sont bloquées par $DIR/HOLD."
  # Les fichiers de la 0.1.0, depuis son archive, et ses images.
  logged "releases/download/v0.1.0/station.tar.gz"
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  diff "$BATS_TEST_TMPDIR/avant" <(station_files)
  logged "docker compose up -d --force-recreate radiotomate-playout radiotomate-interface radiotomate-scheduler (dans $DIR)"
  logged "smoke https://radio.example https://radio.example/radio.mp3"
  # Pas de schéma migré : la base reste.
  run ! logged "restaurée : "
  [ "$(last_update | cut -f1-5)" = "$(printf '0.2.0\t0.1.0\tretour arrière\t-\tà la main')" ]
  grep -q "^Bloquées par station rollback, le " "$DIR/HOLD"
  grep -qF "Raison : retour de 0.2.0 à 0.1.0, à la main. La version 0.2.0 ne se reprend qu'une fois HOLD retiré." "$DIR/HOLD"
  grep -qF -- "-- Mise à jour défaite : station rollback a ramené la station de 0.2.0 à 0.1.0, à la main" "$FAKE_STATE/alerts"
  # Une fois défaite, plus rien à défaire ; et HOLD bloque la mise à jour.
  station rollback --yes
  assert_success
  assert_output "Rien à défaire : la dernière mise à jour, de 0.1.0 à 0.2.0, est déjà défaite."
  station update
  assert_failure
  assert_output --partial "les mises à jour sont bloquées"
}

@test "rollback remet la base d'avant la mise à jour quand le schéma a migré, et le demande d'abord" {
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  installed_then 0.2.0
  database >"$BATS_TEST_TMPDIR/base-avant"
  station update
  assert_success
  # Ce qui s'écrit ensuite, en 0.2.0.
  echo "écrit=en 0.2.0" >>"$DIR/data/radiotomate/radiotomate.db"
  station_at_keyboard rollback <<<"o"
  assert_success
  assert_output --regexp "Revenir de 0\.2\.0 à 0\.1\.0 \? La base revient à celle d'avant la mise à jour, du [0-9/]+ à [0-9:]+ : ce qui s'est écrit depuis, il y a 1 min, sera perdu, et la base d'aujourd'hui gardée à côté\. L'antenne se coupe le temps de redémarrer\. \(o/n\)"
  assert_output --partial "Retour arrière : la station s'arrête, le temps de remettre la base d'avant la mise à jour."
  assert_output --regexp "  Avec la base d'avant la mise à jour : ce qui s'est écrit depuis le [0-9/]+ à [0-9:]+ est perdu ; la base de la 0\.2\.0 reste à côté, dans $DIR/data/radiotomate/backups\."
  diff "$BATS_TEST_TMPDIR/base-avant" <(database)
  grep -qx "écrit=en 0.2.0" "$DIR"/data/radiotomate/backups/avant-restauration-*.db
  last_update | cut -f5 | grep -q "^à la main ; avec la base d'avant la mise à jour : ce qui s'est écrit depuis le "
}

@test "au clavier, rollback se confirme ; non, ou pas de terminal, ne change rien" {
  installed_then 0.2.0
  station update
  assert_success
  station_at_keyboard rollback <<<"n"
  assert_failure
  assert_output --partial "Revenir de 0.2.0 à 0.1.0 ? L'antenne se coupe le temps de redémarrer. (o/n) [n] :"
  assert_output --partial "Rien n'est changé."
  station rollback
  assert_failure
  assert_output --partial "Sans terminal, station rollback attend --yes pour se faire."
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ ! -e "$DIR/HOLD" ]
  [ "$(last_update | cut -f3)" = faite ]
}

@test "rollback sans mise à jour à défaire ne change rien" {
  installed_then 0.2.0
  station rollback --yes
  assert_success
  assert_output "Rien à défaire : $DIR/updates.log ne note aucune mise à jour en place."
  # Une mise à jour qui n'a rien touché.
  touch "$FAKE_STATE/pull-fails"
  station update
  assert_failure
  station rollback --yes
  assert_success
  assert_output "Rien à défaire : $DIR/updates.log ne note aucune mise à jour en place."
  # Une mise à jour revenue seule.
  rm "$FAKE_STATE/pull-fails"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  station rollback --yes
  assert_success
  assert_output "Rien à défaire : $DIR/updates.log ne note aucune mise à jour en place."
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
}

@test "rollback --from prend les fichiers de la version d'avant dans une archive, et seulement les siens" {
  installed_then 0.2.0
  station update
  assert_success
  station rollback --yes --from "$FAKE_STATE/releases/v0.2.0/station.tar.gz"
  assert_failure
  assert_output --partial "est la version 0.2.0, et la version d'avant la dernière mise à jour la 0.1.0. Rien n'est changé."
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  : >"$FAKE_STATE/log"
  station rollback --yes --from "$FAKE_STATE/releases/v0.1.0/station.tar.gz"
  assert_success
  run ! logged "releases/download/v0.1.0/"
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
}

@test "rollback tire d'abord les images de la version d'avant qui manquent" {
  installed_then 0.2.0
  station update
  assert_success
  : >"$FAKE_STATE/log"
  touch "$FAKE_STATE/image-missing"
  station rollback --yes
  assert_success
  assert_output --partial "Retour arrière : les images de la version 0.1.0 qui manquent, tirées pendant que l'antenne joue :"
  local pull up
  pull=$(grep -n "images : BUTTON_VERSION=0.1.0" "$FAKE_STATE/log" | cut -d: -f1)
  up=$(grep -n "docker compose up -d --force-recreate" "$FAKE_STATE/log" | cut -d: -f1)
  ((pull < up))
  # Une image qui ne se tire pas : rien ne change.
  rm "$DIR/HOLD"
  station update
  assert_success
  touch "$FAKE_STATE/pull-fails"
  station rollback --yes
  assert_failure
  assert_output --partial "Les images de la version 0.1.0 ne se tirent pas : voir le message de docker compose plus haut. Rien n'est changé."
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ ! -e "$DIR/HOLD" ]
}

@test "un retour arrière à la main qui rate se note, et se reprend" {
  installed_then 0.2.0
  station update
  assert_success
  touch "$FAKE_STATE/up-fails"
  station rollback --yes
  assert_failure
  assert_output --partial "Le moteur ne repart pas en 0.1.0 : voir le message de docker compose plus haut."
  assert_output --partial "Le retour arrière n'est pas fini : updates.log le note, et HOLD bloque les mises à jour."
  [ "$(last_update | cut -f1-3,5)" = "$(printf '0.2.0\t0.1.0\tretour arrière échoué\tpendant le redémarrage')" ]
  grep -qF -- "-- Retour arrière raté : station rollback, de 0.2.0 à 0.1.0, a échoué pendant le redémarrage" "$FAKE_STATE/alerts"
  [ -f "$DIR/HOLD" ]
  station rollback --yes
  assert_success
  assert_output --partial "La station est revenue en 0.1.0, au lieu de 0.2.0 : le contrôle passe."
  [ "$(last_update | cut -f1-3)" = "$(printf '0.2.0\t0.1.0\tretour arrière')" ]
}

@test "rollback passe les mises à jour qui n'ont rien laissé, et défait la dernière en place" {
  installed_then 0.2.0
  station update
  assert_success
  make_release 0.3.0 "$FAKE_STATE/releases/v0.3.0"
  echo 0.3.0 >"$FAKE_STATE/latest"
  # Arrêtée par un direct, échouée sur ses images, puis revenue seule.
  echo "occupée : QG, un direct, commence à 20:00, dans 29 min" >"$FAKE_STATE/window-later"
  station update
  assert_failure
  touch "$FAKE_STATE/pull-fails"
  station update
  assert_failure
  rm "$FAKE_STATE/pull-fails"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  [ "$(grep -v '^#' "$DIR/updates.log" | cut -f4 | tr '\n' ' ')" = "faite arrêtée échouée annulée " ]
  station rollback --yes
  assert_success
  assert_output --partial "La station est revenue en 0.1.0, au lieu de 0.2.0 : le contrôle passe."
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
}

@test "rollback refuse une base que la version d'avant ne lirait pas, quand la copie n'est plus là" {
  echo 18 >"$FAKE_STATE/schema-0.1.0"
  echo 20 >"$FAKE_STATE/schema-0.2.0"
  installed_then 0.2.0
  station update
  assert_success
  rm "$DIR"/data/radiotomate/backups/avant-v*.db
  station rollback --yes
  assert_failure
  assert_output --partial "La base est au schéma v20, et la version 0.1.0 ne lit que jusqu'au v18 : la copie de la base d'avant la mise à jour n'est plus dans $DIR/data/radiotomate/backups. Rien n'est changé."
  assert_output --partial "Revenir à la main, en redescendant le schéma avec l'image de la 0.2.0"
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ ! -e "$DIR/HOLD" ]
}

@test "rollback refuse un updates.log qu'il ne comprend pas, ou une station à une autre version" {
  installed_then 0.2.0
  station update
  assert_success
  printf '%s\t0.2.0\t0.3.0\tbizarre\t-\tun essai\n' "$(date +%s)" >>"$DIR/updates.log"
  station rollback --yes
  assert_failure
  assert_output --partial "a une ligne au résultat inattendu, « bizarre ». Rien n'est changé."
  sed -i '$d' "$DIR/updates.log"
  sed -i 's/^BUTTON_VERSION=.*/BUTTON_VERSION=0.3.0/' "$DIR/.env"
  station rollback --yes
  assert_failure
  assert_output --partial "La station est en 0.3.0, et la dernière mise à jour allait de 0.1.0 à 0.2.0 : rollback ne sait pas d'où revenir. Rien n'est changé."
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
}

@test "un avertissement de Compose n'est pas une image qui manque" {
  installed_then 0.2.0
  station update
  assert_success
  echo 'WARN[0000] The "X" variable is not set. Defaulting to a blank string.' >"$FAKE_STATE/compose-warning"
  : >"$FAKE_STATE/log"
  station rollback --yes
  assert_success
  refute_output --partial "qui manquent"
  run ! logged "images : BUTTON_VERSION=0.1.0"
}

@test "l'aide de rollback, et ses options" {
  installed
  station help rollback
  assert_success
  assert_output --partial "Usage : station rollback [--from ARCHIVE] [--yes] [--dir DOSSIER]"
  station rollback --help
  assert_success
  assert_output --partial "Usage : station rollback"
  station help
  assert_output --partial "rollback       défaire la dernière mise à jour"
  station rollback --version 0.1.0
  assert_failure 2
  assert_output --partial "Option inconnue : --version."
  assert_output --partial "Voir : station help rollback."
}
