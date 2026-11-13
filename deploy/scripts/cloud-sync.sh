#!/bin/sh
# Le pont des bacs ouverts dans Dropbox (FON-15). Tourne dans le conteneur
# cloud-sync, sur l'image de rclone, seulement avec le profil Compose `cloud`.
# Le guide : docs/exploitation/bacs-dropbox.md.
#
# Toutes les CLOUD_SYNC_INTERVAL secondes, il lit le dossier Bacs/ du dossier
# Dropbox de la station (CLOUD_SYNC_REMOTE, comme dropbox:BUTTON). Chaque
# dossier Bacs/<id>-<titre> ouvre le bac <id> : ses fichiers nouveaux sont
# copiés dans le dossier de ce bac, par son lien de la banque (CART_LINKS), et
# le moteur les prend à son tour suivant. Seul le compte rendu de chaque
# dossier, _compte-rendu.txt, repart vers Dropbox.
#
# - Le bac se trouve par son numéro : renommer le bac ne casse rien.
# - Un fichier n'est copié qu'une fois. CLOUD_SYNC_STATE/copies garde le bac,
#   la date, la taille et le chemin de chaque copie : un son retiré dans la
#   console ne revient pas. Un fichier remplacé dans Dropbox, d'une autre date
#   ou d'une autre taille, entre comme un son nouveau.
# - Seulement les formats du moteur. Un autre fichier est refusé, et le compte
#   rendu dit pourquoi.
# - rclone écrit sous un nom temporaire (.partial), puis renomme : le moteur ne
#   voit jamais un fichier à moitié copié. Rien n'est écrasé : un nom déjà pris
#   dans le bac reçoit un suffixe, -1, -2…
# - Le compte rendu n'est réécrit que si quelque chose y change : sinon,
#   Dropbox le renverrait chaque minute à tous ceux qui partagent le dossier.
#   Un dossier qui n'ouvre plus de bac garde le sien, changé en avis : rien de
#   ce qu'on y dépose n'est copié.
#
# Un seul passage, pour essayer : sh /cloud-sync.sh --once
set -eu
REMOTE="${CLOUD_SYNC_REMOTE:-}"
INTERVAL="${CLOUD_SYNC_INTERVAL:-60}"
MEDIA="${MEDIA_ROOT:-/media}"
# Le dossier des liens vers le dossier de chaque bac. Les scripts de la station,
# le catalogue et le moteur nomment les dossiers de la banque chacun à un seul
# endroit : services/catalog/test_layout.py les compare, et refuse un nom écrit
# ailleurs dans ce fichier.
CART_LINKS=Carts
STATE="${CLOUD_SYNC_STATE:-/state}"
GUIDE="docs/exploitation/bacs-dropbox.md"
REPORT="_compte-rendu.txt"
# Les formats du moteur, sans le point : AUDIO_SUFFIXES, dans
# engine/radiotomate/services/media_bank.py. test_cloud_sync.py vérifie que les
# deux listes restent les mêmes.
FORMATS="aac aif aiff flac m4a mp2 mp3 oga ogg opus wav wave webm wma"
TAB=$(printf '\t')

ONCE=0
case "${1:-}" in
  "") ;;
  --once) ONCE=1 ;;
  *) echo "usage : cloud-sync.sh [--once]" >&2; exit 64 ;;
esac

if [ -z "$REMOTE" ]; then
  echo "CLOUD_SYNC_REMOTE manquant dans .env : le dossier de la station dans Dropbox, comme dropbox:BUTTON. Voir $GUIDE." >&2
  exit 1
fi
case "$REMOTE" in
  *:*) ;;
  *)
    echo "CLOUD_SYNC_REMOTE=$REMOTE : il faut le nom du remote de rclone, deux-points, puis le dossier, comme dropbox:BUTTON. Voir $GUIDE." >&2
    exit 1
    ;;
esac
# dropbox:BUTTON/ comme dropbox:BUTTON.
while [ "${REMOTE%/}" != "$REMOTE" ]; do
  REMOTE=${REMOTE%/}
done
case "$INTERVAL" in
  "" | *[!0-9]* | 0 | 00*)
    echo "CLOUD_SYNC_INTERVAL=$INTERVAL : un nombre de secondes, 60 par défaut." >&2
    exit 1
    ;;
