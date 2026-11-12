#!/usr/bin/env bats
# Les tests des alertes de deploy/station (SUR-01) : ntfy et l'e-mail, réglés
# par install et config après un essai, puis les alertes de la commande, qui
# partent par eux. La même machine jouée par de faux outils que dans
# station.bats ; le faux curl y joue un faux ntfy et un faux serveur SMTP.
# Depuis la racine du dépôt :
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
  # Un mot de passe que docker compose lirait mal hors d'apostrophes : un $,
  # des espaces, des guillemets.
  # shellcheck disable=SC2016
  SECRET='mot de passe $smtp "de" test'
  PASSWORD=$BATS_TEST_TMPDIR/smtp
  echo "$SECRET" >"$PASSWORD"
  TOKEN=$BATS_TEST_TMPDIR/jeton
  echo "tk_jeton-de-test" >"$TOKEN"
  SMTP=(--alert-email "technique@radio.example, direction@radio.example" --alert-smtp smtp.radio.example:587
    --alert-smtp-user alertes@radio.example --alert-smtp-password-file "$PASSWORD")
}

# Le message n de ntfy, une ligne : l'adresse, puis le JSON.
ntfy_message() { # n
  sed -n "${1}p" "$FAKE_STATE/ntfy"
}

ntfy_count() {
  if [[ -f $FAKE_STATE/ntfy ]]; then wc -l <"$FAKE_STATE/ntfy"; else echo 0; fi
}

mail_count() {
  find "$FAKE_STATE/mails" -name '*.eml' 2>/dev/null | wc -l
}

# Le sujet de l'e-mail n, ses mots encodés décodés.
mail_subject() { # n
  local subject="" word
  while read -r word; do
    if [[ $word =~ ^=\?UTF-8\?B\?(.*)\?=$ ]]; then
      subject+=$(printf '%s' "${BASH_REMATCH[1]}" | base64 -d)
    else
      subject+=$word
    fi
  done < <(awk '/^Subject: / { sub(/^Subject: /, ""); print; on = 1; next } on && /^ / { sub(/^ /, ""); print; next } { on = 0 }' \
    "$FAKE_STATE/mails/$1.eml")
  printf '%s\n' "$subject"
}

# Le texte de l'e-mail n, décodé.
mail_body() { # n
  sed '1,/^$/d' "$FAKE_STATE/mails/$1.eml" | base64 -d
}

# Une station installée, ses alertes réglées vers ntfy.sh et par e-mail, et
# un journal vide.
alerts_installed() {
  installed
  station config --alert-ntfy https://ntfy.sh "${SMTP[@]}"
  assert_success
  rm -rf "$FAKE_STATE/ntfy" "$FAKE_STATE/ntfy-config" "$FAKE_STATE/mails"
  : >"$FAKE_STATE/log"
}

# Une alerte de la commande, comme cleanup ou update la donnent.
alert() { # sujet, message, note ou rien
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; dir=$2; shift 2; station_alert "$@"' _ "$STATION" "$DIR" "$@"
}

# --- config ---

