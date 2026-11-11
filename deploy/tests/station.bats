#!/usr/bin/env bats
# Les tests de deploy/station, la commande d'exploitation d'une station : ses
# vérifications, ses questions, les fichiers qu'elle écrit, et sa relance.
# Une machine jouée par de faux outils, fakes/ et docker, dans un dossier
# temporaire : ni conteneur, ni réseau, ni root. Depuis la racine du dépôt :
#   ./scripts/verifier.sh deploy

bats_require_minimum_version 1.5.0

setup_file() {
  load helpers
  make_release 0.1.0 "$BATS_FILE_TMPDIR/releases/v0.1.0"
  make_release 0.2.0 "$BATS_FILE_TMPDIR/releases/v0.2.0"
  make_release main "$BATS_FILE_TMPDIR/main"
}

setup() {
  load helpers
  bats_load_library bats-support
  bats_load_library bats-assert
  setup_machine
}

# --- Une installation neuve ---

@test "une installation neuve pose la version, écrit le dossier, démarre et contrôle la station" {
  install_station --domain radio.example --email admin@radio.example
  assert_success
  assert_output --partial "Machine : debian 12 (bookworm), x86-64."
  assert_output --partial "Version : 0.1.0, la plus haute publiée."
  assert_output --partial "Domaine : radio.example mène à cette machine (192.0.2.10)."
  assert_output --partial "La station tourne : l'antenne joue."
  assert_output --partial "Console : https://radio.example"

  # Les fichiers de la version, vérifiés par leur somme.
  logged "curl --disable -fsSL --retry 3 --max-time 120 -o"
  logged "https://github.com/lazbutton/button/releases/download/v0.1.0/station.tar.gz"
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  cmp "$DEPLOY/compose.yml" "$DIR/compose.yml"
  cmp "$DEPLOY/Caddyfile" "$DIR/Caddyfile"
  [ -x "$DIR/station" ]
  [ -x "$DIR/scripts/smoke.sh" ]
  [ -f "$DIR/scripts/init-radiotomate.sh" ]

  # .env, en droits 600.
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
  [ "$(env_of COMPOSE_PROFILES)" = vps ]
  [ "$(env_of DOMAIN)" = radio.example ]
  [ "$(env_of ACME_EMAIL)" = admin@radio.example ]
  [ "$(env_of BIND_ADDRESS)" = 127.0.0.1 ]
  [ "$(env_of TZ)" = Europe/Paris ]
  [ "$(env_of RT_ADMIN_USER)" = admin ]
  [ "$(env_of BUTTON_UPDATES)" = auto ]
  run ! grep -q '^CADDY_TLS=' "$DIR/.env"
  # Quatre secrets de machine, de 48 caractères, tous différents.
  local key secrets=""
  for key in ICECAST_SOURCE_PASSWORD ICECAST_ADMIN_PASSWORD RT_NOWPLAYING_SECRET MEILI_MASTER_KEY; do
    [[ $(env_of "$key") =~ ^[0-9a-f]{48}$ ]]
    secrets="$secrets$(env_of "$key")"$'\n'
  done
  [ "$(sort -u <<<"$secrets" | grep -c .)" -eq 4 ]
  [[ $(env_of RT_ADMIN_PASSWORD) =~ ^[A-Za-z0-9_-]{24}$ ]]

  # Les dossiers de données, et la commande sur la machine.
  for key in data/radiotomate data/nowplaying data/meilisearch data/caddy media; do
    [ -d "$DIR/$key" ]
  done
  [ "$(readlink "$ROOT/usr/local/bin/station")" = "$DIR/station" ]

  # Démarrer, puis contrôler par HTTPS.
  logged "docker compose pull (dans $DIR)"
  logged "docker compose up -d (dans $DIR)"
  logged "curl --disable -sS -o /dev/null --max-time 10 https://radio.example/"
  logged "smoke https://radio.example https://radio.example/radio.mp3 SMOKE_WAIT=300 dans $DIR"
}

@test "le nom et les adresses publiques vont dans les réglages Station, sans rien écraser" {
  install_station --domain radio.example --name "Radio d'Ici"
  assert_success
  assert_output --partial "Réglages Station : nom et adresses publiques posés."
  grep -qxF -- "-T -e BUTTON_NAME=Radio d'Ici -e BUTTON_DOMAIN=radio.example -e BUTTON_HARBOR_PORT=6800 -e BUTTON_MOUNT=radio.mp3 radiotomate-interface python3 -" \
    "$FAKE_STATE/settings"
  grep -qF "insert or ignore into settings" "$FAKE_STATE/settings.py"
  grep -qF "select 1 from settings where key like 'station.%'" "$FAKE_STATE/settings.py"
}

