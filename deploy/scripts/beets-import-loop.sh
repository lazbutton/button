#!/bin/sh
# Indexe sur place 10-rotation et 20-archives (pas de move Beets).
set -eu
MEDIA="${MEDIA_ROOT:-/media}"
INTERVAL="${BEETS_IMPORT_INTERVAL:-45}"
# L'état de chaque dossier quand la boucle s'est endormie.
SEEN="${TMPDIR:-/tmp}/beets-import-loop"
# Monté à la racine du conteneur. Les tests le prennent dans le dépôt.
PROMOTE="${PROMOTE_INBOX:-/promote-inbox.sh}"

# Beets note ce qu'il a importé (import.incremental) et ne le relit plus. La
# boucle importe par titre (-s) : l'historique retient alors chaque fichier.
# Par dossier, il ne retenait que le dossier, et un titre déposé ensuite, à plat
# dans 10-rotation ou dans une banque, n'entrait jamais dans la bibliothèque.
#
# Une bibliothèque indexée par dossier n'a pas ses fichiers dans l'historique.
# Sans eux, Beets les réimporterait tous : nouveaux identifiants, ReplayGain
# recalculé, et un titre qu'il n'a pas pu taguer sortirait de sa sélection le
# temps de l'import. Avant chaque import, l'historique reprend donc les fichiers
# que la bibliothèque connaît déjà. Perdu ou illisible, il se refait de même.
resume_history() {
  python3 - <<'PY'
import os
import pickle
import sqlite3
from contextlib import closing
from pathlib import Path

beetsdir = Path(os.environ.get("BEETSDIR", ""))
library = beetsdir / "library.db"
state_path = beetsdir / "state.pickle"
known = set()
if library.is_file():
    # Ouverte en écriture, comme par Beets : SQLite y finit d'abord une
    # écriture coupée par l'arrêt du conteneur.
    with closing(sqlite3.connect(library)) as con:
        if con.execute("select 1 from sqlite_master where name = 'items'").fetchone():
            rows = con.execute("select path from items where path is not null")
            known = {(os.fsencode(path),) for (path,) in rows}
try:
    state = pickle.loads(state_path.read_bytes())
    missing = known - state.setdefault("taghistory", set())
except Exception:
    # Comme Beets : un état absent ou illisible vaut un état vide.
    state = {"taghistory": set()}
    missing = known
if missing:
    state["taghistory"] |= missing
    partial = state_path.with_name(".state.partial.pickle")
    partial.write_bytes(pickle.dumps(state))
    partial.replace(state_path)
    print(f"Historique Beets : {len(missing)} fichier(s) déjà indexé(s) repris.")
PY
}

# Un fichier encore en cours de copie ne va pas à Beets : il mesurerait son gain
# sur un morceau, et beet modify écrirait ses tags dans un fichier qui s'écrit
# encore. La boucle retient donc l'état de chaque dossier avant de dormir, noms,
# tailles et dates (keep), et ne donne à Beets, au réveil, qu'un dossier resté
# le même (same). Ce qu'elle écrit elle-même pendant son tour ne compte pas : les
# tags de Beets, et ceux de promote-inbox.sh, qui passe pour cela après l'import.
# Un dépôt est donc indexé au tour qui suit son arrivée, une fois la copie finie.
folder_state() { # same dossier | keep dossier…
  python3 - "$SEEN" "$@" <<'PY'
import hashlib
import os
import sys

seen, mode, *tops = sys.argv[1:]
sys.stdout.reconfigure(errors="backslashreplace")
moved = False
for top in tops:
    top = os.path.normpath(top)
    if not os.path.isdir(top):
        continue
    state = hashlib.sha256()
    latest = (0, "")
    for folder, subfolders, names in os.walk(top):
        # Comme Beets, sans les fichiers ni les dossiers cachés.
        subfolders[:] = sorted(name for name in subfolders if not name.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            path = os.path.join(folder, name)
            try:
                info = os.stat(path)
            except OSError:
                continue
            state.update(os.fsencode(f"{path}\0{info.st_size}\0{info.st_mtime_ns}\0"))
            latest = max(latest, (info.st_mtime_ns, path))
    now = state.hexdigest()
    mark = os.path.join(seen, hashlib.sha256(os.fsencode(top)).hexdigest())
    if mode == "keep":
        os.makedirs(seen, exist_ok=True)
        with open(mark, "w", encoding="ascii") as f:
            f.write(now)
        continue
    try:
        with open(mark, encoding="ascii") as f:
            before = f.read()
    except OSError:
        # Premier tour : rien ne dit encore si une copie est en cours.
        moved = True
        print(f"{top} : premier tour. Beets l'indexera au suivant, s'il n'a pas bougé pendant la pause.")
        continue
    if now != before:
        moved = True
        print(f"{top} a bougé pendant la pause, dernier fichier écrit : {latest[1]}. Beets l'indexera après une pause sans mouvement.")
sys.exit(1 if moved else 0)
PY
}

while true; do
  if [ -f /refresh_volume.py ]; then
    python3 /refresh_volume.py || true
  fi
  if resume_history; then
    if [ -d "$MEDIA/10-rotation" ] && folder_state same "$MEDIA/10-rotation"; then
      beet import -A -q -s "$MEDIA/10-rotation" || true
      beet modify -y grouping=rotation "path:$MEDIA/10-rotation" || true
    fi
    # Chaque dossier de 20-archives est une banque ; son nom devient le grouping.
    for dir in "$MEDIA"/20-archives/*/; do
      [ -d "$dir" ] || continue
      dir=${dir%/}
      ed=$(basename "$dir")
      case "$ed" in .*|_*) continue ;; esac
      folder_state same "$dir" || continue
      beet import -A -q -s "$dir" || true
      beet modify -y grouping="$ed" genre=Archive "path:$dir" || true
    done
  else
    echo "Historique Beets : reprise impossible, l'erreur est au-dessus. Rien n'est indexé à ce tour : sans elle, Beets réimporterait des titres déjà indexés. La boucle réessaie au prochain. Si l'erreur parle de droits, relancer la station (docker compose up -d) : radiotomate-init rend le dossier de Beets au moteur." >&2
  fi
  if [ -f "$PROMOTE" ]; then
    sh "$PROMOTE" || true
  fi
  folder_state keep "$MEDIA/10-rotation" "$MEDIA"/20-archives/*/ ||
    echo "État des dossiers : impossible de le noter dans $SEEN, l'erreur est au-dessus. Beets n'indexe rien tant que la boucle ne peut pas y écrire." >&2
  if [ -f /export_share_roles.py ]; then
    python3 /export_share_roles.py || true
  fi
  sleep "$INTERVAL"
done
