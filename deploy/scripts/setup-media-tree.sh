#!/bin/sh
# Arbre unique de la banque BUTTON. Idempotent.
set -eu
ROOT="${1:-${MEDIA_ROOT:-/media}}"
mkdir -p \
  "$ROOT/00-inbox/rotation" \
  "$ROOT/00-inbox/archives/ntf1" \
  "$ROOT/00-inbox/archives/ntf2" \
  "$ROOT/00-inbox/archives/ntf3" \
  "$ROOT/00-inbox/habillage/jingles" \
  "$ROOT/00-inbox/habillage/ids" \
  "$ROOT/00-inbox/habillage/pubs" \
  "$ROOT/00-inbox/habillage/beds" \
  "$ROOT/00-inbox/habillage/stings" \
  "$ROOT/00-inbox/habillage/sfx" \
  "$ROOT/00-inbox/emissions/_modele/entiere" \
  "$ROOT/00-inbox/emissions/_modele/podcasts" \
  "$ROOT/10-rotation" \
  "$ROOT/20-archives/ntf1" \
  "$ROOT/20-archives/ntf2" \
  "$ROOT/20-archives/ntf3" \
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
