#!/bin/sh
# Promotion vers la banque indexée par beets-import-loop.sh.
# Tourne dans button-radiotomate-dropbox-1 (ffmpeg + beets), à chaque tour
# de la boucle, ou à la main :
#   docker exec button-radiotomate-dropbox-1 sh /promote-inbox.sh [--dry-run]
#
# - 00-inbox/rotation        -> 10-rotation
# - 00-inbox/archives/<banque> -> 20-archives/<banque>, pour chaque dossier de 20-archives
# - 10-rotation et 20-archives : un fichier déjà là est tagué sur place.
#   wav / aiff deviennent du flac dans le même dossier. Un fichier n'est
#   réécrit que si son nom lui donne un tag qu'il n'a pas.
# - Sans BROADCAST_CODEC : MP3 / FLAC / OGG / M4A déplacés tels quels ;
#   WAV / AIFF convertis en FLAC ; l'original part dans 00-inbox/_sources.
# - BROADCAST_CODEC=mp3 ou opus (petit disque) : tout fichier accepté est réencodé
#   (MP3 320 ou Opus 192) et l'original est effacé. Pas de masters sur le volume.
# Rejouable : une cible déjà présente est ignorée.
# Un fichier modifié pendant le passage attend le suivant : voir settled.
set -eu
MEDIA="${MEDIA_ROOT:-/media}"
SOURCES="$MEDIA/00-inbox/_sources"
BROADCAST_CODEC="${BROADCAST_CODEC:-}"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
case "$BROADCAST_CODEC" in
  ""|mp3|opus) ;;
  *) echo "BROADCAST_CODEC inconnu : $BROADCAST_CODEC" >&2; exit 1 ;;
esac

run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi; }

tag_of() { # tag_of <file> <artist|title>
  tag=$(ffprobe -v error -show_entries "format_tags=$2" -of default=nw=1:nk=1 "$1" 2>/dev/null | head -n1)
  # Opus et Ogg gardent leurs tags dans le flux audio, pas dans le fichier. Le
  # premier flux audio seulement : la pochette, un flux image, a parfois son title.
  if [ -z "$tag" ]; then
    tag=$(ffprobe -v error -select_streams a:0 -show_entries "stream_tags=$2" -of default=nw=1:nk=1 "$1" 2>/dev/null | head -n1)
  fi
  printf '%s\n' "$tag"
}

# Les tags à écrire : ceux du fichier, complétés par son nom. Vrai si le nom
# n'ajoute rien, par exemple un fichier sans artiste dont le nom n'a pas de
# « Artiste - Titre » : le réécrire ne changerait que sa date, à chaque tour.
adds_nothing() { # après have_artist, have_title, artist et title
  meta_artist=${have_artist:-$artist}
  meta_title=${have_title:-$title}
  [ "$meta_artist" = "$have_artist" ] && [ "$meta_title" = "$have_title" ]
}

# encode <source> <cible> <arguments de ffmpeg…> : ffmpeg écrit dans un
# fichier caché à côté de la cible, qui ne prend sa place qu'entier. Si ffmpeg
# échoue, le fichier est sauté : rien n'est déplacé, et le passage continue.
encode() {
  enc_src=$1
  enc_target=$2
  shift 2
  enc_name=$(basename "$enc_target")
  enc_partial="$(dirname "$enc_target")/.${enc_name%.*}.partial.${enc_name##*.}"
  if [ "$DRY" = 1 ]; then
    echo "+ ffmpeg -v error -y -i $enc_src $* $enc_partial"
    return 0
  fi
  if ffmpeg -v error -y -i "$enc_src" "$@" "$enc_partial"; then
    mv "$enc_partial" "$enc_target"
    return
  fi
  rm -f "$enc_partial"
  echo "illisible : $(basename "$enc_src"), dans $(dirname "$enc_src"). ffmpeg ne l'a pas lu, son erreur est au-dessus. Le fichier reste où il est, et le passage continue sans lui : le remplacer par une copie entière, ou le retirer. Sinon, il sera retenté à chaque tour." >&2
  failed=$((failed+1))
  return 1
}

# Un fichier encore en cours de copie n'est pas touché : retagué ou converti,
# il garderait sa moitié, et la suite de la copie serait perdue. Le catalogue
# copie un envoi dans l'inbox sous son nom final, et le dossier partagé écrit sur
# place. Avant le premier fichier à écrire ou à déplacer, le passage attend
# PROMOTE_SETTLE secondes, une fois ; un fichier modifié depuis le début du
# passage attend le suivant. L'attente se fait dans le passage, et non d'un
# passage à l'autre : la boucle Beets indexe un dossier resté immobile pendant
# sa pause, et un fichier repoussé d'un tour y entrerait sans ses tags.
SETTLE="${PROMOTE_SETTLE:-5}"
started=$(mktemp "${TMPDIR:-/tmp}/promote-inbox.XXXXXX")
trap 'rm -f "$started"' EXIT
waited=0
settled() { # settled <fichier>
  if [ "$waited" = 0 ]; then
    sleep "$SETTLE"
    waited=1
  fi
  if [ -f "$1" ] && [ -z "$(find "$1" -newer "$started")" ]; then
    return 0
  fi
  echo "en cours de copie : $(basename "$1"). Repris au prochain passage, une fois la copie finie."
  moving=$((moving+1))
  return 1
}