esac
# Le remote vient de la configuration de rclone, montée depuis l'hôte. Un
# remote décrit dans CLOUD_SYNC_REMOTE même, qui commence par deux-points,
# n'en a pas besoin.
NAME=${REMOTE%%:*}
if [ -n "$NAME" ] && ! rclone listremotes 2>/dev/null | grep -Fqx -- "$NAME:"; then
  echo "rclone ne connaît pas le remote $NAME : sa configuration, avec le jeton Dropbox, manque dans le dossier CLOUD_SYNC_CONFIG. Voir $GUIDE, « Relier le compte Dropbox »." >&2
  exit 1
fi
if ! mkdir -p "$STATE/comptes-rendus" || ! touch "$STATE/copies"; then
  echo "$STATE n'est pas inscriptible : la liste des copies y est gardée. Vérifier le volume cloud-sync-state." >&2
  exit 1
fi
# Deux ponts sur la même liste copieraient deux fois le même fichier. flock est
# dans l'image de rclone ; ailleurs, comme sur un Mac pour les tests, le pont
# tourne sans verrou.
if command -v flock >/dev/null 2>&1; then
  exec 9>"$STATE/verrou"
  if ! flock -n 9; then
    echo "Un autre pont tourne déjà sur $STATE : rien à faire." >&2
    exit 1
  fi
fi

WORK=$(mktemp -d)
MEDIA_REAL=$(cd -P "$MEDIA" 2>/dev/null && pwd) || MEDIA_REAL=$MEDIA
FORMAT_LIST=$(printf '%s' "$FORMATS" | sed 's/ /, /g')
child=
trouble=0
closed_reason=
: > "$WORK/annonces"

# docker stop envoie TERM au premier processus du conteneur, ce script. Il le
# passe à rclone, qui efface alors son fichier temporaire, et l'attend.
stop() {
  if [ -n "$child" ]; then
    kill "$child" 2>/dev/null || :
    wait "$child" 2>/dev/null || :
  fi
  exit "$1"
}
trap 'rm -rf "$WORK"' EXIT
trap 'stop 143' TERM
trap 'stop 130' INT

# rclone tourne en arrière-plan, et le script l'attend : sinon, sh ne prend le
# signal d'arrêt qu'à la fin de la copie, et docker tue tout au bout de 10 s,
# en laissant un .partial dans le bac.
rc() {
  rclone "$@" &
  child=$!
  rc_status=0
  wait "$child" || rc_status=$?
  child=
  return "$rc_status"
}

say() { printf '%s\n' "$*"; }

# Ce que le pont sait déjà pendant ce lancement.
known() { grep -Fqx -- "$1" "$WORK/annonces"; }
note() { printf '%s\n' "$1" >> "$WORK/annonces"; }

# Un message qui ne change pas, comme un dossier sauté, n'est dit qu'une fois
# par lancement du pont.
once() { # once <clé> <message>
  if known "$1"; then
    return 0
  fi
  note "$1"
  say "$2"
}

# stat de GNU et de busybox, sinon celui des BSD : les tests tournent aussi sur
# un Mac.
file_stat() { # file_stat <format GNU> <format BSD> <chemin>
  stat -c "$1" "$3" 2>/dev/null || stat -f "$2" "$3"
}

# Le fichier du bac est-il celui de Dropbox, même date, même taille ? rclone
# garde la date de Dropbox.
same_file() { # same_file <chemin>
  [ -f "$1" ] && [ ! -L "$1" ] &&
    [ "$(file_stat %s %z "$1")" = "$size" ] &&
    [ "$(file_stat %Y %m "$1")" = "$stamp" ]
}