@test "config --alert-ntfy https://ntfy.sh tire un sujet au hasard, l'essaie, puis radiotomate.yaml suit" {
  installed
  station config --alert-ntfy https://ntfy.sh
  assert_success
  assert_output --partial "Alertes : un essai par ntfy."
  assert_output --partial "Changé dans $DIR/.env : BUTTON_ALERT_NTFY."
  assert_output --partial "Alertes d'antenne : radiotomate.yaml suit, et le scheduler les prend d'ici une minute, sans couper l'antenne."
  local topic
  topic=$(env_of BUTTON_ALERT_NTFY)
  [[ $topic =~ ^https://ntfy\.sh/button-[0-9a-f]{24}$ ]]
  # Sans terminal, le sujet ne s'affiche pas : qui le connaît lit les alertes.
  refute_output --partial "$topic"
  assert_output --partial "Alertes sur le téléphone : le sujet ntfy est dans $DIR/.env, BUTTON_ALERT_NTFY"
  # L'essai, posté à la racine de ntfy.sh, en JSON, insiste comme une alerte.
  [ "$(ntfy_count)" -eq 1 ]
  ntfy_message 1 | grep -qF "https://ntfy.sh/ {\"topic\":\"${topic##*/}\",\"title\":\"Essai des alertes · radio.example\""
  ntfy_message 1 | grep -qF '"message":"Les alertes de la station arriveront ici : un silence à l'"'"'antenne'
  ntfy_message 1 | grep -qF '"priority":4,"tags":["bell"]}'
  # radiotomate-init relancé une fois .env écrit, pour radiotomate.yaml.
  logged "docker compose run --rm --no-deps -T radiotomate-init (dans $DIR)"
  logged "radiotomate-init relancé : BUTTON_ALERT_NTFY=$topic"
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  # Le même sujet, redemandé : un autre, tiré au hasard. Le sien se garde.
  station config --alert-ntfy "$topic"
  assert_success
  assert_output --partial "Rien à changer"
  [ "$(env_of BUTTON_ALERT_NTFY)" = "$topic" ]
}

@test "dans un terminal, config dit le sujet où s'abonner" {
  installed
  station_at_keyboard config --alert-ntfy ntfy.sh
  assert_success
  local topic
  topic=$(env_of BUTTON_ALERT_NTFY)
  assert_output --partial "Alertes sur le téléphone : s'abonner, dans l'application ntfy, au sujet $topic."
  station_at_keyboard config
  assert_success
  assert_output --partial "  Alertes : par ntfy, sujet $topic"
  station config
  assert_success
  assert_output --partial "  Alertes : par ntfy, sur https://ntfy.sh"
  refute_output --partial "$topic"
}

@test "le jeton d'un sujet protégé passe par la configuration de curl, jamais par sa ligne de commande" {
  installed
  station config --alert-ntfy https://ntfy.radio.example/alertes-de-la-station --alert-ntfy-token-file "$TOKEN"
  assert_success
  [ "$(env_of BUTTON_ALERT_NTFY)" = https://ntfy.radio.example/alertes-de-la-station ]
  [ "$(env_of BUTTON_ALERT_NTFY_TOKEN)" = tk_jeton-de-test ]
  ntfy_message 1 | grep -qF 'https://ntfy.radio.example/ {"topic":"alertes-de-la-station"'
  grep -qxF 'header = "Authorization: Bearer tk_jeton-de-test"' "$FAKE_STATE/ntfy-config"
  run ! grep -qF tk_jeton-de-test "$FAKE_STATE/log"
  refute_output --partial tk_jeton-de-test
}

@test "config règle l'e-mail : l'essai part en STARTTLS exigé, avec le compte, et l'expéditeur est le compte" {
  installed
  station config "${SMTP[@]}"
  assert_success
  assert_output --partial "Alertes : un essai par e-mail."
  assert_output --partial "Changé dans $DIR/.env : BUTTON_ALERT_EMAIL, BUTTON_ALERT_FROM, BUTTON_ALERT_SMTP, BUTTON_ALERT_SMTP_USER, BUTTON_ALERT_SMTP_PASSWORD."
  [ "$(env_of BUTTON_ALERT_EMAIL)" = "technique@radio.example,direction@radio.example" ]
  [ "$(env_of BUTTON_ALERT_FROM)" = alertes@radio.example ]
  [ "$(env_of BUTTON_ALERT_SMTP)" = smtp.radio.example:587 ]
  # Entre apostrophes : docker compose lirait $ et les espaces.
  [ "$(env_of BUTTON_ALERT_SMTP_PASSWORD)" = "'$SECRET'" ]
  [ "$(mail_count)" -eq 1 ]
  local sent=$FAKE_STATE/mails/1.envoi
  grep -qxF "adresse smtp://smtp.radio.example:587" "$sent"
  grep -qxF "expéditeur alertes@radio.example" "$sent"
  grep -qxF "destinataires technique@radio.example direction@radio.example" "$sent"
  grep -qF -- " --ssl-reqd " "$sent"
  grep -qF -- " --crlf " "$sent"
  grep -qxF "user = \"alertes@radio.example:${SECRET//\"/\\\"}\"" "$sent"
  [ "$(mail_subject 1)" = "Essai des alertes · radio.example" ]
  grep -qxF "To: technique@radio.example, direction@radio.example" "$FAKE_STATE/mails/1.eml"
  grep -qxF "From: BUTTON <alertes@radio.example>" "$FAKE_STATE/mails/1.eml"
  mail_body 1 | grep -qF "Les alertes de la station arriveront ici"
  mail_body 1 | grep -qF 'Pour ne plus recevoir ces e-mails, sur la machine de la station : station config --alert-email "".'
  # Le mot de passe ne passe ni par la ligne de commande, ni par la sortie.
  run ! grep -qF "$SECRET" "$FAKE_STATE/log"
  refute_output --partial "$SECRET"
  logged "radiotomate-init relancé : BUTTON_ALERT_NTFY= BUTTON_ALERT_EMAIL=technique@radio.example,direction@radio.example"
}

@test "le port 465 prend TLS dès le début, et un compte sans adresse donne l'expéditeur button@ le domaine" {
  installed
  station config --alert-email technique@radio.example --alert-smtp smtp.radio.example:465 \
    --alert-smtp-user compte-sans-adresse --alert-smtp-password-file "$PASSWORD"
  assert_success
  grep -qxF "adresse smtps://smtp.radio.example:465" "$FAKE_STATE/mails/1.envoi"
  [ "$(env_of BUTTON_ALERT_FROM)" = button@radio.example ]
  station config --alert-from alertes@radio.example
  assert_success
  [ "$(env_of BUTTON_ALERT_FROM)" = alertes@radio.example ]
  [ "$(mail_count)" -eq 2 ]
}

@test "un essai qui ne part pas ne change rien" {
  installed
  cp "$DIR/.env" "$BATS_TEST_TMPDIR/env-avant"
  touch "$FAKE_STATE/ntfy-down"
  station config --alert-ntfy https://ntfy.sh
  assert_failure
  assert_output --partial "L'essai par ntfy ne part pas : curl: (7) Failed to connect to ntfy.sh port 443"
  assert_output --partial "Rien n'est changé."
  assert_output --partial "Vérifier l'adresse du sujet, le jeton d'un sujet protégé, et que la machine joint le serveur ntfy."
  touch "$FAKE_STATE/smtp-refuses"
  station config "${SMTP[@]}"
  assert_failure
  assert_output --partial "L'essai par e-mail ne part pas : curl: (67) Login denied. Rien n'est changé."
  assert_output --partial "Vérifier le serveur SMTP et son port, 465 en TLS dès le début ou 587 en STARTTLS"
  diff "$BATS_TEST_TMPDIR/env-avant" "$DIR/.env"
  run ! logged "radiotomate-init"
}

@test "un e-mail sans serveur SMTP, ou un compte sans mot de passe, ne se règle pas" {
  installed
  station config --alert-email technique@radio.example
  assert_failure
  assert_output --partial "Les alertes par e-mail demandent le serveur SMTP qui les envoie. Rien n'est changé."
  station config --alert-email technique@radio.example --alert-smtp smtp.radio.example --alert-smtp-user alertes@radio.example
  assert_failure
  assert_output --partial "Le compte SMTP alertes@radio.example n'a pas de mot de passe. Rien n'est changé."
  [ "$(mail_count)" -eq 0 ]
}

@test "config refuse une alerte mal écrite, avant de rien faire" {
  installed
  station config --alert-ntfy "https://ntfy.sh/un/deux"
  assert_failure 2
  assert_output --partial "n'est pas une adresse de ntfy"
  station config --alert-email "technique@radio.example, pas-un-email"
  assert_failure 2
  assert_output --partial "« pas-un-email » n'est pas un e-mail"
  station config --alert-email technique@radio.example --alert-smtp "smtp.radio.example:99999"
  assert_failure 2
  assert_output --partial "un serveur SMTP s'écrit HÔTE:PORT"
  station config --alert-smtp-user "deux mots"
  assert_failure 2
  station config --alert-ntfy-token-file "$BATS_TEST_TMPDIR/absent"
  assert_failure 2
  assert_output --partial "--alert-ntfy-token-file : $BATS_TEST_TMPDIR/absent n'existe pas."
  [ "$(ntfy_count)" -eq 0 ]
}

@test "\"\" arrête un canal, sans essai, et le jeton s'en va avec ntfy" {
  installed
  station config --alert-ntfy https://ntfy.radio.example/alertes-de-la-station --alert-ntfy-token-file "$TOKEN" "${SMTP[@]}"
  assert_success
  rm -f "$FAKE_STATE/ntfy"
  : >"$FAKE_STATE/log"
  station config --alert-ntfy ""
  assert_success
  assert_output --partial "Changé dans $DIR/.env : BUTTON_ALERT_NTFY, BUTTON_ALERT_NTFY_TOKEN."
  [ -z "$(env_of BUTTON_ALERT_NTFY)" ]
  [ -z "$(env_of BUTTON_ALERT_NTFY_TOKEN)" ]
  [ "$(ntfy_count)" -eq 0 ]
  logged "radiotomate-init relancé : BUTTON_ALERT_NTFY= BUTTON_ALERT_EMAIL=technique@radio.example,direction@radio.example"
  station config --alert-email ""
  assert_success
  [ -z "$(env_of BUTTON_ALERT_EMAIL)" ]
  # Le serveur reste, pour un e-mail qui reviendrait.
  [ "$(env_of BUTTON_ALERT_SMTP)" = smtp.radio.example:587 ]
  station status
  assert_output --partial "Alertes : aucune, hors du journal du système."
}

@test "radiotomate.yaml qui ne suit pas se dit, .env écrit" {
  installed
  touch "$FAKE_STATE/init-fails"
  station config --alert-ntfy https://ntfy.sh
  assert_success
  assert_output --partial "radiotomate-init : échec"
  assert_output --partial "Attention : radiotomate.yaml ne suit pas : les alertes d'antenne, comme un silence, gardent l'ancien réglage."
  [ -n "$(env_of BUTTON_ALERT_NTFY)" ]
}

@test "--alert-test essaie chaque canal réglé, sans rien changer" {
  installed
  station config --alert-test
  assert_failure
  assert_output --partial "Aucune alerte n'est réglée sur cette station : rien à essayer."
  station config --alert-ntfy https://ntfy.sh "${SMTP[@]}"
  assert_success
  cp "$DIR/.env" "$BATS_TEST_TMPDIR/env-avant"
  station config --alert-test
  assert_success
  assert_output --partial "Alertes : l'essai par ntfy est parti."
  assert_output --partial "Alertes : l'essai par e-mail est parti."
  refute_output --partial "Rien à changer"
  [ "$(ntfy_count)" -eq 2 ]
  [ "$(mail_count)" -eq 2 ]
  diff "$BATS_TEST_TMPDIR/env-avant" "$DIR/.env"
  touch "$FAKE_STATE/smtp-down"
  station config --alert-test
  assert_failure
  assert_output --partial "L'essai par e-mail ne part pas : curl: (7) Failed to connect"
}

# --- install ---

@test "install règle les alertes par ses options, après un essai, avant de rien écrire" {
  install_station --domain radio.example --alert-ntfy https://ntfy.sh "${SMTP[@]}"
  assert_success
  local topic
  topic=$(env_of BUTTON_ALERT_NTFY)
  [[ $topic =~ ^https://ntfy\.sh/button-[0-9a-f]{24}$ ]]
  [ "$(env_of BUTTON_ALERT_EMAIL)" = "technique@radio.example,direction@radio.example" ]
  [ "$(env_of BUTTON_ALERT_FROM)" = alertes@radio.example ]
  [ "$(env_of BUTTON_ALERT_SMTP_USER)" = alertes@radio.example ]
  grep -qxF "# Les alertes sur un téléphone, par ntfy, et par e-mail : station config les" "$DIR/.env"
  assert_output --partial "  Alertes : par ntfy, sur https://ntfy.sh, et par e-mail, à technique@radio.example, direction@radio.example"
  assert_output --partial "  Sur le téléphone : le sujet ntfy est dans $DIR/.env, BUTTON_ALERT_NTFY."
  refute_output --partial "$topic"
  [ "$(ntfy_count)" -eq 1 ]
  [ "$(mail_count)" -eq 1 ]
  [ "$(mail_subject 1)" = "Essai des alertes · radio.example" ]
  # L'essai part avant le dossier de la station.
  local essai dossier
  essai=$(grep -n "smtp://smtp.radio.example:587" "$FAKE_STATE/log" | head -n 1 | cut -d: -f1)
  dossier=$(grep -n "docker compose pull" "$FAKE_STATE/log" | head -n 1 | cut -d: -f1)
  ((essai < dossier))
}

@test "un essai raté à l'installation n'installe rien" {
  touch "$FAKE_STATE/smtp-refuses"
  install_station --domain radio.example "${SMTP[@]}"
  assert_failure
  assert_output --partial "L'essai par e-mail ne part pas : curl: (67) Login denied. Rien n'est changé."
  [ ! -e "$DIR/.env" ]
}

@test "sans terminal ni option, install ne règle aucune alerte, et n'en envoie pas" {
  installed
  [ "$(grep -c '^BUTTON_ALERT_' "$DIR/.env")" -eq 2 ]
  [ -z "$(env_of BUTTON_ALERT_NTFY)" ]
  [ -z "$(env_of BUTTON_ALERT_EMAIL)" ]
  [ "$(ntfy_count)" -eq 0 ]
  install_station --domain radio.example
  assert_output --partial "  Alertes : aucune, hors du journal du système. Sur un téléphone : station config --alert-ntfy https://ntfy.sh"
  # Une relance ne les règle pas : config le fait.
  install_station --domain radio.example --alert-ntfy https://ntfy.sh
  assert_success
  assert_output --partial "Attention : les options --alert-… ne sont pas prises : la station est installée, et station config change ses alertes."
  [ -z "$(env_of BUTTON_ALERT_NTFY)" ]
  [ "$(ntfy_count)" -eq 0 ]
}

@test "au clavier, install propose ntfy, puis demande l'e-mail et son serveur, le mot de passe sans l'afficher" {
  install_at_keyboard <<EOF
Radio Test
radio.example



n

technique@radio.example
smtp.radio.example:587

mot-de-passe-tape
EOF
  assert_success
  assert_output --partial "Alertes sur un téléphone, par ntfy.sh, un service gratuit : un silence à l'antenne, un disque presque plein, une mise à jour annulée ? (o/n) [o] :"
  assert_output --partial "Son mot de passe, qui ne s'affiche pas :"
  [[ $(env_of BUTTON_ALERT_NTFY) =~ ^https://ntfy\.sh/button-[0-9a-f]{24}$ ]]
  [ "$(env_of BUTTON_ALERT_EMAIL)" = technique@radio.example ]
  [ "$(env_of BUTTON_ALERT_SMTP_USER)" = technique@radio.example ]
  [ "$(env_of BUTTON_ALERT_SMTP_PASSWORD)" = mot-de-passe-tape ]
  refute_output --partial mot-de-passe-tape
  # Dans un terminal, le sujet où s'abonner.
  assert_output --partial "  Sur le téléphone : s'abonner, dans l'application ntfy, au sujet $(env_of BUTTON_ALERT_NTFY)."
}

# --- les alertes de la commande ---

@test "une alerte part par ntfy et par e-mail, en haute priorité, et alerts.log la note" {
  alerts_installed
  alert "Mise à jour annulée" "la mise à jour de 0.1.0 à 0.2.0 a échoué pendant le contrôle : la station est revenue en 0.1.0."
  assert_success
  grep -qF -- "logger -t button -p user.warning -- Mise à jour annulée : la mise à jour de 0.1.0 à 0.2.0" "$FAKE_STATE/alerts"
  ntfy_message 1 | grep -qF '"title":"Mise à jour annulée · radio.example","message":"La mise à jour de 0.1.0 à 0.2.0 a échoué pendant le contrôle'
  ntfy_message 1 | grep -qF '"priority":4,"tags":["warning"]}'
  ntfy_message 1 | grep -qF "\\n\\nLa station radio.example, dans $DIR sur "
  [ "$(mail_subject 1)" = "Mise à jour annulée · radio.example" ]
  mail_body 1 | grep -qF "La mise à jour de 0.1.0 à 0.2.0 a échoué pendant le contrôle"
  local line
  line=$(grep -v '^#' "$DIR/alerts.log")
  [ "$(cut -f2-5 <<<"$line")" = "$(printf 'alerte\tMise à jour annulée\tntfy, e-mail\t-')" ]
  station status
  assert_output --partial "Alertes : par ntfy, sur https://ntfy.sh, et par e-mail, à technique@radio.example, direction@radio.example."
  assert_output --regexp "  La dernière de la commande : le [0-9/]+ à [0-9:]+, « Mise à jour annulée », partie par ntfy, e-mail\."
}

@test "une note ne sonne pas : priorité basse, et logger en notice" {
  alerts_installed
  alert "Mise à jour faite" "la station est passée de 0.1.0 à 0.2.0." note
  assert_success
  grep -qF -- "logger -t button -p user.notice -- Mise à jour faite" "$FAKE_STATE/alerts"
  ntfy_message 1 | grep -qF '"priority":2,"tags":["information_source"]}'
  grep -v '^#' "$DIR/alerts.log" | cut -f2 | grep -qx note
}

@test "un canal en panne n'arrête pas l'autre, et status le dit" {
  alerts_installed
  touch "$FAKE_STATE/ntfy-down"
  alert "La sauvegarde hors de la machine a échoué" "le dépôt ne répond pas."
  assert_success
  assert_output --partial "Attention : l'alerte « La sauvegarde hors de la machine a échoué » n'est pas partie par ntfy : curl: (7) Failed to connect"
  [ "$(mail_count)" -eq 1 ]
  station status
  assert_output --partial "partie par e-mail."
  assert_output --partial "Attention : la dernière alerte, « La sauvegarde hors de la machine a échoué », n'est pas partie par ntfy : curl: (7)"
}

@test "sans alerte réglée, le journal du système seul, et alerts.log" {
  installed
  alert "Retour arrière raté" "station rollback a échoué."
  assert_success
  grep -qF "Retour arrière raté : station rollback a échoué." "$FAKE_STATE/alerts"
  [ "$(ntfy_count)" -eq 0 ]
  [ "$(mail_count)" -eq 0 ]
  station status
  assert_output --partial "Alertes : aucune, hors du journal du système."
  assert_output --partial "  Sur un téléphone, ou par e-mail : station config --alert-ntfy https://ntfy.sh, ou --alert-email ADRESSE."
  assert_output --regexp "  La dernière de la commande : le [0-9/]+ à [0-9:]+, « Retour arrière raté »\."
}

@test "une mise à jour faite part en note, par ntfy et par e-mail" {
  alerts_installed
  echo 0.2.0 >"$FAKE_STATE/latest"
  station update
  assert_success
  ntfy_message 1 | grep -qF '"title":"Mise à jour faite · radio.example","message":"La station est passée de 0.1.0 à 0.2.0, et le contrôle passe'
  [ "$(mail_subject 1)" = "Mise à jour faite · radio.example" ]
}

@test "une mise à jour annulée part par ntfy et par e-mail" {
  alerts_installed
  echo 0.2.0 >"$FAKE_STATE/latest"
  touch "$FAKE_STATE/smoke-fails"
  station update
  assert_failure
  assert_output --partial "La mise à jour vers 0.2.0 est annulée."
  ntfy_message 1 | grep -qF '"title":"Mise à jour annulée · radio.example","message":"La mise à jour de 0.1.0 à 0.2.0 a échoué pendant le contrôle'
  [ "$(mail_subject 1)" = "Mise à jour annulée · radio.example" ]
}

@test "une majeure qui attend part une fois par version" {
  local changelog=$BATS_TEST_TMPDIR/CHANGELOG.md
  printf '%s\n' "# Journal" "" "## 1.0.0" "" "**Mise en service.** Une action à faire." >"$changelog"
  RELEASE_CHANGELOG=$changelog make_release 1.0.0 "$FAKE_STATE/releases/v1.0.0"
  alerts_installed
  echo 1.0.0 >"$FAKE_STATE/latest"
  station update
  assert_failure
  assert_output --partial "La version 1.0.0 est une majeure"
  ntfy_message 1 | grep -qF '"title":"Version majeure en attente · radio.example","message":"La 1.0.0 demande une action avant de la prendre'
  ntfy_message 1 | grep -qF '"priority":2'
  [ "$(mail_subject 1)" = "Version majeure en attente · radio.example" ]
  station update
  assert_failure
  [ "$(ntfy_count)" -eq 1 ]
  [ "$(mail_count)" -eq 1 ]
}

@test "une sauvegarde hors de la machine ratée part sur le téléphone" {
  alerts_installed
  station config --backup-remote s3:https://s3.stockage.example/sauvegardes/radio --backup-s3-access-key CLEDACCES \
    --backup-s3-secret-key-file "$TOKEN"
  assert_success
  touch "$FAKE_STATE/restic-backup-fails"
  station backup --remote
  assert_failure
  ntfy_message 1 | grep -qF '"title":"La sauvegarde hors de la machine a échoué · radio.example"'
  [ "$(mail_subject 1)" = "La sauvegarde hors de la machine a échoué · radio.example" ]
}

# --- les aides ---

@test "les en-têtes d'un e-mail : l'ASCII tel quel, le reste en mots encodés coupés entre deux mots" {
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; mime_header "Plain subject"; echo; mime_header "La sauvegarde hors de la machine a échoué · radio.example"' \
    _ "$STATION"
  assert_success
  assert_line --index 0 "Plain subject"
  assert_line --index 1 "=?UTF-8?B?$(printf 'La sauvegarde hors de la machine a échoué ' | base64 -w 0)?="
  assert_line --index 2 " =?UTF-8?B?$(printf '· radio.example' | base64 -w 0)?="
}

@test "le JSON de ntfy garde guillemets, barres et sauts de ligne, et perd les caractères de contrôle" {
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; json_string "$2"' _ "$STATION" $'ligne 1\nligne\t"2" \\ fin\x01\x07'
  assert_success
  assert_output '"ligne 1\nligne\t\"2\" \\ fin"'
}
