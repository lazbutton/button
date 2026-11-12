#!/usr/bin/env bats
# Les tests de la sauvegarde hors de la machine de deploy/station (SAV-01) :
# config --backup-remote, backup --remote, restore --remote et son test, et
# leurs minuteurs systemd. La même machine jouée par de faux outils que dans
# station.bats ; le faux docker y joue aussi restic, sur un dépôt fait d'un
# dossier de $FAKE_STATE/depots. Depuis la racine du dépôt :
#   ./scripts/verifier.sh deploy

bats_require_minimum_version 1.5.0

setup_file() {
  load helpers
  make_release 0.1.0 "$BATS_FILE_TMPDIR/releases/v0.1.0"
}

setup() {
  load helpers
  bats_load_library bats-support
  bats_load_library bats-assert
  setup_machine
  S3=s3:https://s3.stockage.example/sauvegardes/radio
  SECRET=$BATS_TEST_TMPDIR/secret-s3
  echo "cle-secrete-de-test" >"$SECRET"
  UNITS=$ROOT/etc/systemd/system
}

# Le dossier du faux dépôt.
depot() { # dépôt
  echo "$FAKE_STATE/depots/$(printf '%s' "$1" | tr -c 'A-Za-z0-9' '_')"
}

# La dernière sauvegarde du faux dépôt, son dossier.
last_snapshot() {
  find "$(depot "$S3")/snapshots" -mindepth 1 -maxdepth 1 | sort | tail -n 1
}

# Un dépôt fait ailleurs, avec son mot de passe et sans sauvegarde.
make_depot() { # dépôt, mot de passe
  mkdir -p "$(depot "$1")/snapshots"
  printf '%s\n' "$2" >"$(depot "$1")/password"
}

# Les lignes de backups-remote.log d'une sorte et d'un résultat.
remote_lines() { # sauvegarde ou test, résultat
  awk -F '\t' -v kind="$1" -v result="$2" '$2 == kind && $3 == result' "$DIR/backups-remote.log"
}

# Une station installée, sa sauvegarde hors de la machine réglée vers le dépôt
# S3 de test, et un journal vide.
remote_installed() {
  installed
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET"
  assert_success
  : >"$FAKE_STATE/log"
}

# --- config ---

@test "config --backup-remote crée le dépôt S3, le règle dans .env, et pose les minuteurs" {
  installed
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET"
  assert_success
  assert_output --partial "Dépôt : connexion à $S3."
  assert_output --partial "Dépôt : créé, vide, à $S3."
  assert_output --partial "Sauvegarde hors de la machine : chaque nuit à 03:00 (Europe/Paris), et le test de restauration le 1er de chaque mois, à 05:00"
  assert_output --partial "Changé dans $DIR/.env : BUTTON_BACKUP_REMOTE, BUTTON_BACKUP_PASSWORD, BUTTON_BACKUP_S3_ACCESS_KEY, BUTTON_BACKUP_S3_SECRET_KEY."
  # Sans terminal, le mot de passe du dépôt neuf ne s'affiche pas.
  assert_output --partial "Mot de passe du dépôt : pas affiché, la sortie n'est pas un terminal. Il est dans $DIR/.env, BUTTON_BACKUP_PASSWORD"
  local password
  password=$(env_of BUTTON_BACKUP_PASSWORD)
  [[ $password =~ ^[0-9a-f]{48}$ ]]
  refute_output --partial "$password"
  [ "$(env_of BUTTON_BACKUP_REMOTE)" = "$S3" ]
  [ "$(env_of BUTTON_BACKUP_S3_ACCESS_KEY)" = CLEDACCES ]
  [ "$(env_of BUTTON_BACKUP_S3_SECRET_KEY)" = cle-secrete-de-test ]
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  grep -q "^# Ajouté par station config, le " "$DIR/.env"
  # Les secrets passent par l'environnement de docker, jamais par sa ligne de
  # commande, que ps montre.
  logged "docker run --rm --network host --cpu-shares 256 --oom-score-adj 500 -e NICE=10 -e IONICE_CLASS=2 -e IONICE_PRIORITY=7 -e RESTIC_REPOSITORY -e RESTIC_PASSWORD -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e TZ=Europe/Paris -e RESTIC_CACHE_DIR=/cache -v $DIR/data/restic/cache:/cache -v $DIR/data/restic/ssh:/root/.ssh docker.io/restic/restic:0.19.1 init"
  run ! grep -qF -e "$password" -e cle-secrete-de-test "$FAKE_STATE/log"
  [ "$(cat "$(depot "$S3")/password")" = "$password" ]
  [ "$(stat -c %a "$DIR/data/restic")" = 700 ]
  # Les minuteurs : chaque nuit, et le 1er du mois, à l'heure de la station,
  # par la commande du dossier, qui attend une autre commande 2 h au plus.
  grep -qxF 'OnCalendar=*-*-* 03:00:00 Europe/Paris' "$UNITS/button-sauvegarde.timer"
  grep -qxF 'OnCalendar=*-*-01 05:00:00 Europe/Paris' "$UNITS/button-test-restauration.timer"
  grep -qxF "ExecStart=\"$DIR/station\" backup --remote --dir \"$DIR\"" "$UNITS/button-sauvegarde.service"
  grep -qxF "ExecStart=\"$DIR/station\" restore --remote --test --dir \"$DIR\"" "$UNITS/button-test-restauration.service"
  grep -qxF 'Environment=STATION_LOCK_WAIT=7200' "$UNITS/button-sauvegarde.service"
  grep -qxF 'Environment=HOME=/root' "$UNITS/button-test-restauration.service"
  grep -qxF 'Persistent=true' "$UNITS/button-sauvegarde.timer"
  [ "$(stat -c %a "$UNITS/button-sauvegarde.timer")" = 644 ]
  logged "systemctl daemon-reload"
  logged "systemctl enable --now button-sauvegarde.timer button-test-restauration.timer"

  station config
  assert_success
  assert_output --partial "Sauvegarde hors de la machine : chaque nuit à 03:00 (Europe/Paris), vers $S3, avec les sons"

  # Relancée, la même commande revérifie le dépôt, sans rien changer : ses
  # minuteurs ne se réécrivent pas, mais se réactivent.
  : >"$FAKE_STATE/log"
  station config --backup-remote "$S3"
  assert_success
  assert_output --partial "Dépôt : $S3, ouvert avec son mot de passe."
  assert_output --partial "Rien à changer"
  refute_output --partial "La sauvegarde de la nuit attend"
  run ! logged "systemctl daemon-reload"
  logged "systemctl enable --now button-sauvegarde.timer button-test-restauration.timer"
  [ "$(awk -F '\t' '$2 == "réglage"' "$DIR/backups-remote.log" | wc -l)" -eq 1 ]
}

