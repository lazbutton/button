#!/usr/bin/env bats
# Les tests de station update, sur une station installée par station install en
# 0.1.0, quand d'autres versions paraissent. La même machine jouée par de faux
# outils que dans station.bats. Depuis la racine du dépôt :
#   ./scripts/verifier.sh deploy

bats_require_minimum_version 1.5.0

setup_file() {
  load helpers
  make_release 0.1.0 "$BATS_FILE_TMPDIR/releases/v0.1.0"
  make_release 0.2.0 "$BATS_FILE_TMPDIR/releases/v0.2.0"
  # Une majeure, dont les notes demandent une action.
  cat >"$BATS_FILE_TMPDIR/CHANGELOG.md" <<'EOF'
# Journal des changements

## 1.0.0

**Mise en service.** Une station pose le nom de son mount public dans `.env` : `ICECAST_MOUNT=button.mp3` garde l'adresse de son flux. Voir [docs/deploiement.md](docs/deploiement.md#les-mounts).

- Les mounts se règlent dans `.env`.

## 0.2.0

**Mise en service.** Rien d'autre que la mise à jour habituelle.
EOF
  RELEASE_CHANGELOG=$BATS_FILE_TMPDIR/CHANGELOG.md make_release 1.0.0 "$BATS_FILE_TMPDIR/releases/v1.0.0"
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

@test "update met la station à la plus haute version publiée" {
  installed_then 0.2.0
  cp "$DIR/.env" "$BATS_TEST_TMPDIR/env-avant"
  station update
  assert_success
  assert_output --partial "BUTTON : mise à jour de la station de $DIR, de 0.1.0 à 0.2.0."
  assert_output --partial "Fenêtre : libre, ni direct ni diffusion de l'Agenda d'ici 30 min."
  assert_output --partial "Mise à jour : les images de la version 0.2.0, pendant que l'antenne joue."
  assert_output --partial "La station est à jour : 0.2.0, au lieu de 0.1.0. Le contrôle passe."
  assert_output --regexp "Redémarrée et contrôlée en [0-9]+ s, coupure de l'antenne comprise."
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  # .env ne change que de version.
  diff <(grep -v '^BUTTON_VERSION=' "$BATS_TEST_TMPDIR/env-avant") <(grep -v '^BUTTON_VERSION=' "$DIR/.env")
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  # La sauvegarde d'abord, dans backups/.
  local archive
  archive=$(find "$DIR/backups" -name 'button-*.tar')
  [ -n "$archive" ]
  assert_output --partial "La sauvegarde d'avant : $archive."
  [ "$(last_update | cut -f1-4)" = "$(printf '0.1.0\t0.2.0\tfaite\t%s' "$archive")" ]
  last_update | cut -f5 | grep -Eqx 'redémarrée et contrôlée en [0-9]+ s'
  # Les images de la version, tirées avant de rien changer, avec ses fichiers ;
  # puis les trois services du moteur recréés ensemble, puis le reste, puis le
  # contrôle.
  logged "docker compose exec -T radiotomate-interface radiotomate maintenance window (dans $DIR)"
  logged "images : BUTTON_VERSION=0.2.0"
  grep -Eq "^docker compose -f /[^ ]+/files/compose.yml --project-directory $DIR pull " "$FAKE_STATE/log"
  logged "docker compose up -d --force-recreate radiotomate-playout radiotomate-interface radiotomate-scheduler (dans $DIR)"
  logged "docker compose up -d (dans $DIR)"
  logged "smoke https://radio.example https://radio.example/radio.mp3 SMOKE_WAIT=300 dans $DIR"
  local pull up
  pull=$(grep -n "images : BUTTON_VERSION=0.2.0" "$FAKE_STATE/log" | cut -d: -f1)
  up=$(grep -n "docker compose up -d --force-recreate" "$FAKE_STATE/log" | cut -d: -f1)
  ((pull < up))
  # Aucun fichier de la version d'avant ne reste à côté : seul VERSION change,
  # comme la version le veut.
  [ -z "$(find "$DIR" -name '*.local-*')" ]
  [ -z "$(find "$DIR" -name '*.station-*')" ]
}

@test "une station à jour : rien à faire, rien ne se télécharge" {
  installed_then 0.1.0
  station update
  assert_success
  assert_output "La station est déjà en 0.1.0. Rien à faire."
  run ! logged "releases/download"
  [ ! -e "$DIR/backups" ]
}

@test "update monte à une version donnée, jamais plus bas" {
  installed_then 1.0.0
  station update --version 0.2.0
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  station update --version 0.1.0
  assert_failure
  assert_output --partial "La version 0.1.0 est plus ancienne que celle de la station, 0.2.0 : station update ne fait que monter."
  assert_output --partial "Revenir en arrière : voir docs/deploiement.md, « Revenir en arrière »."
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  station update --version 0.2
  assert_failure 2
  assert_output --partial "« 0.2 » : une version s'écrit X.Y.Z"
}

@test "une majeure s'arrête et cite l'action de ses notes ; --major la prend" {
  installed_then 1.0.0
  station update
  assert_failure
  assert_output --partial "La version 1.0.0 est une majeure : elle demande une action à la station avant de la prendre."
  assert_output --partial "La 1.0.0 demande :"
  assert_output --partial "  Une station pose le nom de son mount public dans \`.env\` :"
  assert_output --partial "(https://github.com/lazbutton/button/blob/v1.0.0/docs/deploiement.md#les-mounts)."
  refute_output --partial "**"
  # Le script lancé, qui n'est pas la commande de la station : celle d'une
  # 0.2.0 n'a pas update.
  assert_output --regexp "Rien n'est changé\. Une fois l'action faite : bash [^ ]*/station update --major\."
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ ! -e "$DIR/backups" ]
  run bash "$DIR/station" update
  assert_failure
  assert_output --partial "Rien n'est changé. Une fois l'action faite : station update --major."
  station update --major
  assert_success
  assert_output --partial "Version majeure : l'action que demandent ses notes est faite (--major)."
  [ "$(env_of BUTTON_VERSION)" = 1.0.0 ]
}