@test "l'environnement du shell ne prend pas la place de .env" {
  # sudo garde TZ, par exemple : docker compose le préférerait à celui de .env.
  TZ=Asia/Tokyo DOMAIN=autre.example install_station --domain radio.example
  assert_success
  logged "environnement : TZ=absent DOMAIN=absent"
}

@test "le mot de passe admin s'affiche une fois, dans un terminal, puis quitte .env" {
  install_in_terminal --domain radio.example
  assert_success
  local password
  password=$(grep '^RT_ADMIN_PASSWORD=' "$FAKE_STATE/env-at-first-up" | cut -d= -f2)
  [ "${#password}" -eq 24 ]
  assert_output --partial "Mot de passe : $password"
  assert_output --partial "Affiché cette fois seulement"
  grep -qx 'RT_ADMIN_PASSWORD=' "$DIR/.env"
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  # radiotomate-init repasse sans lui.
  [ "$(grep -c 'docker compose up -d' "$FAKE_STATE/log")" -eq 2 ]

  : >"$FAKE_STATE/log"
  install_in_terminal
  assert_success
  refute_output --partial "$password"
  refute_output --partial "Mot de passe"
  run ! logged "radiotomate-interface python3"
}

@test "sans terminal, le mot de passe admin ne s'affiche pas, et reste dans .env" {
  install_station --domain radio.example
  assert_success
  local password
  password=$(env_of RT_ADMIN_PASSWORD)
  [ -n "$password" ]
  refute_output --partial "$password"
  assert_output --partial "Mot de passe admin : pas affiché, la sortie n'est pas un terminal."

  install_in_terminal
  assert_success
  assert_output --partial "Mot de passe : $password"
  [ -z "$(env_of RT_ADMIN_PASSWORD)" ]
}

@test "--github-token-file passe le jeton à docker login, par l'entrée standard" {
  printf 'jeton-de-test\n' >"$BATS_TEST_TMPDIR/jeton"
  install_station --domain radio.example --github-token-file "$BATS_TEST_TMPDIR/jeton"
  assert_success
  grep -qxF "login ghcr.io --username lazbutton --password-stdin jeton=jeton-de-test" "$FAKE_STATE/login"
  run ! logged "jeton-de-test"
  logged "docker compose pull"
}

@test "un jeton illisible arrête tout avant le démarrage" {
  install_station --domain radio.example --github-token-file "$BATS_TEST_TMPDIR/absent"
  assert_failure
  assert_output --partial "Jeton illisible"
  run ! logged "docker compose pull"
}

@test "--tls internal : un certificat de Caddy, sans vérifier le domaine" {
  install_station --domain radio.example --tls internal
  assert_success
  [ "$(env_of CADDY_TLS)" = internal ]
  run ! logged "nslookup"
  logged "--cacert $DIR/data/caddy/pki/authorities/local/root.crt --resolve radio.example:443:127.0.0.1 https://radio.example/"
  logged "smoke http://127.0.0.1:30126 http://127.0.0.1:18000/radio.mp3"
}

@test "--version installe une version publiée, pas la plus haute" {
  install_station --domain radio.example --version 0.2.0
  assert_success
  assert_output --partial "Version : 0.2.0."
  run ! logged "releases/latest"
  [ "$(cat "$DIR/VERSION")" = 0.2.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.2.0 ]
}

@test "--from installe depuis une archive, sans GitHub, main compris" {
  install_station --domain radio.example --from "$BATS_FILE_TMPDIR/main/station.tar.gz"
  assert_success
  assert_output --partial "Version : main, depuis"
  run ! logged "github.com"
  [ "$(env_of BUTTON_VERSION)" = main ]
  [ "$(cat "$DIR/VERSION")" = main ]
}

# --- Sous une ACL par défaut ---

@test "une ACL par défaut qui ouvre en lecture : .env naît quand même en 600" {
  install_under_acl 022 --domain radio.example
  assert_success
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  [[ $(env_of RT_ADMIN_PASSWORD) =~ ^[A-Za-z0-9_-]{24}$ ]]
  # Elle reste : le umask habituel ouvre autant.
  refute_output --partial "Droits :"
  run ! logged "setfacl"
}