@test "config : dans un terminal, le mot de passe d'un dépôt neuf s'affiche, une fois" {
  installed
  station_at_keyboard config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET"
  assert_success
  assert_output --partial "Mot de passe du dépôt : $(env_of BUTTON_BACKUP_PASSWORD)"
  assert_output --partial "À noter maintenant, hors de cette machine, avec l'adresse du dépôt"
}

@test "config : un dépôt qui existe demande son mot de passe, et un faux ne change rien" {
  installed
  make_depot "$S3" le-bon-mot-de-passe
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET"
  assert_failure
  assert_output --partial "Le dépôt $S3 existe déjà : il a son propre mot de passe. Rien n'est changé."
  assert_output --partial "--backup-password-file FICHIER"
  [ -z "$(env_of BUTTON_BACKUP_REMOTE)" ]
  [ -z "$(env_of BUTTON_BACKUP_PASSWORD)" ]
  [ ! -e "$UNITS/button-sauvegarde.timer" ]

  echo "un-faux" >"$BATS_TEST_TMPDIR/faux"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET" \
    --backup-password-file "$BATS_TEST_TMPDIR/faux"
  assert_failure
  assert_output --partial "Ce mot de passe n'ouvre pas le dépôt $S3. Rien n'est changé."
  [ -z "$(env_of BUTTON_BACKUP_REMOTE)" ]

  echo "  le-bon-mot-de-passe  " >"$BATS_TEST_TMPDIR/bon"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET" \
    --backup-password-file "$BATS_TEST_TMPDIR/bon"
  assert_success
  assert_output --partial "Dépôt : $S3, ouvert avec son mot de passe. Ses sauvegardes : station restore --remote --list."
  refute_output --partial "Mot de passe du dépôt"
  [ "$(env_of BUTTON_BACKUP_PASSWORD)" = le-bon-mot-de-passe ]
  [ -f "$UNITS/button-sauvegarde.timer" ]
}

@test "config : une station neuve devant un dépôt qui existe attend, jusqu'à sa première sauvegarde" {
  installed
  make_depot "$S3" le-bon-mot-de-passe
  echo le-bon-mot-de-passe >"$BATS_TEST_TMPDIR/bon"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET" \
    --backup-password-file "$BATS_TEST_TMPDIR/bon"
  assert_success
  assert_output --partial "La sauvegarde de la nuit attend : ce dépôt existait déjà"
  [ -f "$DIR/data/restic/en-attente" ]
  logged "systemctl disable --now button-sauvegarde.timer button-test-restauration.timer"
  run ! logged "systemctl enable"
  # Sauvegardée exprès, elle reprend la nuit.
  : >"$FAKE_STATE/log"
  station backup --remote
  assert_success
  [ ! -e "$DIR/data/restic/en-attente" ]
  logged "systemctl enable --now button-sauvegarde.timer button-test-restauration.timer"
  station status
  refute_output --partial "en attente"
  # Une station qui s'est déjà sauvegardée n'attend pas, même devant un autre
  # dépôt qui existe.
  local autre=s3:https://s3.stockage.example/autre/radio
  make_depot "$autre" le-bon-mot-de-passe
  station config --backup-remote "$autre"
  assert_success
  refute_output --partial "La sauvegarde de la nuit attend"
  [ ! -e "$DIR/data/restic/en-attente" ]
}

@test "config : un mot de passe avec \$, # ou un espace se garde entre apostrophes, et sert tel quel" {
  installed
  # Un dollar, tel quel : docker compose le lirait dans .env.
  # shellcheck disable=SC2016
  local password='un $mot #de passe'
  make_depot "$S3" "$password"
  echo "$password" >"$BATS_TEST_TMPDIR/mot"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET" \
    --backup-password-file "$BATS_TEST_TMPDIR/mot"
  assert_success
  grep -qxF "BUTTON_BACKUP_PASSWORD='un \$mot #de passe'" "$DIR/.env"
  station backup --remote
  assert_success

  echo "l'apostrophe" >"$BATS_TEST_TMPDIR/apostrophe"
  station config --backup-password-file "$BATS_TEST_TMPDIR/apostrophe"
  assert_failure
  assert_output --partial "a un caractère que .env ne garde pas : une apostrophe"
}