@test "update attend qu'aucun direct ne soit proche, sauf --force" {
  installed_then 0.2.0
  echo "occupée : QG, un direct, commence à 20:00, dans 12 min" >"$FAKE_STATE/window"
  station update
  assert_failure
  assert_output --partial "Pas de mise à jour maintenant : QG, un direct, commence à 20:00, dans 12 min. L'antenne se couperait pendant. Rien n'est changé."
  assert_output --regexp "Relancer plus tard, ou mettre à jour quand même : bash [^ ]*/station update --force\."
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ ! -e "$DIR/backups" ]
  [ ! -e "$DIR/updates.log" ]
  echo "occupée : QG, un direct, en cours" >"$FAKE_STATE/window"
  station update --force
  assert_success
  assert_output --partial "Fenêtre : pas vérifiée (--force). L'antenne se coupera, même pendant un direct."
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
}

@test "un direct qui se rapproche pendant les préparatifs arrête la mise à jour avant la coupure" {
  installed_then 0.2.0
  echo "occupée : QG, un direct, commence à 20:00, dans 29 min" >"$FAKE_STATE/window-later"
  station update
  assert_failure
  assert_output --partial "Pas de mise à jour maintenant : QG, un direct, commence à 20:00, dans 29 min. L'antenne se couperait pendant. La station reste en 0.1.0, avec la sauvegarde d'avant."
  run ! logged "docker compose up"
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ "$(last_update | cut -f1-3)" = "$(printf '0.1.0\t0.2.0\tarrêtée')" ]
  [ "$(last_update | cut -f5)" = "QG, un direct, commence à 20:00, dans 29 min" ]
}

@test "un moteur qui ne dit pas la fenêtre ne bloque pas la mise à jour" {
  installed_then 0.2.0
  touch "$FAKE_STATE/window-unknown"
  station update
  assert_success
  assert_output --partial "Attention : la fenêtre n'est pas vérifiée : le moteur ne la dit pas, il ne répond pas, ou sa version n'a pas radiotomate maintenance window."
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
}

