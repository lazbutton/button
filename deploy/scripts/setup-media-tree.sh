#!/bin/sh
# Arbre unique de la banque BUTTON. Idempotent.
# Les banques d'archives (dossiers de 20-archives) se créent depuis la console.
#
# MEDIA_OWNER (uid:gid), posé par radiotomate-init et le catalogue, qui tournent
# en root : la banque est au moteur, rtuser, comme RT_DATA. La boucle Beets et
# l'interface, en rtuser, y écrivent ; un dossier créé ici par root leur serait
# fermé. Ce qui n'est pas à lui lui est donné, à chaque démarrage, sauf ce que
# le dossier partagé tient : .volume, et les dossiers ouverts au groupe deposer
# (DEPOSER_GID de share/apply_share.py). lost+found reste au disque.
set -eu
ROOT="${1:-${MEDIA_ROOT:-/media}}"
DEPOSER_GID=2050
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
if [ -n "${MEDIA_OWNER:-}" ]; then
  owner_uid=${MEDIA_OWNER%%:*}
  owner_gid=${MEDIA_OWNER#*:}
  # -xdev : un disque monté dans la banque n'est pas à elle. -h : un lien de
  # Carts/ change lui-même, pas le son qu'il vise.
  if ! find "$ROOT" -xdev \( -path "$ROOT/.volume" -o -path "$ROOT/lost+found" \) -prune \
    -o ! -gid "$DEPOSER_GID" \( ! -uid "$owner_uid" -o ! -gid "$owner_gid" \) \
    -exec chown -h "$owner_uid:$owner_gid" {} +; then
    # Un disque qui refuse chown (exFAT, NFS en root_squash) : la boucle Beets
    # le dira à chaque tour. Le démarrage continue.
    echo "Attention : la banque $ROOT n'a pas pu être donnée en entier à $MEDIA_OWNER, l'utilisateur du moteur. La boucle Beets et la console ne pourront pas écrire dans ce qui reste à un autre compte. Sur l'hôte, depuis le dossier de la station : chown -R $MEDIA_OWNER media (ou le chemin de BUTTON_MEDIA), puis docker compose up -d." >&2
  fi
fi
printf "Médiathèque BUTTON : %s\n" "$ROOT"
find "$ROOT" -type d | sort