@test "une ACL par défaut qui ouvre en écriture ne passe pas au dossier de la station" {
  ln -s "$TESTS/setfacl" "$FAKE_STATE/bin/setfacl"
  install_under_acl 000 --domain radio.example
  assert_success
  assert_output --partial "Droits : une ACL par défaut sur $ROOT passe outre le umask."
  # Le dossier de la station, et celui qui manquait au-dessus.
  logged "setfacl -k -b $DIR"
  logged "setfacl -k -b $ROOT/opt"
  [ "$(stat -c %a "$DIR")" = 755 ]
  [ "$(stat -c %a "$ROOT/opt")" = 755 ]
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
}

@test "sans setfacl, une ACL par défaut qui ouvre en écriture arrête tout, avant d'écrire" {
  install_under_acl 000 --domain radio.example
  assert_failure
  assert_output --partial "Une ACL par défaut sur $ROOT passe outre le umask : le dossier de la station y naîtrait en 777"
  assert_output --partial "apt-get install acl"
  [ ! -e "$ROOT/opt" ]
  run ! logged "docker"
}

# --- Les vérifications ---

@test "sans root, rien ne se fait" {
  echo 1000 >"$FAKE_STATE/uid"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "station install demande les droits root."
  [ ! -e "$DIR" ]
}

@test "un système autre que Debian 12 ou 13, ou Ubuntu 24.04, est refusé" {
  local release
  for release in "debian 11 bullseye" "ubuntu 22.04 jammy" "fedora 41 x"; do
    # Les mots, un à un.
    # shellcheck disable=SC2086
    system $release
    install_station --domain radio.example
    assert_failure
    assert_output --partial "Système non pris en charge : ${release% *}."
  done
  for release in "debian 13 trixie" "ubuntu 24.04 noble"; do
    # shellcheck disable=SC2086
    system $release
    install_station --domain radio.example --tls internal
    assert_success
  done
}

@test "un processeur autre que x86-64 est refusé" {
  echo aarch64 >"$FAKE_STATE/arch"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Processeur aarch64 : les images de BUTTON ne sont construites que pour x86-64"
}

@test "sans Docker, --yes l'installe depuis son dépôt" {
  rm "$FAKE_STATE/bin/docker"
  system ubuntu 24.04 noble
  install_station --domain radio.example --yes
  assert_success
  assert_output --partial "Docker : installation depuis download.docker.com."
  logged "curl --disable -fsSL https://download.docker.com/linux/ubuntu/gpg -o $ROOT/etc/apt/keyrings/docker.asc"
  logged "apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
  logged "systemctl enable --now docker"
  grep -qx "URIs: https://download.docker.com/linux/ubuntu" "$ROOT/etc/apt/sources.list.d/docker.sources"
  grep -qx "Suites: noble" "$ROOT/etc/apt/sources.list.d/docker.sources"
  grep -qx "Signed-By: /etc/apt/keyrings/docker.asc" "$ROOT/etc/apt/sources.list.d/docker.sources"
  [ -f "$DIR/.env" ]
}

@test "sans Docker ni terminal, sans --yes, rien ne s'installe" {
  rm "$FAKE_STATE/bin/docker"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Relancer avec --yes pour l'installer"
  run ! logged "apt-get"
}

@test "sans Docker, au clavier, installer Docker se demande" {
  rm "$FAKE_STATE/bin/docker"
  install_at_keyboard --domain radio.example <<<"n"
  assert_failure
  assert_output --partial "Docker n'est pas installé. L'installer depuis le dépôt de Docker ? (o/n) [o] :"
  assert_output --partial "Rien n'est installé : une station a besoin de Docker."
  run ! logged "apt-get"
}

@test "Docker sans Compose v2, ou qui ne répond pas, est refusé" {
  touch "$FAKE_STATE/no-compose"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Docker est là, mais pas Compose v2 (docker compose)."

  rm "$FAKE_STATE/no-compose"
  touch "$FAKE_STATE/docker-down"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Docker ne répond pas."
}

@test "un port pris arrête l'installation, et le programme qui le tient est nommé" {
  printf 'tcp 80 apache2\nudp 443 openvpn\n' >"$FAKE_STATE/ports"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "80 (tcp) : apache2"
  assert_output --partial "443 (udp) : openvpn"
  [ ! -e "$DIR" ]
}

@test "la place manque : une installation neuve s'arrête" {
  echo 5242880 >"$FAKE_STATE/free-kb"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Place libre insuffisante"
  assert_output --partial "Il en faut 10 Go au moins"
  [ ! -e "$DIR" ]
}