@test "HOLD bloque les mises à jour" {
  installed_then 0.2.0
  station hold la grille de Noël
  station update --force --yes
  assert_failure
  assert_output --partial "Attention : les mises à jour sont bloquées, par $DIR/HOLD :"
  assert_output --partial "  Raison : la grille de Noël"
  assert_output --partial "Rien n'est changé."
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  run ! logged "releases/download"
}

@test "une restauration pas finie bloque les mises à jour" {
  installed_then 0.2.0
  echo "# station restore" >"$DIR/restauration-en-cours"
  station update
  assert_failure
  assert_output --partial "Une restauration ne s'est pas finie : $DIR/restauration-en-cours est encore là. Rien n'est changé."
}

@test "une station au script de sauvegarde sans repli Python se sauvegarde avec celui de la version visée" {
  # Comme une 0.2.0 : son script demande sqlite3, que l'image du moteur n'a pas.
  mkdir -p "$BATS_TEST_TMPDIR/ancienne/scripts"
  cat >"$BATS_TEST_TMPDIR/ancienne/scripts/backup-radiotomate.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
command -v sqlite3 >/dev/null 2>&1 || {
  echo "sqlite3 is required" >&2
  exit 1
}
EOF
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/ancienne make_release 0.1.0 "$FAKE_STATE/releases/v0.1.0"
  installed_then 0.2.0
  station backup
  assert_failure
  assert_output --partial "sqlite3 is required"
  station update
  assert_success
  grep -Eq -- "-v /[^ ]+/files/scripts/backup-radiotomate.sh:/backup-radiotomate.sh:ro" "$FAKE_STATE/log"
  [ "$(find "$DIR/backups" -name 'button-*.tar' | wc -l)" = 1 ]
  # Puis la station a le sien, celui de la 0.2.0.
  cmp "$DIR/scripts/backup-radiotomate.sh" "$DEPLOY/scripts/backup-radiotomate.sh"
}

@test "update garde les cinq dernières sauvegardes de backups/" {
  installed_then 0.2.0
  mkdir -p "$DIR/backups"
  local day
  for day in 1 2 3 4 5 6; do
    touch "$DIR/backups/button-2026010${day}T030000Z.tar"
  done
  touch "$DIR/backups/autre-chose.tar"
  station update
  assert_success
  assert_output --partial "Sauvegardes : les 5 dernières restent dans $DIR/backups ; 2 plus ancienne(s) effacée(s)."
  [ ! -e "$DIR/backups/button-20260101T030000Z.tar" ]
  [ ! -e "$DIR/backups/button-20260102T030000Z.tar" ]
  [ -e "$DIR/backups/button-20260103T030000Z.tar" ]
  [ -e "$DIR/backups/autre-chose.tar" ]
  [ "$(find "$DIR/backups" -name 'button-*.tar' | wc -l)" = 5 ]
}

@test "la sauvegarde de la mise à jour reste, même après des archives d'une horloge en avance" {
  installed_then 0.2.0
  mkdir -p "$DIR/backups"
  local day
  for day in 1 2 3 4 5; do
    touch "$DIR/backups/button-2099010${day}T030000Z.tar"
  done
  station update
  assert_success
  local archive
  archive=$(sed -n 's/^  La sauvegarde d.avant : \(.*\)\.$/\1/p' <<<"$output")
  [ -f "$archive" ]
  [ ! -e "$DIR/backups/button-20990101T030000Z.tar" ]
  [ "$(find "$DIR/backups" -name 'button-*.tar' | wc -l)" = 5 ]
}

