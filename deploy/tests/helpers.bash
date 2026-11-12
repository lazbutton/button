# Les aides des tests de deploy/station : une machine jouée par de faux outils,
# dans le dossier temporaire du test. Voir station.bats.

TESTS=$(cd "$BATS_TEST_DIRNAME" && pwd)
DEPLOY=$(cd "$TESTS/.." && pwd)
STATION=$DEPLOY/station

# Les fichiers joints à une version, faits des fichiers du dépôt, comme
# scripts/version.py station, dont les tests disent le reste. smoke.sh n'y fait
# que noter son appel : ses tests sont dans services/catalog/test_smoke.py.
# Une autre commande station, ou un autre CHANGELOG.md : leur chemin, dans
# RELEASE_STATION et RELEASE_CHANGELOG. D'autres fichiers, par-dessus ceux
# du dépôt : un dossier, RELEASE_OVERLAY, avec les mêmes chemins.
make_release() { # version, dossier
  local files script=${RELEASE_STATION:-$STATION}
  files=$(mktemp -d)
  mkdir -p "$files/scripts" "$2"
  cp "$DEPLOY/compose.yml" "$DEPLOY/Caddyfile" "$DEPLOY/.env.example" "$files/"
  cp "$script" "$files/station"
  cp "${RELEASE_CHANGELOG:-$DEPLOY/../CHANGELOG.md}" "$files/CHANGELOG.md"
  cp "$DEPLOY"/scripts/* "$files/scripts/"
  [[ -z ${RELEASE_OVERLAY:-} ]] || cp -R "$RELEASE_OVERLAY/." "$files/"
  cat >"$files/scripts/smoke.sh" <<'EOF'
#!/usr/bin/env bash
echo "smoke $* SMOKE_WAIT=${SMOKE_WAIT:-} dans $PWD" >>"$FAKE_STATE/log"
# Un contrôle qui dure, tant que $FAKE_STATE/smoke-hangs est là.
while [[ -e $FAKE_STATE/smoke-hangs ]]; do sleep 0.1; done
# Un échec, une fois : $FAKE_STATE/smoke-fails.
if [[ -e $FAKE_STATE/smoke-fails ]]; then
  rm "$FAKE_STATE/smoke-fails"
  exit 1
fi
EOF
  chmod 755 "$files/scripts/smoke.sh"
  echo "$1" >"$files/VERSION"
  # Un nom de fichier par mot : aucun n'a d'espace.
  # shellcheck disable=SC2046
  (cd "$files" && tar -czf "$2/station.tar.gz" $(find . -type f | sed 's|^\./||' | sort))
  cp "$script" "$2/station"
  (cd "$2" && sha256sum station station.tar.gz >SHA256SUMS)
  rm -rf "$files"
}

# Une Debian 12 x86-64 neuve, avec Docker, un domaine qui mène à elle, et deux
# versions publiées : 0.1.0, la plus haute, et 0.2.0, à venir.
setup_machine() {
  ROOT=$BATS_TEST_TMPDIR/root
  DIR=$ROOT/opt/button
  export STATION_ROOT=$ROOT
  export FAKE_STATE=$BATS_TEST_TMPDIR/state
  export FAKE_DOCKER=$TESTS/docker
  mkdir -p "$ROOT/etc" "$ROOT/usr/share/zoneinfo/Europe" "$ROOT/usr/share/zoneinfo/America" \
    "$FAKE_STATE/bin" "$FAKE_STATE/releases"
  touch "$ROOT/usr/share/zoneinfo/Europe/Paris" "$ROOT/usr/share/zoneinfo/America/Montreal"
  system debian 12 bookworm
  ln -s "$FAKE_DOCKER" "$FAKE_STATE/bin/docker"
  cp -R "$BATS_FILE_TMPDIR/releases/." "$FAKE_STATE/releases/"
  echo 0.1.0 >"$FAKE_STATE/latest"
  echo 192.0.2.10 >"$FAKE_STATE/dns-a"
  echo 192.0.2.10 >"$FAKE_STATE/here"
  : >"$FAKE_STATE/log"
  export PATH="$FAKE_STATE/bin:$TESTS/fakes:$PATH"
}

system() { # id, version, nom de code
  printf 'PRETTY_NAME="%s %s"\nID=%s\nVERSION_ID="%s"\nVERSION_CODENAME=%s\n' "$1" "$2" "$1" "$2" "$3" \
    >"$ROOT/etc/os-release"
}

# Sans terminal : les options répondent, rien ne s'affiche du mot de passe.
install_station() {
  run bash "$STATION" install "$@"
}

# Au clavier, dans un terminal : l'entrée standard donne les réponses.
install_at_keyboard() {
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; shift; interactive() { [[ -z $assume_yes ]]; }; terminal() { true; }; main install "$@"' \
    _ "$STATION" "$@"
}

# Dans un terminal, sans question : le mot de passe s'affiche.
install_in_terminal() {
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; shift; terminal() { true; }; main install "$@"' _ "$STATION" "$@"
}

# Sous une ACL par défaut, comme celle de /opt sur les runners de GitHub : le
# umask n'y compte plus. Ici, umask ne fait plus rien, et le umask donné joue
# l'ACL : 022 ouvre en lecture, 000 en écriture.
install_under_acl() { # umask, options
  local mask=$1
  shift
  # shellcheck disable=SC2016
  run bash -c 'umask "$1"; umask() { :; }; source "$2"; shift 2; main install "$@"' _ "$mask" "$STATION" "$@"
}

# La valeur d'une variable du .env de la station.
env_of() {
  grep -E "^$1=" "$DIR/.env" | tail -n 1 | cut -d= -f2-
}

logged() {
  grep -qF -- "$1" "$FAKE_STATE/log"
}

# Chaque fichier du dossier de la station, avec ses droits et sa somme.
snapshot() {
  (cd "$DIR" && find . -type f | sort | while read -r file; do
    printf '%s %s %s\n' "$(stat -c %a "$file")" "$(sha256sum "$file" | cut -d' ' -f1)" "$file"
  done)
}

# Une commande de station, sans terminal.
station() {
  run bash "$STATION" "$@"
}

# Une commande de station au clavier, dans un terminal : l'entrée standard
# donne les réponses.
station_at_keyboard() {
  # shellcheck disable=SC2016
  run bash -c 'source "$1"; shift; interactive() { [[ -z $assume_yes ]]; }; terminal() { true; }; main "$@"' \
    _ "$STATION" "$@"
}

# Une station installée, sans terminal, et un journal vide.
installed() { # options d'install
  install_station --domain radio.example "$@"
  assert_success
  : >"$FAKE_STATE/log"
}

# Une autre machine neuve, à la place de la première.
new_machine() {
  rm -rf "$ROOT" "$FAKE_STATE"
  setup_machine
}

# Les dossiers et fichiers d'une restauration, préparés ou mis de côté.
leftovers() { # motif
  find "$DIR" -name "$1" 2>/dev/null
}