@test "un domaine sans adresse arrête tout avant le certificat" {
  : >"$FAKE_STATE/dns-a"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Le domaine radio.example ne mène à aucune adresse."
  run ! logged "caddy respond"
  [ ! -e "$DIR" ]
}

@test "un domaine qui mène ailleurs arrête tout avant le certificat" {
  printf '192.0.2.10\n198.51.100.7\n' >"$FAKE_STATE/dns-a"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Le domaine radio.example mène à 198.51.100.7, qui ne répond pas comme cette machine sur le port 80."
  logged "docker run -d --rm --name button-verification-domaine -p 80:80 caddy:2.11-alpine caddy respond --listen :80 --body"
  logged "docker rm -f button-verification-domaine"
  [ ! -e "$DIR" ]
}

@test "chaque adresse du domaine compte, IPv6 comprise" {
  echo 2001:db8::10 >"$FAKE_STATE/dns-aaaa"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "mène à 2001:db8::10"
  logged "--resolve radio.example:80:[2001:db8::10] http://radio.example/.well-known/button-"

  echo 2001:db8::10 >>"$FAKE_STATE/here"
  install_station --domain radio.example
  assert_success
  assert_output --partial "Domaine : radio.example mène à cette machine (192.0.2.10 2001:db8::10)."
}

@test "--no-domain-check passe la vérification, en le disant" {
  : >"$FAKE_STATE/dns-a"
  install_station --domain radio.example --no-domain-check
  assert_success
  assert_output --partial "Attention : le domaine n'est pas vérifié (--no-domain-check)."
  run ! logged "nslookup"
}

@test "une archive qui ne correspond pas à sa somme n'est pas installée" {
  sed -i 's/^[0-9a-f]*  station.tar.gz$/0000  station.tar.gz/' "$FAKE_STATE/releases/v0.1.0/SHA256SUMS"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "station.tar.gz de la version 0.1.0 ne correspond pas à sa somme"
  [ ! -e "$DIR" ]
}

@test "sans version publiée, ou sans fichiers de station, l'installation le dit" {
  : >"$FAKE_STATE/latest"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "Aucune version publiée de BUTTON"

  echo 0.0.9 >"$FAKE_STATE/latest"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "La version 0.0.9 n'a pas de fichier station.tar.gz sur GitHub"

  touch "$FAKE_STATE/github-down"
  install_station --domain radio.example
  assert_failure
  assert_output --partial "GitHub répond 503 pour la dernière version de lazbutton/button."
  [ ! -e "$DIR" ]
}

# --- Les questions ---

@test "au clavier, chaque réponse a sa question et sa valeur par défaut" {
  install_at_keyboard <<'EOF'
Radio Test
Radio.Example

America/Montreal

n
EOF
  assert_success
  assert_output --partial "Quelques questions. Entrée garde la valeur entre crochets."
  assert_output --partial "Nom de la station [BUTTON] :"
  assert_output --partial "Domaine, qui pointe déjà sur cette machine :"
  assert_output --partial "Fuseau de la station [Europe/Paris] :"
  assert_output --partial "Identifiant du compte admin [admin] :"
  assert_output --partial "Mises à jour automatiques, dès que station update saura se lancer seule ? (o/n) [o] :"
  [ "$(env_of DOMAIN)" = radio.example ]
  [ -z "$(env_of ACME_EMAIL)" ]
  [ "$(env_of TZ)" = America/Montreal ]
  [ "$(env_of RT_ADMIN_USER)" = admin ]
  [ "$(env_of BUTTON_UPDATES)" = manual ]
  grep -qF -- "-e BUTTON_NAME=Radio Test " "$FAKE_STATE/settings"
}

@test "au clavier, une réponse refusée se redemande, en disant pourquoi" {
  install_at_keyboard <<'EOF'

https://radio.example
radio.example
pas-un-e-mail

Mars/Olympus

un admin
studio
peut-être
o
EOF
  assert_success
  assert_output --partial "« https://radio.example » n'est pas un nom de domaine."
  assert_output --partial "« pas-un-e-mail » n'est pas un e-mail."
  assert_output --partial "« Mars/Olympus » n'est pas un fuseau connu de cette machine"
  assert_output --partial "« un admin » : un identifiant de 32 caractères au plus"
  assert_output --partial "Répondre o ou n."
  [ "$(env_of DOMAIN)" = radio.example ]
  [ "$(env_of TZ)" = Europe/Paris ]
  [ "$(env_of RT_ADMIN_USER)" = studio ]
  [ "$(env_of BUTTON_UPDATES)" = auto ]
  grep -qF -- "-e BUTTON_NAME=BUTTON " "$FAKE_STATE/settings"
}