# Où copier le fichier : sous son nom, ou sous le premier nom libre,
# chanson-1.mp3, chanson-2.mp3… Le nom a toujours une extension : c'est un
# format du moteur. Échoue si le fichier est déjà dans le bac, sous son nom ou
# un nom à suffixe : copié juste avant un arrêt, ou avant que la liste des
# copies se perde. Pas de doublon.
place() { # place <chemin dans le bac>, puis target
  stem=${1%.*}
  ext=${1##*.}
  for found in "$cart_dir/$1" "$cart_dir/$stem"-*".$ext"; do
    if same_file "$found"; then
      target=${found#"$cart_dir"/}
      return 1
    fi
  done
  target=$1
  n=0
  while [ -e "$cart_dir/$target" ] || [ -L "$cart_dir/$target" ]; do
    n=$((n + 1))
    target="$stem-$n.$ext"
  done
  return 0
}

# Le pont tourne en root. Ce qu'il copie passe au propriétaire du dossier du
# bac, comme les sons envoyés par la console, et chaque dossier du chemin
# aussi, même laissé par une copie ratée : sinon, le moteur ne pourrait pas
# sortir de son sous-dossier un son retiré dans la console, et le son
# reviendrait au tour suivant. -h : un lien n'est pas suivi.
give_to_cart() { # give_to_cart <chemin dans le bac>
  owner=$(file_stat %u:%g %u:%g "$cart_dir")
  part=
  rest=$1
  while :; do
    part=${part:+$part/}${rest%%/*}
    if ! chown -h "$owner" "$cart_dir/$part" 2>/dev/null; then
      say "attention : $cart_rel/$part reste au compte du pont, le moteur pourrait ne pas le retirer."
      return 0
    fi
    case "$rest" in
      */*) rest=${rest#*/} ;;
      *) return 0 ;;
    esac
  done
}

# Le fichier passe au bac avant d'entrer dans la liste des copies : arrêté
# entre les deux, le pont le retrouve au passage suivant, et finit.
copy_file() {
  key="$id$TAB$stamp$TAB$size$TAB$rel"
  if ! place "$rel"; then
    give_to_cart "$target"
    printf '%s\n' "$key" >> "$STATE/copies"
    say "- $rel" >> "$WORK/recus"
    return 0
  fi
  if rc copyto --ignore-existing "$REMOTE/Bacs/$folder/$rel" "$cart_dir/$target" 2> "$WORK/erreur"; then
    give_to_cart "$target"
    printf '%s\n' "$key" >> "$STATE/copies"
    say "copié : Bacs/$folder/$rel -> $cart_rel/$target"
    say "- $rel" >> "$WORK/recus"
  else
    trouble=1
    say "pas copié : Bacs/$folder/$rel ($(tail -n 1 "$WORK/erreur")). Nouvel essai dans $INTERVAL s."
    say "- $rel : la copie a échoué, nouvel essai dans $INTERVAL s." >> "$WORK/attente"
  fi
}

# Le compte rendu, sans sa ligne de date : c'est lui qu'on compare d'un passage
# à l'autre. closed_reason dit pourquoi le dossier n'ouvre plus de bac.
report_body() {
  if [ -n "$closed_reason" ]; then
    say "Ce dossier n'ouvre plus de bac : $closed_reason. Rien de ce qu'on y dépose n'est copié."
    say "Les sons déjà reçus restent dans leur bac. Pour en ajouter d'autres, demander à la station."
    say ""
    say "Ce fichier est écrit par la station."
    return 0
  fi
  say "Ce dossier est ouvert : un son déposé ici est copié dans son bac. S'il est lisible, il passe à l'antenne quand le bac joue, sans que personne l'écoute avant. La station relève ce dossier toutes les $INTERVAL s."
  say ""
  if [ -s "$WORK/recus" ]; then
    say "Reçus ($(wc -l < "$WORK/recus" | tr -d ' ')) :"
    cat "$WORK/recus"
  else
    say "Reçus : aucun pour l'instant."
  fi
  if [ -s "$WORK/refus" ]; then
    say ""
    say "Refusés ($(wc -l < "$WORK/refus" | tr -d ' ')) :"
    cat "$WORK/refus"
  fi
  if [ -s "$WORK/attente" ]; then
    say ""
    say "Pas encore copiés ($(wc -l < "$WORK/attente" | tr -d ' ')) :"
    cat "$WORK/attente"
  fi
  say ""
  say "Formats pris : $FORMAT_LIST."
  say "Retirer un fichier d'ici ne le retire pas du bac : un son se retire dans la console de la station."
  say "Ce fichier est écrit par la station. Il change à chaque nouveauté."
}

# Dans CLOUD_SYNC_STATE/comptes-rendus, par dossier : le dernier compte rendu
# envoyé, et à côté (.corps) le même sans sa ligne de date.
write_report() {
  saved="$STATE/comptes-rendus/$folder"
  report_body > "$WORK/corps"
  if [ -f "$saved" ] && [ -f "$saved.corps" ] && cmp -s "$WORK/corps" "$saved.corps"; then
    # Rien de neuf. Le compte rendu ne repart que s'il a disparu de Dropbox,
    # ou si quelqu'un l'y a changé.
    if [ "$remote_report" = "$(file_stat %s %z "$saved")" ]; then
      return 0
    fi
    sent=$saved
  else
    if [ -f "$saved.corps" ]; then
      before=$saved.corps
    else
      before=/dev/null
    fi
    folder=$folder awk 'FILENAME == ARGV[1] { old[$0] = 1; next }
      !($0 in old) { print "refusé : Bacs/" ENVIRON["folder"] "/" substr($0, 3) }' \
      "$before" "$WORK/refus"
    sent=$saved.nouveau
    {
      say "Compte rendu de la station, pour Bacs/$folder."
      say "Dernier changement : $(date '+%d/%m/%Y à %H:%M')."
      say ""
      cat "$WORK/corps"
    } > "$sent"
  fi
  if rc copyto "$sent" "$REMOTE/Bacs/$folder/$REPORT" 2> "$WORK/erreur"; then
    if [ "$sent" != "$saved" ]; then
      mv "$sent" "$saved"
      cp "$WORK/corps" "$saved.corps"
    fi
    say "compte rendu : Bacs/$folder/$REPORT"
  else
    trouble=1
    rm -f "$saved.nouveau"
    say "compte rendu pas envoyé : Bacs/$folder/$REPORT ($(tail -n 1 "$WORK/erreur")). Nouvel essai dans $INTERVAL s."
  fi
}

# La taille du compte rendu du dossier dans Dropbox, rien s'il n'en a pas.
report_size() {
  path="$folder/$REPORT" awk -F "$TAB" '
    substr($0, length($1) + length($2) + 3) == ENVIRON["path"] { print $2 }' "$WORK/liste"
}

# Le compte rendu du dossier est-il de la station ? Sa première ligne le dit.
station_report() {
  rc cat "$REMOTE/Bacs/$folder/$REPORT" > "$WORK/ancien" 2>/dev/null &&
    head -n 1 "$WORK/ancien" | grep -q '^Compte rendu de la station, pour Bacs/'
}

# Un dossier qui n'ouvre plus de bac, bac supprimé ou dossier renommé sans son
# numéro, garde le compte rendu qui le disait ouvert. Le pont le remplace par
# un avis : rien de ce qu'on y dépose n'est copié. Il ne crée pas de compte
# rendu, et ne remplace que le sien.
close_folder() { # close_folder <raison>
  remote_report=$(report_size)
  if [ -z "$remote_report" ]; then
    return 0
  fi
  if [ ! -f "$STATE/comptes-rendus/$folder.corps" ]; then
    # Un dossier renommé : le pont n'y a rien écrit sous ce nom.
    if known "autre $folder $remote_report"; then
      return 0
    fi
    if ! station_report; then
      note "autre $folder $remote_report"
      return 0
    fi
  fi
  : > "$WORK/recus"
  : > "$WORK/refus"
  : > "$WORK/attente"
  closed_reason=$1
  write_report
}

open_folder() { # open_folder <nom du dossier dans Bacs/>
  folder=$1
  closed_reason=
  case "$folder" in
    .*) return 0 ;;
  esac
  id=
  case "$folder" in
    *-*) id=${folder%%-*} ;;
  esac
  case "$id" in
    "" | *[!0-9]*)
      once "sauté $folder" "sauté : Bacs/$folder n'est pas le nom d'un bac : son numéro, un tiret, puis son titre, comme 12-nouveautes."
      close_folder "son nom ne commence pas par le numéro d'un bac, comme 12-nouveautes"
      return 0
      ;;
  esac
  cart_dir=
  for link in "$MEDIA/$CART_LINKS/$id"-*; do
    if [ -L "$link" ] && [ -d "$link" ] && cart_dir=$(cd -P "$link" && pwd); then
      break
    fi
    cart_dir=
  done
  if [ -z "$cart_dir" ]; then
    once "sauté $folder" "sauté : Bacs/$folder, la station n'a pas de bac $id."
    close_folder "la station n'a pas de bac $id"
    return 0
  fi
  cart_rel=${cart_dir#"$MEDIA_REAL"/}

  # Pour chaque fichier du dossier : recu, déjà copié ; copie, à copier ;
  # refus, un format que le moteur ne prend pas. Puis sa date, sa taille et son
  # chemin. Les fichiers cachés, comme pour le moteur, et le compte rendu ne
  # comptent pas : de lui, seule la taille sert.
  dir="$folder/" id=$id formats=$FORMATS report=$REPORT awk -F "$TAB" -v OFS="$TAB" '
    BEGIN {
      n = split(ENVIRON["formats"], list, " ")
      for (i = 1; i <= n; i++) ok[list[i]] = 1
      dir = ENVIRON["dir"]
    }
    FILENAME == ARGV[1] {
      if ($1 == ENVIRON["id"]) done[substr($0, length($1) + 2)] = 1
      next
    }
    {
      path = substr($0, length($1) + length($2) + 3)
      if (index(path, dir) != 1) next
      rel = substr(path, length(dir) + 1)
      if (rel == "" || rel ~ /\/$/) next
      if (rel == ENVIRON["report"]) { print "rapport", $2; next }
      if (("/" rel) ~ /\/\./) next
      name = rel
      sub(/.*\//, "", name)
      ext = ""
      if (index(name, ".")) { ext = tolower(name); sub(/.*\./, "", ext) }
      entry = $1 OFS $2 OFS rel
      if (!(ext in ok)) print "refus", entry
      else if (entry in done) print "recu", entry
      else print "copie", entry
    }' "$STATE/copies" "$WORK/liste" > "$WORK/fichiers"

  : > "$WORK/recus"
  : > "$WORK/refus"
  : > "$WORK/attente"
  remote_report=
  while IFS= read -r line <&4; do
    kind=${line%%"$TAB"*}
    rest=${line#*"$TAB"}
    if [ "$kind" = rapport ]; then
      remote_report=$rest
      continue
    fi
    stamp=${rest%%"$TAB"*}
    rest=${rest#*"$TAB"}
    size=${rest%%"$TAB"*}
    rel=${rest#*"$TAB"}
    case "$kind" in
      recu) say "- $rel" >> "$WORK/recus" ;;
      copie) copy_file ;;
      refus)
        name=${rel##*/}
        case "$name" in
          *.*) say "- $rel : format .${name##*.}, que la station ne prend pas." >> "$WORK/refus" ;;
          *) say "- $rel : sans extension, la station ne sait pas si c'est un son." >> "$WORK/refus" ;;
        esac
        ;;
    esac
  done 4< "$WORK/fichiers"
  write_report
}