@test "config refuse un dépôt ni S3 ni SFTP, un dépôt S3 sans ses clés, et une option fausse" {
  installed
  local wrong
  # Un dollar, tel quel : docker compose le lirait dans .env.
  # shellcheck disable=SC2016
  for wrong in /srv/sauvegardes s3:https://stockage.example "s3:https://stockage.example/a b" sftp:stockage.example:/sauvegardes \
    'sftp:ci@h:/$HOME' b2:bucket:/radio; do
    station config --backup-remote "$wrong"
    [ "$status" -eq 2 ]
  done
  assert_output --partial "n'est pas un dépôt S3 ou SFTP"
  station config --backup-media peut-etre
  [ "$status" -eq 2 ]
  station config --backup-time 3h
  [ "$status" -eq 2 ]
  station config --backup-password-file "$BATS_TEST_TMPDIR/absent"
  [ "$status" -eq 2 ]
  station config --backup-s3-access-key "avec espace"
  [ "$status" -eq 2 ]

  station config --backup-remote "$S3"
  assert_failure
  assert_output --partial "Un dépôt S3 demande ses clés : --backup-s3-access-key CLÉ et --backup-s3-secret-key-file FICHIER. Rien n'est changé."
  station config --backup-password-file "$SECRET"
  assert_failure
  assert_output --partial "Aucun dépôt n'est réglé pour la sauvegarde hors de la machine. Rien n'est changé."
  run ! logged "restic"
  [ -z "$(env_of BUTTON_BACKUP_REMOTE)" ]
}

@test "config : un stockage qui refuse les clés, ou ne répond pas, ne change rien" {
  installed
  touch "$FAKE_STATE/restic-refuses"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET"
  assert_failure
  assert_output --partial "The request signature we calculated does not match"
  assert_output --partial "Le dépôt $S3 ne s'ouvre pas : voir le message de restic plus haut. Rien n'est changé."
  rm "$FAKE_STATE/restic-refuses"
  touch "$FAKE_STATE/restic-down"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET"
  assert_failure
  assert_output --partial "connection refused"
  [ -z "$(env_of BUTTON_BACKUP_REMOTE)" ]
  [ -z "$(env_of BUTTON_BACKUP_S3_SECRET_KEY)" ]
  [ ! -e "$UNITS/button-sauvegarde.timer" ]
  [ ! -e "$(depot "$S3")" ]
}

@test "config --backup-remote sftp : la clé SSH de la station, à autoriser, puis le dépôt" {
  installed
  local sftp=sftp://ci@sauvegarde.example:23//sauvegardes/radio key
  touch "$FAKE_STATE/restic-refuses"
  station config --backup-remote "$sftp"
  assert_failure
  assert_output --partial "Clé SSH : créée pour la sauvegarde hors de la machine, $DIR/data/restic/ssh/id_ed25519.pub."
  assert_output --partial "Permission denied (publickey)."
  assert_output --partial "La clé SSH de la station, que le stockage doit autoriser, dans ses clés autorisées (authorized_keys) :"
  assert_output --partial "  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAUSSE button-sauvegarde@radio.example"
  assert_output --partial "Rien n'est changé dans .env."
  logged "docker run --rm -v $DIR/data/restic/ssh:/cles --entrypoint ssh-keygen docker.io/restic/restic:0.19.1 -q -t ed25519 -N  -C button-sauvegarde@radio.example -f /cles/id_ed25519"
  [ -z "$(env_of BUTTON_BACKUP_REMOTE)" ]
  [ "$(stat -c %a "$DIR/data/restic/ssh")" = 700 ]
  [ "$(stat -c %a "$DIR/data/restic/ssh/config")" = 600 ]
  grep -qxF '  StrictHostKeyChecking accept-new' "$DIR/data/restic/ssh/config"
  grep -qxF '  IdentityFile /root/.ssh/id_ed25519' "$DIR/data/restic/ssh/config"
  key=$(cat "$DIR/data/restic/ssh/id_ed25519.pub")

  # Une fois la clé autorisée, la même commande passe, avec la même clé.
  rm "$FAKE_STATE/restic-refuses"
  : >"$FAKE_STATE/log"
  station config --backup-remote "$sftp"
  assert_success
  assert_output --partial "Dépôt : créé, vide, à $sftp."
  [ "$(cat "$DIR/data/restic/ssh/id_ed25519.pub")" = "$key" ]
  run ! logged "ssh-keygen"
  [ "$(env_of BUTTON_BACKUP_REMOTE)" = "$sftp" ]
  [ -z "$(env_of BUTTON_BACKUP_S3_ACCESS_KEY)" ]
  station backup --remote
  assert_success
  logged "-v $DIR/data/restic/ssh:/root/.ssh"
}

@test "config --backup-remote \"\" arrête la sauvegarde : ses minuteurs s'en vont, le mot de passe reste" {
  remote_installed
  station config --backup-remote ""
  assert_success
  assert_output --partial "Sauvegarde hors de la machine : arrêtée. Le dépôt garde ses sauvegardes, et .env son mot de passe, BUTTON_BACKUP_PASSWORD."
  [ -z "$(env_of BUTTON_BACKUP_REMOTE)" ]
  [ -n "$(env_of BUTTON_BACKUP_PASSWORD)" ]
  local unit
  for unit in button-sauvegarde.timer button-test-restauration.timer button-sauvegarde.service button-test-restauration.service; do
    [ ! -e "$UNITS/$unit" ]
  done
  logged "systemctl disable --now button-sauvegarde.timer button-test-restauration.timer"
  station status
  assert_output --partial "Sauvegarde hors de la machine : aucune. La régler : station config --backup-remote."
  station backup --remote
  assert_failure
  assert_output --partial "Aucune sauvegarde hors de la machine n'est réglée sur cette station."
}