@test "les options répondent : aucune question ne se pose" {
  install_at_keyboard --name "Radio Test" --domain radio.example --email "" --timezone UTC --admin studio --updates manual <<<""
  assert_failure
  assert_output --partial "« UTC » n'est pas un fuseau connu de cette machine"

  touch "$ROOT/usr/share/zoneinfo/UTC"
  install_at_keyboard --name "Radio Test" --domain radio.example --email "" --timezone UTC --admin studio --updates manual <<<""
  assert_success
  refute_output --partial "Quelques questions"
  refute_output --partial "Nom de la station"
  refute_output --partial "Domaine, qui pointe"
  refute_output --partial "Mises à jour automatiques,"
  [ "$(env_of TZ)" = UTC ]
  [ "$(env_of RT_ADMIN_USER)" = studio ]
  [ "$(env_of BUTTON_UPDATES)" = manual ]
}

@test "sans terminal, le domaine se donne en option" {
  install_station
  assert_failure
  assert_output --partial "--domain manque : sans terminal, ou avec --yes, rien ne se demande."
  [ ! -e "$DIR" ]
}

@test "une option fausse s'arrête tout de suite, avec son usage" {
  install_station --domain radio.example --email pas-un-e-mail
  [ "$status" -eq 2 ]
  assert_output --partial "« pas-un-e-mail » n'est pas un e-mail."

  install_station --domain radio.example --tls autre
  [ "$status" -eq 2 ]
  assert_output --partial "--tls vaut internal, ou acme"

  install_station --domain radio.example --dir opt/button
  [ "$status" -eq 2 ]

  install_station --domain radio.example --version 0.1
  [ "$status" -eq 2 ]
  assert_output --partial "une version s'écrit X.Y.Z"

  install_station --domain radio.example --inconnue x
  [ "$status" -eq 2 ]
  assert_output --partial "Option inconnue : --inconnue."
  [ ! -e "$DIR" ]
}

@test "station sans commande donne l'aide ; une commande inconnue est refusée" {
  run bash "$STATION"
  assert_success
  assert_output --partial "Usage : station COMMANDE [options]"
  assert_output --partial "  install        installer la station, ou la réparer"

  run bash "$STATION" install --help
  assert_success
  assert_output --partial "Usage : station install [options]"

  run bash "$STATION" detruire
  [ "$status" -eq 2 ]
  assert_output --partial "Commande inconnue : detruire."
}

# --- La relance ---

@test "relancer install ne change rien" {
  install_in_terminal --domain radio.example
  assert_success
  local before
  before=$(snapshot)
  : >"$FAKE_STATE/log"

  install_in_terminal --domain radio.example
  assert_success
  assert_output --partial "Réponses : celles de $DIR/.env, déjà là."
  assert_output --partial "Ports : la station tourne déjà, avec son Caddy."
  assert_output --partial "Domaine : pas vérifié, la station a déjà son certificat."
  assert_output --partial "Dossier : $DIR, rien à réparer."
  [ "$(snapshot)" = "$before" ]
  run ! logged "releases/latest"
  run ! logged "nslookup"
  run ! logged "ss -H -l -n -p"
  # Ses images restent : une relance ne tire pas une caddy:2.11-alpine plus
  # récente, qui recréerait Caddy.
  run ! logged "docker compose pull"
  logged "docker compose up -d"
  logged "https://github.com/lazbutton/button/releases/download/v0.1.0/station.tar.gz"
  logged "smoke https://radio.example https://radio.example/radio.mp3"
}

@test "relancer répare ce qui manque, et garde à côté ce qui a changé" {
  install_in_terminal --domain radio.example
  local icecast meili
  icecast=$(env_of ICECAST_SOURCE_PASSWORD)
  meili=$(env_of MEILI_MASTER_KEY)
  rm "$DIR/scripts/smoke.sh"
  echo "# changé à la main" >>"$DIR/compose.yml"
  sed -i '/^MEILI_MASTER_KEY=/d' "$DIR/.env"
  chmod 644 "$DIR/.env"

  install_in_terminal
  assert_success
  assert_output --partial "Remis à la version : compose.yml."
  assert_output --partial "Ajouté à .env : MEILI_MASTER_KEY."
  [ -x "$DIR/scripts/smoke.sh" ]
  cmp "$DEPLOY/compose.yml" "$DIR/compose.yml"
  grep -q "# changé à la main" "$DIR"/compose.yml.local-*
  [ "$(stat -c %a "$DIR/.env")" = 600 ]
  [ "$(env_of ICECAST_SOURCE_PASSWORD)" = "$icecast" ]
  [[ $(env_of MEILI_MASTER_KEY) =~ ^[0-9a-f]{48}$ ]]
  [ "$(env_of MEILI_MASTER_KEY)" != "$meili" ]
  grep -q "^# Ajouté par station install, le " "$DIR/.env"
}