sync_once() {
  trouble=0
  if [ ! -d "$MEDIA/$CART_LINKS" ]; then
    trouble=1
    once "sans $CART_LINKS" "$MEDIA/$CART_LINKS manque : la banque n'est pas montée, ou le moteur ne l'a pas encore préparée. Nouvel essai toutes les $INTERVAL s."
    return 0
  fi
  if ! rc lsf -R --format tsp --time-format unix --separator "$TAB" "$REMOTE/Bacs" > "$WORK/brute" 2> "$WORK/erreur"; then
    trouble=1
    if [ "$rc_status" = 3 ]; then
      once "sans Bacs" "$REMOTE/Bacs n'existe pas : crée le dossier Bacs dans le dossier Dropbox de la station, puis un dossier par bac à ouvrir. Voir $GUIDE."
    else
      say "Dropbox ne répond pas : $REMOTE/Bacs ne se lit pas ($(tail -n 1 "$WORK/erreur")). Nouvel essai dans $INTERVAL s."
    fi
    return 0
  fi
  # Trié par chemin : rclone liste dans le désordre, et le compte rendu ne doit
  # pas changer sans raison.
  LC_ALL=C sort -t "$TAB" -k 3 "$WORK/brute" > "$WORK/liste"
  awk -F "$TAB" '{
      path = substr($0, length($1) + length($2) + 3)
      cut = index(path, "/")
      if (cut > 1) print substr(path, 1, cut - 1)
    }' "$WORK/liste" | LC_ALL=C sort -u > "$WORK/dossiers"
  awk -F "$TAB" '{
      path = substr($0, length($1) + length($2) + 3)
      if (path != "" && index(path, "/") == 0 && substr(path, 1, 1) != ".") print path
    }' "$WORK/liste" > "$WORK/racine"
  while IFS= read -r stray <&3; do
    once "racine $stray" "pas copié : Bacs/$stray est posé dans Bacs/ même. Un son se dépose dans le dossier d'un bac."
  done 3< "$WORK/racine"
  while IFS= read -r folder_name <&3; do
    open_folder "$folder_name"
  done 3< "$WORK/dossiers"
}

say "Pont Dropbox : $REMOTE/Bacs vers les bacs de la banque, toutes les $INTERVAL s."
while :; do
  sync_once
  if [ "$ONCE" = 1 ]; then
    exit "$trouble"
  fi
  sleep "$INTERVAL" &
  child=$!
  wait "$child" || :
  child=
done
