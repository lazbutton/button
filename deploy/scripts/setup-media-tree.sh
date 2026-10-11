#!/bin/sh
# Arbre unique de la banque BUTTON. Idempotent.
# Les banques d'archives (dossiers de 20-archives) se créent depuis la console.
set -eu
ROOT="${1:-${MEDIA_ROOT:-/media}}"
mkdir -p \
  "$ROOT/00-inbox/rotation" \
  "$ROOT/00-inbox/archives" \
  "$ROOT/00-inbox/habillage/jingles" \
  "$ROOT/00-inbox/habillage/ids" \
  "$ROOT/00-inbox/habillage/pubs" \
  "$ROOT/00-inbox/habillage/beds" \
  "$ROOT/00-inbox/habillage/stings" \
  "$ROOT/00-inbox/habillage/sfx" \
  "$ROOT/00-inbox/emissions/_modele/entiere" \
  "$ROOT/00-inbox/emissions/_modele/podcasts" \
  "$ROOT/10-rotation" \
  "$ROOT/20-archives" \
  "$ROOT/30-habillage/jingles" \
  "$ROOT/30-habillage/ids" \
  "$ROOT/30-habillage/pubs" \
  "$ROOT/30-habillage/beds" \
  "$ROOT/30-habillage/stings" \
  "$ROOT/30-habillage/sfx" \
  "$ROOT/40-emissions/_modele/entiere" \
  "$ROOT/40-emissions/_modele/podcasts" \
  "$ROOT/50-carts" \
  "$ROOT/Carts" \
  "$ROOT/90-trash"
printf "Médiathèque BUTTON : %s\n" "$ROOT"
find "$ROOT" -type d | sort
