#!/bin/sh
# Promotion vers la banque indexée par beets-import-loop.sh.
# Tourne dans button-radiotomate-dropbox-1 (ffmpeg + beets), à chaque tour
# de la boucle, ou à la main :
#   docker exec button-radiotomate-dropbox-1 sh /promote-inbox.sh [--dry-run]
#
# - 00-inbox/rotation        -> 10-rotation
# - 00-inbox/archives/<banque> -> 20-archives/<banque>, pour chaque dossier de 20-archives
# - 10-rotation et 20-archives : un fichier déjà là est tagué sur place.
#   wav / aiff deviennent du flac dans le même dossier. Un mp3 ou un flac
#   déjà tagué n'est pas réécrit.
# - Sans BROADCAST_CODEC : MP3 / FLAC / OGG / M4A déplacés tels quels ;
#   WAV / AIFF convertis en FLAC ; l'original part dans 00-inbox/_sources.
# - BROADCAST_CODEC=mp3 ou opus (petit disque) : tout fichier accepté est réencodé
#   (MP3 320 ou Opus 192) et l'original est effacé. Pas de masters sur le volume.
# Rejouable : une cible déjà présente est ignorée.
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
  ffprobe -v error -show_entries "format_tags=$2" -of default=nw=1:nk=1 "$1" 2>/dev/null | head -n1
}

promoted=0
skipped=0

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
    ext=$(printf '%s' "${name##*.}" | tr 'A-Z' 'a-z')
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
      partial="$dest/.$stem.partial.${target##*.}"
      if [ "$DRY" = 1 ]; then
        echo "+ ffmpeg -v error -y -i $src -map 0:a $codec_args -metadata artist=$artist -metadata title=$title $partial"
      elif ! ffmpeg -v error -y -i "$src" -map 0:a $codec_args \
        -metadata artist="$artist" -metadata title="$title" "$partial"; then
        rm -f "$partial"
        exit 1
      else
        mv "$partial" "$target"
        rm -f "$src"
      fi
      echo "promu : $name -> $dest/$(basename "$target") (${BROADCAST_CODEC}, original effacé)"
      promoted=$((promoted+1))
      continue
    fi
    case "$ext" in
      mp3|flac|ogg|opus|m4a)
        target="$dest/$stem.$ext"
        if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
        have_artist=$(tag_of "$src" artist)
        have_title=$(tag_of "$src" title)
        if [ -n "$have_artist" ] && [ -n "$have_title" ]; then
          run mv "$src" "$target"
        else
          run ffmpeg -v error -y -i "$src" -map 0:a -c copy \
            -metadata artist="${have_artist:-$artist}" -metadata title="${have_title:-$title}" \
            "$target"
          run mv "$src" "$SOURCES/$name"
        fi
        echo "promu : $name -> $dest/$(basename "$target")"
        promoted=$((promoted+1))
        ;;
      wav|aif|aiff)
        target="$dest/$stem.flac"
        if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
        run ffmpeg -v error -y -i "$src" -map 0:a -c:a flac -compression_level 5 \
          -metadata artist="$artist" -metadata title="$title" "$target"
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
    ext=$(printf '%s' "${name##*.}" | tr 'A-Z' 'a-z')
    case "$stem" in
      *" - "*) artist=${stem%% - *}; title=${stem#* - } ;;
      *)       artist=""; title=$stem ;;
    esac
    case "$ext" in
      wav|aif|aiff)
        target="$dest/$stem.flac"
        if [ -e "$target" ]; then echo "déjà là : $name"; skipped=$((skipped+1)); continue; fi
        partial="$dest/.$stem.partial.flac"
        if [ "$DRY" = 1 ]; then
          echo "+ ffmpeg -v error -y -i $src -map 0:a -c:a flac -compression_level 5 -metadata artist=$artist -metadata title=$title $partial"
        elif ! ffmpeg -v error -y -i "$src" -map 0:a -c:a flac -compression_level 5 \
          -metadata artist="$artist" -metadata title="$title" "$partial"; then
          rm -f "$partial"
          exit 1
        else
          mv "$partial" "$target"
          rm -f "$src"
        fi
        echo "sur place : $name -> $dest/$(basename "$target")"
        promoted=$((promoted+1))
        ;;
      mp3|flac|ogg|opus|m4a)
        have_artist=$(tag_of "$src" artist)
        have_title=$(tag_of "$src" title)
        if [ -n "$have_artist" ] && [ -n "$have_title" ]; then
          continue
        fi
        partial="$dest/.$stem.retag.$ext"
        meta_artist=${have_artist:-$artist}
        meta_title=${have_title:-$title}
        if [ "$DRY" = 1 ]; then
          echo "+ ffmpeg -v error -y -i $src -map 0:a -c copy -metadata artist=$meta_artist -metadata title=$meta_title $partial"
        elif ! ffmpeg -v error -y -i "$src" -map 0:a -c copy \
          -metadata artist="$meta_artist" -metadata title="$meta_title" "$partial"; then
          rm -f "$partial"
          exit 1
        else
          mv "$partial" "$src"
        fi
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
echo "promotion : $promoted promu(s), $skipped ignoré(s). Index Beets au prochain tour (${BEETS_IMPORT_INTERVAL:-45} s)."