@test "un Caddyfile changé par la version fait repartir Caddy, que up ne recrée pas" {
  mkdir -p "$BATS_TEST_TMPDIR/suivante"
  { cat "$DEPLOY/Caddyfile"; echo "# changé en 0.2.0"; } >"$BATS_TEST_TMPDIR/suivante/Caddyfile"
  RELEASE_OVERLAY=$BATS_TEST_TMPDIR/suivante make_release 0.2.0 "$FAKE_STATE/releases/v0.2.0"
  installed_then 0.2.0
  # Caddy, d'une image épinglée, monte le Caddyfile ; le playout, rien du dossier.
  printf 'id-caddy\nid-playout\n' >"$FAKE_STATE/containers"
  printf 'id-caddy|caddy|%s %s \nid-playout|radiotomate-playout|%s \n' \
    "$DIR/Caddyfile" "$DIR/data/caddy" "$DIR/data/radiotomate" >"$FAKE_STATE/inspect-mounts"
  station update
  assert_success
  assert_output --partial "Mise à jour : recréés avec les fichiers de la version : caddy."
  logged "docker compose --profile cloud --profile share --profile vps up -d --force-recreate --no-deps caddy (dans $DIR)"
  run ! logged "--no-deps radiotomate-playout"
}

@test "update garde .env et compose.override.yml, et à côté un fichier que la station a changé" {
  installed_then 0.2.0
  printf 'services:\n  console:\n    restart: always\n' >"$DIR/compose.override.yml"
  echo "# un réglage de la station" >>"$DIR/Caddyfile"
  station update
  assert_success
  [ "$(cat "$DIR/compose.override.yml")" = "$(printf 'services:\n  console:\n    restart: always')" ]
  logged "-f $DIR/compose.override.yml --project-directory $DIR pull"
  cmp "$DIR/Caddyfile" "$DEPLOY/Caddyfile"
  grep -qx "# un réglage de la station" "$DIR"/Caddyfile.local-*
  assert_output --partial "Changés sur cette station, gardés à côté, en .local-… : Caddyfile. Les changements d'une station vont dans compose.override.yml."
  # VERSION change avec la version : il ne reste pas à côté.
  [ "$(find "$DIR" -name '*.local-*' | wc -l)" = 1 ]
}

@test "sans les fichiers de la version d'avant, chaque fichier remplacé reste à côté" {
  installed_then 0.2.0
  rm -r "$FAKE_STATE/releases/v0.1.0"
  station update
  assert_success
  assert_output --partial "Attention : les fichiers de la version 0.1.0 ne se téléchargent pas : chaque fichier que la mise à jour remplace sera gardé à côté."
  [ "$(cat "$DIR"/VERSION.local-*)" = 0.1.0 ]
}