@test "config --backup-time et --backup-media : l'heure du minuteur, et les sons" {
  remote_installed
  station config --backup-time 02:30 --backup-media no
  assert_success
  grep -qxF 'OnCalendar=*-*-* 02:30:00 Europe/Paris' "$UNITS/button-sauvegarde.timer"
  [ "$(env_of BUTTON_BACKUP_MEDIA)" = no ]
  logged "systemctl daemon-reload"
  run ! logged "restic/restic"
  station config
  assert_output --partial "chaque nuit à 02:30 (Europe/Paris), vers $S3, sans les sons"
}

# --- backup --remote ---

@test "backup --remote envoie la base, .env, Caddy et les sons dans le dépôt, puis fait la rotation" {
  remote_installed
  mkdir -p "$DIR/media/10-rotation"
  echo "un son" >"$DIR/media/10-rotation/titre.mp3"
  station backup --remote
  assert_success
  assert_output --partial "Sauvegarde hors de la machine : la base, sans couper l'antenne."
  assert_output --partial "Sauvegarde hors de la machine : l'envoi vers $S3, chiffré, avec les sons,"
  local snapshot id
  snapshot=$(last_snapshot)
  id=${snapshot##*-}
  assert_output --partial "Sauvegarde hors de la machine : faite, $id, dans $S3 : 2.000 KiB de neuf, 1.000 KiB une fois compressés."
  # Ce que porte une archive, et la banque sous media, comme le dit MANIFEST.
  run ls "$snapshot/tree/sauvegarde"
  assert_output "MANIFEST
SHA256SUMS
caddy.tar.gz
env
media
radiotomate.tar.gz"
  [ "$(cat "$snapshot/tree/sauvegarde/media/10-rotation/titre.mp3")" = "un son" ]
  (cd "$snapshot/tree/sauvegarde" && sha256sum -c SHA256SUMS)
  grep -qx 'media=media' "$snapshot/tree/sauvegarde/MANIFEST"
  grep -qx 'version=0.1.0' "$snapshot/tree/sauvegarde/MANIFEST"
  grep -qx 'RT_ADMIN_PASSWORD=' "$snapshot/tree/sauvegarde/env"
  [ "$(cat "$snapshot/host")" = button ]
  # La banque se lit sur place, en lecture seule ; puis la rotation.
  logged "-v $(readlink -f "$DIR/media"):/sauvegarde/media:ro docker.io/restic/restic:0.19.1 backup /sauvegarde --host button --tag button --tag version:0.1.0 --tag sons"
  logged "docker.io/restic/restic:0.19.1 forget --host button --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune"
  # Rien ne reste sur la machine, et l'antenne ne s'arrête pas.
  [ -z "$(find "$DIR/backups" -mindepth 1)" ]
  run ! logged " stop (dans $DIR)"
  [ -n "$(remote_lines sauvegarde faite | awk -F '\t' -v id="$id" '$4 == id')" ]
  [ ! -e "$FAKE_STATE/alerts" ]

  station status
  assert_success
  assert_output --partial "Sauvegarde hors de la machine : chaque nuit à 03:00 (Europe/Paris), vers $S3, avec les sons."
  assert_output --regexp "La dernière : le [0-9/]+ à [0-9:]+, il y a 1 min, faite \($id\) : 2.000 KiB de neuf"
  assert_output --partial "Test de restauration : aucun encore."
}

@test "backup --remote sans les sons, quand config le dit" {
  remote_installed
  echo "BUTTON_BACKUP_MEDIA=no" >>"$DIR/.env"
  mkdir -p "$DIR/media/10-rotation"
  echo "un son" >"$DIR/media/10-rotation/titre.mp3"
  station backup --remote
  assert_success
  local snapshot
  snapshot=$(last_snapshot)
  [ ! -e "$snapshot/tree/sauvegarde/media" ]
  grep -qx 'media=' "$snapshot/tree/sauvegarde/MANIFEST"
  run ! logged ":/sauvegarde/media:ro"
  logged "--tag version:0.1.0 --tag sans-sons"
}

@test "backup --remote qui échoue : backups-remote.log le note, status le dit, et l'alerte part" {
  remote_installed
  touch "$FAKE_STATE/restic-backup-fails"
  station backup --remote
  assert_failure
  assert_output --partial "Fatal: unable to save snapshot: connection reset by peer"
  assert_output --partial "La sauvegarde hors de la machine n'a pas abouti : voir le message de restic plus haut."
  remote_lines sauvegarde échouée | grep -qF "n'a pas abouti"
  grep -qF "logger -t button -p user.warning -- La sauvegarde hors de la machine a échoué : La sauvegarde hors de la machine n'a pas abouti" \
    "$FAKE_STATE/alerts"
  [ -z "$(find "$DIR/backups" -mindepth 1)" ]
  station status
  assert_output --partial ", échouée : La sauvegarde hors de la machine n'a pas abouti"
  assert_output --partial "aucune sauvegarde hors de la machine n'a encore réussi. Voir pourquoi : journalctl -u button-sauvegarde."
}

@test "backup --remote : sans des sons illisibles, faite ; une rotation ratée donne l'alerte" {
  remote_installed
  touch "$FAKE_STATE/restic-backup-partial" "$FAKE_STATE/restic-forget-fails"
  station backup --remote
  assert_success
  assert_output --partial "des fichiers ne se lisaient pas pendant la sauvegarde"
  assert_output --partial "la rotation du dépôt a échoué : la sauvegarde"
  remote_lines sauvegarde faite | grep -F "sans des fichiers qui ne se lisaient pas" | grep -qF "la rotation a échoué"
  grep -qF "Rotation de la sauvegarde hors de la machine ratée" "$FAKE_STATE/alerts"
  # Une rotation qui échoue sans un mot : la sauvegarde reste faite.
  rm "$FAKE_STATE/restic-backup-partial"
  echo silencieux >"$FAKE_STATE/restic-forget-fails"
  station backup --remote
  assert_success
  [ "$(remote_lines sauvegarde faite | wc -l)" -eq 2 ]
  [ -z "$(remote_lines sauvegarde échouée)" ]
}

@test "backup --remote ne part pas tant qu'une restauration n'est pas finie" {
  remote_installed
  printf '%s\n' "# station restore, le 10/11/2026 à 13:00 : pas finie, tant que ce fichier est là." >"$DIR/restauration-en-cours"
  station backup --remote
  assert_failure
  assert_output --partial "Une restauration ne s'est pas finie : $DIR/restauration-en-cours est encore là. La sauvegarde hors de la machine ne part pas."
  run ! logged "restic/restic:0.19.1 backup"
  grep -qF "La sauvegarde hors de la machine a échoué : Une restauration ne s'est pas finie" "$FAKE_STATE/alerts"
}

@test "backup --remote : sans dépôt, ou avec une archive ou --with-media, dit quoi faire" {
  installed
  station backup --remote
  assert_failure
  assert_output --partial "Aucune sauvegarde hors de la machine n'est réglée sur cette station."
  assert_output --partial "station config --backup-remote DÉPÔT"
  station backup --remote "$BATS_TEST_TMPDIR/x.tar"
  [ "$status" -eq 2 ]
  station backup --remote --with-media
  [ "$status" -eq 2 ]
  assert_output --partial "station config --backup-media"
}

@test "la sauvegarde de la nuit attend une autre commande, STATION_LOCK_WAIT secondes au plus" {
  remote_installed
  local lock=$ROOT/run/button-station.lock
  # Une commande qui finit pendant l'attente : la sauvegarde part ensuite.
  flock "$lock" sleep 2 &
  sleep 0.5
  run env STATION_LOCK_WAIT=10 bash "$STATION" backup --remote
  assert_success
  assert_output --partial "Une autre commande station tourne : station backup attend qu'elle finisse, 10 s au plus."
  assert_output --partial "Sauvegarde hors de la machine : faite,"
  refute_output --partial "unrecognized option"
  wait
  # Une commande qui dure plus que l'attente : l'échec et l'alerte.
  run env STATION_LOCK_WAIT=1 flock "$lock" bash "$STATION" backup --remote
  assert_failure
  assert_output --partial "attend qu'elle finisse, 1 s au plus."
  assert_output --partial "Une autre commande station tourne déjà sur cette machine."
  grep -qF "La sauvegarde hors de la machine a échoué : Une autre commande station tourne déjà" "$FAKE_STATE/alerts"
  # Sans attente, comme avant.
  run flock "$lock" bash "$STATION" backup --remote
  assert_failure
  refute_output --partial "attend qu'elle finisse"
}

# --- restore --remote ---

@test "après la perte de la machine, une installation neuve et restore --remote redonnent la station" {
  remote_installed
  mkdir -p "$DIR/media/10-rotation"
  echo "le son sauvegardé" >"$DIR/media/10-rotation/titre.mp3"
  printf 'ICECAST_MOUNT=antenne.mp3\nSUR_TOKEN=jeton-de-la-sauvegarde\n' >>"$DIR/.env"
  station backup --remote
  assert_success
  cp "$DIR/data/radiotomate/radiotomate.db" "$BATS_TEST_TMPDIR/base"
  cp "$DIR/data/caddy/certificates/site.crt" "$BATS_TEST_TMPDIR/certificat"
  env_of BUTTON_BACKUP_PASSWORD >"$BATS_TEST_TMPDIR/mot-de-passe"
  # Le stockage, chez un autre fournisseur, survit à la machine.
  cp -R "$FAKE_STATE/depots" "$BATS_TEST_TMPDIR/stockage"

  new_machine
  cp -R "$BATS_TEST_TMPDIR/stockage" "$FAKE_STATE/depots"
  installed
  echo "SUR_TOKEN=jeton-d-ici" >>"$DIR/.env"
  local secret
  secret=$(env_of MEILI_MASTER_KEY)
  run ! cmp -s "$BATS_TEST_TMPDIR/base" "$DIR/data/radiotomate/radiotomate.db"
  : >"$FAKE_STATE/log"
  station config --backup-remote "$S3" --backup-s3-access-key CLEDACCES --backup-s3-secret-key-file "$SECRET" \
    --backup-password-file "$BATS_TEST_TMPDIR/mot-de-passe"
  assert_success
  # Neuve, devant un dépôt qui a des sauvegardes : la nuit attend, sinon la
  # station vide deviendrait la dernière.
  assert_output --partial "La sauvegarde de la nuit attend : ce dépôt existait déjà, et cette station ne s'est jamais sauvegardée."
  refute_output --partial "La première sauvegarde part cette nuit"
  [ -f "$DIR/data/restic/en-attente" ]
  [ -f "$UNITS/button-sauvegarde.timer" ]
  logged "systemctl disable --now button-sauvegarde.timer button-test-restauration.timer"
  run ! logged "systemctl enable"
  station status
  assert_output --partial "Sauvegarde hors de la machine : en attente, vers $S3, un dépôt qui existait déjà."
  : >"$FAKE_STATE/log"
  station restore --remote
  assert_failure
  assert_output --partial "Sans terminal, station restore attend --yes pour se faire."
  # Avant de rien lire du dépôt.
  run ! logged "restic/restic:0.19.1 restore"
  station restore --remote --yes
  assert_success
  assert_output --partial "Restauration : lecture de la dernière sauvegarde du dépôt, $S3."
  assert_output --regexp "Sauvegarde du [0-9/]+ à [0-9:]+, d'une station en version 0.1.0, avec ses sons : [0-9a-f]{8}, dans le dépôt."
  assert_output --partial "La station est restaurée : celle de la sauvegarde du "
  cmp "$BATS_TEST_TMPDIR/base" "$DIR/data/radiotomate/radiotomate.db"
  cmp "$BATS_TEST_TMPDIR/certificat" "$DIR/data/caddy/certificates/site.crt"
  [ "$(cat "$DIR/media/10-rotation/titre.mp3")" = "le son sauvegardé" ]
  # .env reste celui de cette machine.
  [ "$(env_of MEILI_MASTER_KEY)" = "$secret" ]
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  # La dernière, puis la même par son ID ; les sons à côté de la banque.
  logged "restore latest --host button --target /cible --include /sauvegarde/MANIFEST --include /sauvegarde/SHA256SUMS"
  logged "--target /cible --include /sauvegarde/MANIFEST --include /sauvegarde/radiotomate.tar.gz --include /sauvegarde/env --include /sauvegarde/caddy.tar.gz"
  logged "-v $(readlink -f "$DIR/media").restauration-"
  logged "--target /cible --include /sauvegarde/media"
  logged "docker compose --profile cloud --profile share --profile vps stop (dans $DIR)"
  logged "smoke https://radio.example https://radio.example/radio.mp3"
  [ -n "$(leftovers 'media.avant-restauration-*')" ]
  [ -z "$(find "$DIR" -name '*.restauration-*' ! -name '*.avant-restauration-*')" ]
  [ ! -e "$DIR/restauration-en-cours" ]
  # De .env, les valeurs qui diffèrent, sans les secrets.
  assert_output --partial "Leurs valeurs dans la sauvegarde : ICECAST_MOUNT=antenne.mp3."
  refute_output --partial "jeton-de-la-sauvegarde"
  refute_output --partial "SUR_TOKEN"
  # Remise, la station reprend la nuit.
  [ ! -e "$DIR/data/restic/en-attente" ]
  logged "systemctl enable --now button-sauvegarde.timer button-test-restauration.timer"
  [ -f "$UNITS/button-sauvegarde.timer" ]
}

@test "restore --remote : --list montre les sauvegardes, et un ID en remet une plus ancienne" {
  remote_installed
  # Un dépôt encore vide.
  station restore --remote --yes
  assert_failure
  assert_output --partial "La dernière sauvegarde ne se lit pas dans le dépôt, $S3 : Fatal: failed to find snapshot"
  assert_output --partial "Les sauvegardes du dépôt, avec leur ID : station restore --remote --list."
  run ! logged " stop (dans $DIR)"
  station backup --remote
  assert_success
  local first second
  first=$(last_snapshot)
  first=${first##*-}
  cp "$DIR/data/radiotomate/radiotomate.db" "$BATS_TEST_TMPDIR/base"
  echo "écrit depuis" >>"$DIR/data/radiotomate/radiotomate.db"
  station backup --remote
  assert_success
  second=$(last_snapshot)
  second=${second##*-}

  station restore --remote --list
  assert_success
  assert_output --partial "Les sauvegardes du dépôt, $S3 :"
  assert_output --partial "$first"
  assert_output --partial "$second  "
  assert_output --partial "button,version:0.1.0,sons"
  logged "docker.io/restic/restic:0.19.1 snapshots --host button"
  run ! logged " stop (dans $DIR)"

  station restore --remote --test "$first"
  assert_success
  assert_output --partial "Test de restauration : la sauvegarde $first, sans ses sons, dans un dossier temporaire."
  assert_output --partial "Test de restauration : réussi. La sauvegarde $first,"

  station restore --remote "$first" --yes
  assert_success
  cmp "$BATS_TEST_TMPDIR/base" "$DIR/data/radiotomate/radiotomate.db"
  logged "restore $first --target /cible --include /sauvegarde/MANIFEST"

  station restore --remote 0badc0de --yes
  assert_failure
  assert_output --partial "La sauvegarde 0badc0de ne se lit pas dans le dépôt, $S3 : Fatal: no matching ID found for prefix"
  station restore --remote pas-un-id
  [ "$status" -eq 2 ]
  station restore --remote --list "$first"
  [ "$status" -eq 2 ]
  station restore --list
  [ "$status" -eq 2 ]
}

@test "restore --remote : une station qui ne repart pas laisse revenir celle d'avant, sons compris" {
  remote_installed
  mkdir -p "$DIR/media/10-rotation"
  echo "le son sauvegardé" >"$DIR/media/10-rotation/titre.mp3"
  station backup --remote
  assert_success
  echo "un son d'après" >"$DIR/media/10-rotation/titre.mp3"
  echo "écrit depuis la sauvegarde" >>"$DIR/data/radiotomate/radiotomate.db"
  local base
  base=$(cat "$DIR/data/radiotomate/radiotomate.db")
  touch "$FAKE_STATE/up-fails"
  station restore --remote --yes
  assert_failure
  assert_output --partial "La station ne démarre pas sur la sauvegarde"
  assert_output --partial "la restauration s'annule : la station d'avant reprend sa place, et repart."
  [ "$(cat "$DIR/data/radiotomate/radiotomate.db")" = "$base" ]
  [ "$(cat "$DIR/media/10-rotation/titre.mp3")" = "un son d'après" ]
  [ -z "$(leftovers '*restauration-*')" ]
  [ ! -e "$DIR/restauration-en-cours" ]
  # Une restauration ratée n'est pas une sauvegarde ratée : pas d'alerte.
  [ ! -e "$FAKE_STATE/alerts" ]
}

@test "restore --remote ne remplace pas une banque qui est un point de montage, et dit quoi faire" {
  remote_installed
  station backup --remote
  assert_success
  local id
  id=$(last_snapshot)
  id=${id##*-}
  echo "$DIR/media" >"$FAKE_STATE/mounts"
  : >"$FAKE_STATE/log"
  station restore --remote --yes
  assert_failure
  assert_output --partial "La banque de sons, $DIR/media, est un point de montage : restore ne sait pas la remplacer. Rien n'a changé."
  assert_output --partial "station restore --remote $id --without-media, puis y remettre ceux de la sauvegarde : voir docs/exploitation/sauvegarde.md, « Une banque sur son propre disque »."
  refute_output --partial "tar -xf"
  run ! logged " stop (dans $DIR)"
  station restore --remote "$id" --yes --without-media
  assert_success
}

@test "restore --remote d'une sauvegarde qui n'est pas d'une station le dit, sans rien changer" {
  remote_installed
  station backup --remote
  assert_success
  local snapshot
  snapshot=$(depot "$S3")/snapshots/999-0badcafe
  mkdir -p "$snapshot/tree/autre"
  echo button >"$snapshot/tags"
  echo button >"$snapshot/host"
  : >"$FAKE_STATE/log"
  station restore --remote 0badcafe --yes
  assert_failure
  assert_output --partial "La sauvegarde 0badcafe du dépôt n'est pas une sauvegarde de station : elle n'a pas de MANIFEST."
  refute_output --partial "sed:"
  run ! logged " stop (dans $DIR)"
  station restore --remote --test 0badcafe
  assert_failure
  remote_lines test échoué | grep -qF "n'est pas une sauvegarde de station"
}

@test "restore --remote d'une sauvegarde sans les sons, ou --without-media, garde la banque" {
  remote_installed
  echo "BUTTON_BACKUP_MEDIA=no" >>"$DIR/.env"
  station backup --remote
  assert_success
  echo "un son d'ici" >"$DIR/media/ici.mp3"
  station restore --remote --yes
  assert_success
  [ "$(cat "$DIR/media/ici.mp3")" = "un son d'ici" ]
  run ! logged "--include /sauvegarde/media"
  [ -z "$(leftovers 'media.*restauration-*')" ]
}

# --- restore --remote --test ---

@test "restore --remote --test restaure la dernière dans un dossier temporaire, sans rien changer" {
  remote_installed
  mkdir -p "$DIR/media/10-rotation"
  echo "un son" >"$DIR/media/10-rotation/titre.mp3"
  station backup --remote
  assert_success
  local base id
  base=$(cat "$DIR/data/radiotomate/radiotomate.db")
  id=$(last_snapshot)
  id=${id##*-}
  : >"$FAKE_STATE/log"
  station restore --remote --test
  assert_success
  assert_output --partial "Test de restauration : le dépôt, $S3, vérifié par restic check."
  assert_output --partial "Test de restauration : la dernière sauvegarde, sans ses sons, dans un dossier temporaire."
  assert_output --regexp "Test de restauration : réussi. La sauvegarde $id, du [0-9/]+ à [0-9:]+, d'une station en version 0.1.0, se remet : ses sommes et sa base sont bonnes, au schéma v18."
  logged "docker.io/restic/restic:0.19.1 check"
  logged "/restore-radiotomate.sh /sauvegarde.tar.gz /cible"
  run ! logged "--include /sauvegarde/media"
  run ! logged " stop (dans $DIR)"
  [ "$(cat "$DIR/data/radiotomate/radiotomate.db")" = "$base" ]
  [ -z "$(find "$DIR/data" -maxdepth 1 -name '.station-*')" ]
  [ -n "$(remote_lines test réussi | awk -F '\t' -v id="$id" '$4 == id')" ]
  station status
  assert_output --regexp "Le dernier test de restauration : le [0-9/]+ à [0-9:]+, réussi : la sauvegarde du [0-9/]+ à [0-9:]+, en version 0.1.0, avec sa base au schéma v18."
}

@test "restore --remote --test qui échoue, dépôt ou sauvegarde abîmés : backups-remote.log et l'alerte le disent" {
  remote_installed
  station backup --remote
  assert_success
  touch "$FAKE_STATE/restic-check-fails"
  station restore --remote --test
  assert_failure
  assert_output --partial "Le dépôt ne passe pas restic check : Fatal: repository contains errors"
  grep -qF "Le test de restauration a échoué : Le dépôt ne passe pas restic check" "$FAKE_STATE/alerts"

  rm "$FAKE_STATE/restic-check-fails"
  echo "# changé" >>"$(last_snapshot)/tree/sauvegarde/env"
  station restore --remote --test
  assert_failure
  assert_output --partial "La sauvegarde est abîmée : un de ses fichiers ne correspond pas à sa somme, dans SHA256SUMS."
  [ "$(remote_lines test échoué | wc -l)" -eq 2 ]
  [ "$(grep -c "Le test de restauration a échoué" "$FAKE_STATE/alerts")" -eq 2 ]
  station status
  assert_output --regexp "Le dernier test de restauration : le [0-9/]+ à [0-9:]+, échoué : La sauvegarde est abîmée"
}

# --- Les minuteurs ---

@test "les minuteurs : install les remet, uninstall les retire, et purge dit que le mot de passe part" {
  remote_installed
  rm "$UNITS/button-sauvegarde.timer"
  station status
  assert_output --partial "le minuteur de la sauvegarde hors de la machine ne tourne pas"
  install_station
  assert_success
  [ -f "$UNITS/button-sauvegarde.timer" ]
  assert_output --partial "Sauvegarde hors de la machine : chaque nuit à 03:00 (Europe/Paris)"

  station_at_keyboard uninstall --purge <<<"non"
  assert_failure
  assert_output --partial "Les sauvegardes hors de la machine restent dans leur dépôt, $S3. Son mot de passe s'efface avec .env : le noter d'abord"

  : >"$FAKE_STATE/log"
  station uninstall --yes
  assert_success
  logged "systemctl disable --now button-sauvegarde.timer button-test-restauration.timer"
  logged "docker image rm docker.io/restic/restic:0.19.1"
  [ -z "$(ls -A "$UNITS")" ]
  # station install les remet, avec la même station.
  run bash "$FAKE_STATE/releases/v0.1.0/station" install
  assert_success
  [ -f "$UNITS/button-sauvegarde.timer" ]
  [ -f "$UNITS/button-test-restauration.service" ]
}

@test "les minuteurs : status dit qu'ils ne tournent pas, et install les réactive sans les réécrire" {
  remote_installed
  touch "$FAKE_STATE/timers-stopped"
  station status
  assert_output --partial "le minuteur de la sauvegarde hors de la machine ne tourne pas : elle ne part pas seule chaque nuit. station install le remet."
  : >"$FAKE_STATE/log"
  install_station
  assert_success
  logged "systemctl enable --now button-sauvegarde.timer button-test-restauration.timer"
  run ! logged "systemctl daemon-reload"
}

@test "status avertit : aucune sauvegarde depuis le réglage, aucun test, un test raté ou trop vieux" {
  remote_installed
  # Les lignes d'une sorte de backups-remote.log, vieillies de tant de jours.
  age() { # sorte, jours
    awk -F '\t' -v OFS='\t' -v kind="$1" -v time=$(($(date +%s) - $2 * 86400)) \
      '$2 == kind { $1 = time } { print }' "$DIR/backups-remote.log" >"$BATS_TEST_TMPDIR/journal"
    cat "$BATS_TEST_TMPDIR/journal" >"$DIR/backups-remote.log"
  }
  station status
  refute_output --partial "Attention"
  age réglage 3
  station status
  assert_output --partial "aucune sauvegarde hors de la machine n'a réussi depuis son réglage, le "
  refute_output --partial "aucun test de restauration"
  age réglage 40
  station status
  assert_output --partial "aucun test de restauration depuis le réglage de la sauvegarde hors de la machine"

  station backup --remote
  assert_success
  station restore --remote --test
  assert_success
  station status
  refute_output --partial "Attention"
  age sauvegarde 3
  age test 40
  station status
  assert_output --partial "la dernière sauvegarde hors de la machine réussie date du "
  assert_output --partial "le dernier test de restauration date du "
  touch "$FAKE_STATE/restic-check-fails"
  station restore --remote --test
  assert_failure
  station status
  assert_output --partial "le dernier test de restauration a échoué. Voir pourquoi : journalctl -u button-test-restauration"
}

@test "systemd_quote garde un chemin tel quel dans une ligne de commande de systemd" {
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; systemd_quote "$2"' _ "$STATION" '/opt/radio 100%/$HOME/"x"\y'
  assert_success
  # shellcheck disable=SC2016
  assert_output '"/opt/radio 100%%/$$HOME/\"x\"\\y"'
}

@test "les minuteurs suivent le fuseau d'une restauration, et s'en vont devant une commande qui ne les connaît pas" {
  remote_installed
  # Une sauvegarde d'une station de Montréal, remise ici : son fuseau vient avec.
  sed -i 's/^TZ=.*/TZ=America\/Montreal/' "$DIR/.env"
  station backup "$BATS_TEST_TMPDIR/montreal.tar"
  assert_success
  sed -i 's/^TZ=.*/TZ=Europe\/Paris/' "$DIR/.env"
  station restore "$BATS_TEST_TMPDIR/montreal.tar" --yes
  assert_success
  grep -qxF 'OnCalendar=*-*-* 03:00:00 America/Montreal' "$UNITS/button-sauvegarde.timer"

  # La commande d'une version d'avant, remise par un retour arrière.
  grep -v BUTTON_BACKUP_REMOTE "$STATION" >"$DIR/station"
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; dir=$2; env_file=$2/.env; remote_timers' _ "$STATION" "$DIR"
  assert_success
  assert_output --partial "ne connaît pas la sauvegarde hors de la machine : ses minuteurs s'en vont"
  [ ! -e "$UNITS/button-sauvegarde.timer" ]
}

# --- L'aide ---

@test "station help dit les options de la sauvegarde hors de la machine" {
  run bash "$STATION" help backup
  assert_output --partial "station backup --remote [--dir DOSSIER]"
  run bash "$STATION" help restore
  assert_output --partial "station restore --remote --test [ID]"
  run bash "$STATION" help config
  assert_output --partial "--backup-remote DÉPÔT"
  assert_output --partial "un autre fournisseur que celui de"
}