promoted=0
skipped=0
failed=0
moving=0

promote_dir() {
  inbox=$1
  dest=$2
  if [ ! -d "$inbox" ]; then
    echo "rien à promouvoir : $inbox absent"
    return 0
  fi
  mkdir -p "$dest" "$SOURCES"
  for src in "$inbox"/*; do
    [ -f "$src" ] || continue
    name=$(basename "$src")
    stem=${name%.*}
    ext=$(printf '%s' "${name##*.}" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    case "$stem" in
      *" - "*) artist=${stem%% - *}; title=${stem#* - } ;;
      *)       artist=""; title=$stem ;;
    esac
    if [ -n "$BROADCAST_CODEC" ]; then
      case "$ext" in
        mp3|flac|ogg|opus|m4a|wav|aif|aiff) ;;
        *) echo "ignoré (format) : $name"; skipped=$((skipped+1)); continue ;;
      esac
      if [ "$BROADCAST_CODEC" = "opus" ]; then
        target="$dest/$stem.opus"
        codec_args="-c:a libopus -b:a 192k"
      else
        target="$dest/$stem.mp3"
        codec_args="-c:a libmp3lame -b:a 320k"
      fi
      if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
      settled "$src" || continue
      # Sans guillemets exprès : codec_args donne plusieurs arguments à ffmpeg.
      # shellcheck disable=SC2086
      encode "$src" "$target" -map 0:a $codec_args \
        -metadata artist="$artist" -metadata title="$title" || continue
      run rm -f "$src"
      echo "promu : $name -> $dest/$(basename "$target") (${BROADCAST_CODEC}, original effacé)"
      promoted=$((promoted+1))
      continue
    fi
    case "$ext" in
      mp3|flac|ogg|opus|m4a)
        target="$dest/$stem.$ext"
        if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
        settled "$src" || continue
        have_artist=$(tag_of "$src" artist)
        have_title=$(tag_of "$src" title)
        if adds_nothing; then
          run mv "$src" "$target"
        else
          encode "$src" "$target" -map 0:a -c copy \
            -metadata artist="$meta_artist" -metadata title="$meta_title" || continue
          run mv "$src" "$SOURCES/$name"
        fi
        echo "promu : $name -> $dest/$(basename "$target")"
        promoted=$((promoted+1))
        ;;
      wav|aif|aiff)
        target="$dest/$stem.flac"
        if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
        settled "$src" || continue
        encode "$src" "$target" -map 0:a -c:a flac -compression_level 5 \
          -metadata artist="$artist" -metadata title="$title" || continue
        run mv "$src" "$SOURCES/$name"
        echo "promu : $name -> $dest/$(basename "$target") (original dans _sources)"
        promoted=$((promoted+1))
        ;;
      *)
        echo "ignoré (format) : $name"
        skipped=$((skipped+1))
        ;;
    esac
  done
}

# Fichier déjà dans la banque : on le laisse dans son dossier.
# wav / aiff -> flac à côté, puis l'original est retiré.
# Les autres formats reçoivent artiste et titre s'il en manque un.
tag_in_place() {
  dest=$1
  [ -d "$dest" ] || return 0
  for src in "$dest"/*; do
    [ -f "$src" ] || continue
    name=$(basename "$src")
    case "$name" in .*) continue ;; esac
    stem=${name%.*}
    ext=$(printf '%s' "${name##*.}" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    case "$stem" in
      *" - "*) artist=${stem%% - *}; title=${stem#* - } ;;
      *)       artist=""; title=$stem ;;
    esac
    case "$ext" in
      wav|aif|aiff)
        target="$dest/$stem.flac"
        if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
        settled "$src" || continue
        encode "$src" "$target" -map 0:a -c:a flac -compression_level 5 \
          -metadata artist="$artist" -metadata title="$title" || continue
        run rm -f "$src"
        echo "sur place : $name -> $dest/$(basename "$target")"
        promoted=$((promoted+1))
        ;;
      mp3|flac|ogg|opus|m4a)
        have_artist=$(tag_of "$src" artist)
        have_title=$(tag_of "$src" title)
        adds_nothing && continue
        settled "$src" || continue
        encode "$src" "$src" -map 0:a -c copy \
          -metadata artist="$meta_artist" -metadata title="$meta_title" || continue
        echo "sur place : $name"
        promoted=$((promoted+1))
        ;;
      *)
        ;;
    esac
  done
}

promote_dir "$MEDIA/00-inbox/rotation" "$MEDIA/10-rotation"
# Une banque d'archives = un dossier de 20-archives (sauf ceux en . ou _).
for bank in "$MEDIA"/20-archives/*/; do
  [ -d "$bank" ] || continue
  ed=$(basename "$bank")
  case "$ed" in .*|_*) continue ;; esac
  promote_dir "$MEDIA/00-inbox/archives/$ed" "$MEDIA/20-archives/$ed"
  tag_in_place "$MEDIA/20-archives/$ed"
done
tag_in_place "$MEDIA/10-rotation"
echo "promotion : $promoted promu(s), $skipped ignoré(s), $moving en cours de copie, $failed illisible(s). Index Beets au prochain tour (${BEETS_IMPORT_INTERVAL:-45} s)."
# Un fichier sauté se voit aussi au code de sortie, pour qui lance le script à
# la main. La boucle Beets passe outre et continue.
[ "$failed" = 0 ]