@test "update ajoute à .env ce que la version y demande, sans rien changer d'autre" {
  installed_then 0.2.0
  local key
  key=$(env_of MEILI_MASTER_KEY)
  sed -i '/^MEILI_MASTER_KEY=/d' "$DIR/.env"
  station update
  assert_success
  assert_output --partial "Ajouté à .env : MEILI_MASTER_KEY."
  grep -q "^# Ajouté par station update, le " "$DIR/.env"
  [ ${#key} = 48 ] && [ "$(env_of MEILI_MASTER_KEY | wc -c)" = 49 ]
  [ "$(env_of MEILI_MASTER_KEY)" != "$key" ]
}

@test "une image qui ne se tire pas laisse la station en 0.1.0, avec sa sauvegarde" {
  installed_then 0.2.0
  cp "$DIR/.env" "$BATS_TEST_TMPDIR/env-avant"
  (cd "$DIR" && snapshot) | grep -v ' ./data/' >"$BATS_TEST_TMPDIR/dossier-avant"
  touch "$FAKE_STATE/pull-fails"
  station update
  assert_failure
  assert_output --partial "Les images de la version 0.2.0 ne se tirent pas : voir le message de docker compose plus haut. La station tourne toujours en 0.1.0."
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  # Rien n'a changé que la sauvegarde d'avant, et son journal.
  cmp "$BATS_TEST_TMPDIR/env-avant" "$DIR/.env"
  diff "$BATS_TEST_TMPDIR/dossier-avant" <( (cd "$DIR" && snapshot) |
    grep -v -e ' ./data/' -e ' ./backups/button-' -e ' ./backups.log$' -e ' ./updates.log$')
  [ "$(find "$DIR/backups" -name 'button-*.tar' | wc -l)" = 1 ]
  run ! logged "docker compose up"
  [ "$(last_update | cut -f1-3)" = "$(printf '0.1.0\t0.2.0\téchouée')" ]
  [ "$(last_update | cut -f5)" = "pendant les images" ]
}

@test "un contrôle qui échoue se dit, avec le chemin du retour, et se note" {
  installed_then 0.2.0
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  assert_output --partial "Le contrôle de la station a échoué en 0.2.0 : voir plus haut."
  assert_output --regexp "Revenir à la version 0\.1\.0 : voir docs/deploiement\.md, « Revenir en arrière », avec la sauvegarde $DIR/backups/button-[0-9TZ]+\.tar\."
  [ "$(last_update | cut -f1-3)" = "$(printf '0.1.0\t0.2.0\téchouée')" ]
  [ "$(last_update | cut -f5)" = "pendant le contrôle" ]
}

@test "relancée après un échec au redémarrage, update dit de réparer la station" {
  installed_then 0.2.0
  touch "$FAKE_STATE/up-fails"
  station update
  assert_failure
  assert_output --partial "Le moteur ne repart pas en 0.2.0"
  [ "$(last_update | cut -f3,5)" = "$(printf 'échouée\tpendant le redémarrage')" ]
  station update
  assert_success
  assert_output --partial "La station est déjà en 0.2.0. Rien à faire."
  assert_output --partial "Attention : la mise à jour vers 0.2.0 a échoué : voir station status. station install la répare, sur cette version."
}

@test "un échec pendant la sauvegarde se note, et status le dit" {
  installed_then 0.2.0
  touch "$FAKE_STATE/backup-fails"
  station update
  assert_failure
  [ "$(last_update | cut -f3-5)" = "$(printf 'échouée\t-\tpendant la sauvegarde')" ]
  station status
  assert_output --regexp "  La dernière : le [0-9/]+ à [0-9:]+, de 0\.1\.0 à 0\.2\.0, échouée, pendant la sauvegarde\."
}

@test "update passe la main à la commande station de la version visée" {
  installed_then 0.2.0
  # La commande de la 0.2.0 n'est pas celle-ci : elle le dit en démarrant.
  {
    head -n 1 "$STATION"
    echo 'echo "La commande de la version 0.2.0." >&2'
    tail -n +2 "$STATION"
  } >"$BATS_TEST_TMPDIR/station-0.2.0"
  RELEASE_STATION=$BATS_TEST_TMPDIR/station-0.2.0 make_release 0.2.0 "$FAKE_STATE/releases/v0.2.0"
  station update --yes
  assert_success
  assert_output --partial "Mise à jour : la commande station de la version 0.2.0 prend la main."
  assert_output --partial "La commande de la version 0.2.0."
  assert_output --partial "La station est à jour : 0.2.0, au lieu de 0.1.0."
  cmp "$DIR/station" "$BATS_TEST_TMPDIR/station-0.2.0"
  # Elle ne la repasse pas.
  [ "$(grep -c "prend la main" <<<"$output")" = 1 ]
}

@test "la commande à qui on a passé la main ne la repasse pas" {
  installed_then 0.2.0
  {
    head -n 1 "$STATION"
    echo 'echo "La commande de la version 0.2.0." >&2'
    tail -n +2 "$STATION"
  } >"$BATS_TEST_TMPDIR/station-0.2.0"
  RELEASE_STATION=$BATS_TEST_TMPDIR/station-0.2.0 make_release 0.2.0 "$FAKE_STATE/releases/v0.2.0"
  # Celle-ci n'est pas celle de l'archive : sans STATION_UPDATE_HANDOFF, elle
  # passerait la main.
  run env STATION_UPDATE_HANDOFF=1 bash "$STATION" update
  assert_success
  refute_output --partial "prend la main"
  refute_output --partial "La commande de la version 0.2.0."
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
}

@test "update depuis une archive, main compris ; de main, pas vers une version publiée" {
  installed_then 0.1.0
  station update --from "$FAKE_STATE/releases/v0.2.0/station.tar.gz"
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
  make_release main "$BATS_TEST_TMPDIR/main"
  station update --from "$BATS_TEST_TMPDIR/main/station.tar.gz" --yes
  assert_success
  assert_output --partial "Attention : main n'est pas une version publiée : pour un essai, jamais à l'antenne."
  [ "$(env_of BUTTON_VERSION)" = main ]
  station update --version 1.0.0 --major
  assert_failure
  assert_output --partial "La station suit main, pour un essai : sa base peut avoir un schéma plus récent que celui de la version 1.0.0."
  station update --from "$FAKE_STATE/releases/v0.2.0/station.tar.gz" --version 1.0.0
  assert_failure
  assert_output --partial "est la version 0.2.0, pas 1.0.0."
}

@test "update relance les services d'un autre profil qui tournaient" {
  installed_then 0.2.0
  printf 'caddy\nradiotomate-playout\nshare\n' >"$FAKE_STATE/services-running"
  station update
  assert_success
  logged "--profile cloud --profile share --profile vps pull share"
  logged "docker compose --profile cloud --profile share --profile vps up -d share (dans $DIR)"
}

@test "update relève la version de chaque service, pour la console" {
  installed_then 0.2.0
  printf 'a1\nb2\n' >"$FAKE_STATE/containers"
  cat >"$FAKE_STATE/inspect" <<'EOF'
radiotomate-playout|ghcr.io/lazbutton/button-playout:0.2.0|0.2.0
caddy|caddy:2.11-alpine|<no value>
EOF
  station update
  assert_success
  logged "docker inspect --format"
  local file=$DIR/data/radiotomate/versions.json
  grep -Eq '^\{"recorded_at":"[0-9-]+T[0-9:]+Z","version":"0.2.0","services":\[' "$file"
  grep -qF '{"service":"caddy","image":"caddy:2.11-alpine","version":""}' "$file"
  grep -qF '{"service":"radiotomate-playout","image":"ghcr.io/lazbutton/button-playout:0.2.0","version":"0.2.0"}' "$file"
  [ "$(stat -c %a "$file")" = 644 ]
  # Les mêmes versions, relevées encore par une relance d'install : le
  # fichier ne change pas, ni son heure.
  touch -d '2026-01-01 00:00' "$file"
  install_station --domain radio.example
  assert_success
  [ "$(date -r "$file" +%F)" = 2026-01-01 ]
}

@test "status dit la dernière mise à jour" {
  installed_then 0.2.0
  station update
  assert_success
  station status
  assert_output --regexp "  La dernière : le [0-9/]+ à [0-9:]+, de 0\.1\.0 à 0\.2\.0, faite, redémarrée et contrôlée en [0-9]+ s\."
  assert_output --partial "Version : 0.2.0, la plus haute publiée."
}

@test "au clavier, update se confirme ; non ne change rien" {
  installed_then 0.2.0
  station_at_keyboard update <<<"n"
  assert_failure
  assert_output --partial "Mettre la station à jour, de 0.1.0 à 0.2.0 ? Une sauvegarde d'abord, puis l'antenne se coupe le temps de redémarrer. (o/n) [n] :"
  assert_output --partial "Rien n'est changé."
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ ! -e "$DIR/backups" ]
  station_at_keyboard update <<<"o"
  assert_success
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
}

@test "update demande une station installée par station install" {
  installed_then 0.2.0
  rm "$DIR/VERSION"
  station update
  assert_failure
  assert_output --partial "La station de $DIR n'a pas de fichier VERSION : elle n'a pas été installée par station install."
  assert_output --partial "La mettre à jour à la main : voir docs/deploiement.md, « Mettre à jour »."
}

@test "l'aide d'update, et ses options" {
  installed
  station help update
  assert_success
  assert_output --partial "Usage : station update [options] [--dir DOSSIER]"
  assert_output --partial "--major"
  station update --help
  assert_success
  assert_output --partial "Usage : station update"
  station help
  assert_output --partial "update         la mettre à jour, vers la plus haute version publiée"
  station update --majeure
  assert_failure 2
  assert_output --partial "Option inconnue : --majeure."
  assert_output --partial "Voir : station help update."
}