@test "relancer garde .env, même contre une option" {
  install_station --domain radio.example --tls internal
  install_station --domain autre.example --timezone America/Montreal --tls acme
  assert_success
  assert_output --partial "--domain autre.example n'est pas pris : la station a déjà DOMAIN=radio.example"
  assert_output --partial "--timezone America/Montreal n'est pas pris : la station a déjà TZ=Europe/Paris"
  assert_output --partial "--tls acme n'est pas pris : la station a déjà CADDY_TLS=internal"
  [ "$(env_of DOMAIN)" = radio.example ]
  [ "$(env_of TZ)" = Europe/Paris ]
}

@test "relancer garde la version de la station, même quand une plus haute paraît" {
  install_station --domain radio.example
  echo 0.2.0 >"$FAKE_STATE/latest"
  : >"$FAKE_STATE/log"
  install_station --version 0.2.0
  assert_success
  assert_output --partial "--version 0.2.0 n'est pas prise : la station est en 0.1.0"
  run ! logged "releases/latest"
  logged "releases/download/v0.1.0/station.tar.gz"
  [ "$(cat "$DIR/VERSION")" = 0.1.0 ]
  [ "$(env_of BUTTON_VERSION)" = 0.1.0 ]
}

@test "la commande posée sur la machine répare sa propre station" {
  install_station --domain radio.example --dir "$ROOT/srv/radio"
  assert_success
  [ "$(readlink "$ROOT/usr/local/bin/station")" = "$ROOT/srv/radio/station" ]
  run bash "$ROOT/usr/local/bin/station" install
  assert_success
  assert_output --partial "installation de la station, dans $ROOT/srv/radio."
  assert_output --partial "Dossier : $ROOT/srv/radio, rien à réparer."

  # Le script téléchargé, relancé sans --dir, suit la commande posée.
  install_station
  assert_success
  assert_output --partial "installation de la station, dans $ROOT/srv/radio."
  [ ! -e "$DIR" ]
}

@test "relancer sur une station à l'étroit répare quand même" {
  install_station --domain radio.example
  echo 5242880 >"$FAKE_STATE/free-kb"
  install_station
  assert_success
  assert_output --partial "Attention : peu de place libre"
}

@test "une installation interrompue reprend où elle en était, mot de passe compris" {
  touch "$FAKE_STATE/pull-fails"
  install_station --domain radio.example --name "Radio Test"
  assert_failure
  assert_output --partial "Les images de la version 0.1.0 ne se tirent pas."
  assert_output --partial "relancer avec --github-token-file"
  local password
  password=$(env_of RT_ADMIN_PASSWORD)
  [ -n "$password" ]

  rm "$FAKE_STATE/pull-fails"
  install_in_terminal --name "Radio Test"
  assert_success
  assert_output --partial "Mot de passe : $password"
  grep -qF -- "-e BUTTON_NAME=Radio Test " "$FAKE_STATE/settings"
}

@test "une station qui tourne sans son Caddy se répare : ses propres ports ne la bloquent pas" {
  install_station --domain radio.example
  rm "$FAKE_STATE/caddy-running"
  touch "$FAKE_STATE/engine-running"
  echo "tcp 6800 docker-proxy" >"$FAKE_STATE/ports"
  install_station
  assert_success
  assert_output --partial "Ports : la station tourne déjà, sans son Caddy."
  # Sans Caddy, la station n'a plus de certificat sûr : le domaine se vérifie.
  logged "nslookup"
}

@test "relancée après une interruption, une installation neuve demande toujours sa place" {
  touch "$FAKE_STATE/pull-fails"
  install_station --domain radio.example
  assert_failure
  rm "$FAKE_STATE/pull-fails"
  echo 5242880 >"$FAKE_STATE/free-kb"
  install_station
  assert_failure
  assert_output --partial "Place libre insuffisante"
}
