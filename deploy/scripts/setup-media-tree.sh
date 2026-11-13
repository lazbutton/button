#!/bin/sh
# Arbre unique de la banque BUTTON. Idempotent.
# Les collections, les dossiers de COLLECTIONS, se créent depuis la console.
#
# MEDIA_OWNER (uid:gid), posé par radiotomate-init et le catalogue, qui tournent
# en root : la banque est au moteur, rtuser, comme RT_DATA. La boucle Beets et
# l'interface, en rtuser, y écrivent ; un dossier créé ici par root leur serait
# fermé. Ce qui n'est pas à lui lui est donné, à chaque démarrage, sauf ce que
# le dossier partagé tient : sa vue, VOLUME, et les dossiers ouverts au groupe
# deposer (DEPOSER_GID de share/apply_share.py). lost+found reste au disque.
set -eu
ROOT="${1:-${MEDIA_ROOT:-/media}}"
DEPOSER_GID=2050

# Les dossiers de la banque. Les scripts de la station, le catalogue et le
# moteur les nomment chacun à un seul endroit : services/catalog/test_layout.py
# les compare, et refuse un nom écrit ailleurs dans ce fichier.
INBOX=00-inbox
ROTATION=10-rotation
COLLECTIONS=20-archives
HABILLAGE=30-habillage
EMISSIONS=40-emissions
CARTS=50-carts
CART_LINKS=Carts
TRASH=90-trash
VOLUME=.volume
HABILLAGE_TYPES="jingles ids pubs beds stings sfx"
EMISSION_SLOTS="entiere podcasts"
# L'inbox range un dépôt d'après sa destination.
INBOX_ROTATION=$INBOX/rotation
INBOX_COLLECTIONS=$INBOX/archives
INBOX_HABILLAGE=$INBOX/habillage
INBOX_EMISSIONS=$INBOX/emissions
# Le modèle d'une émission : son dossier, avec ses deux sous-dossiers.
EMISSION_MODEL=_modele

# Un seul mkdir, pour tout l'arbre : un dossier qu'il ne peut pas créer
# n'empêche pas les autres.
set -- "$ROOT/$INBOX_ROTATION" "$ROOT/$INBOX_COLLECTIONS"
for kind in $HABILLAGE_TYPES; do
  set -- "$@" "$ROOT/$INBOX_HABILLAGE/$kind"
done
for slot in $EMISSION_SLOTS; do
  set -- "$@" "$ROOT/$INBOX_EMISSIONS/$EMISSION_MODEL/$slot"
done
set -- "$@" "$ROOT/$ROTATION" "$ROOT/$COLLECTIONS"
for kind in $HABILLAGE_TYPES; do
  set -- "$@" "$ROOT/$HABILLAGE/$kind"
done
for slot in $EMISSION_SLOTS; do
  set -- "$@" "$ROOT/$EMISSIONS/$EMISSION_MODEL/$slot"
done
mkdir -p "$@" "$ROOT/$CARTS" "$ROOT/$CART_LINKS" "$ROOT/$TRASH"
if [ -n "${MEDIA_OWNER:-}" ]; then
  owner_uid=${MEDIA_OWNER%%:*}
  owner_gid=${MEDIA_OWNER#*:}
  # -xdev : un disque monté dans la banque n'est pas à elle. -h : un lien vers
  # le dossier d'un bac change lui-même, pas le son qu'il vise.
  if ! find "$ROOT" -xdev \( -path "$ROOT/$VOLUME" -o -path "$ROOT/lost+found" \) -prune \
    -o ! -gid "$DEPOSER_GID" \( ! -uid "$owner_uid" -o ! -gid "$owner_gid" \) \
    -exec chown -h "$owner_uid:$owner_gid" {} +; then
    # Un disque qui refuse chown (exFAT, NFS en root_squash) : la boucle Beets
    # le dira à chaque tour. Le démarrage continue.
    echo "Attention : la banque $ROOT n'a pas pu être donnée en entier à $MEDIA_OWNER, l'utilisateur du moteur. La boucle Beets et la console ne pourront pas écrire dans ce qui reste à un autre compte. Sur l'hôte, depuis le dossier de la station : chown -R $MEDIA_OWNER media (ou le chemin de BUTTON_MEDIA), puis docker compose up -d." >&2
  fi
fi
printf "Médiathèque BUTTON : %s\n" "$ROOT"
find "$ROOT" -type d | sort
