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
# Avant chaque import, la bibliothèque et l'historique suivent le disque :
# - Un fichier disparu de 10-rotation ou de 20-archives quitte la bibliothèque
#   (beet remove, qui ne touche pas au disque), sans attendre que son dossier se
#   calme : un titre déplacé d'une banque à l'autre serait sinon sauté comme
#   doublon de son ancienne entrée, et retenu ainsi dans l'historique. Seul
#   « n'existe pas » compte, pas une erreur de droits ou de disque. Et sans son
#   dossier de tête, rien n'est retiré : une banque non montée ne vide pas la
#   bibliothèque.
# - L'historique reprend les fichiers que la bibliothèque connaît. Une
#   bibliothèque indexée par dossier n'y a pas les siens, et Beets les
#   réimporterait tous : nouveaux identifiants, ReplayGain recalculé, et un titre
#   qu'il n'a pas pu taguer sortirait de sa sélection le temps de l'import.
#   Perdu ou illisible, il se refait de même.
# - Il oublie un fichier disparu que la bibliothèque ne connaît plus : remis au
#   même chemin, le fichier est réindexé, sous un nouvel identifiant.
follow_disk() {
  python3 - "$MEDIA" <<'PY'
import os
import pickle
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

media = os.fsencode(sys.argv[1])
beetsdir = Path(os.environ.get("BEETSDIR", ""))
library = beetsdir / "library.db"
state_path = beetsdir / "state.pickle"
tops = tuple(
    os.path.join(media, top, b"")
    for top in (b"10-rotation", b"20-archives")
    if os.path.isdir(os.path.join(media, top))
)


def gone(path):
    """Le fichier n'existe plus, dans un dossier de tête qui, lui, existe."""
    if not isinstance(path, bytes) or not path.startswith(tops):
        return False
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return False


def items():
    if not library.is_file():
        return {}
    # Ouverte en écriture, comme par Beets : SQLite y finit d'abord une
    # écriture coupée par l'arrêt du conteneur.
    with closing(sqlite3.connect(library)) as con:
        if not con.execute("select 1 from sqlite_master where name = 'items'").fetchone():
            return {}
        rows = con.execute("select id, path from items where path is not null")
        return {item_id: os.fsencode(path) for item_id, path in rows}


removed = [item_id for item_id, path in items().items() if gone(path)]
# Par paquets : au-delà d'un millier, SQLite refuse la requête.
for start in range(0, len(removed), 200):
    query = []
    for item_id in removed[start : start + 200]:
        query += [f"id:{item_id}", ","]
    if subprocess.run(["beet", "remove", "-f", *query[:-1]]).returncode:
        print(
            "Bibliothèque Beets : retrait impossible, l'erreur est au-dessus. Les titres"
            " disparus y restent, et l'auto-DJ peut encore les choisir. La boucle"
            " réessaie au prochain tour.",
            file=sys.stderr,
        )
        break
after = items()
left = [item_id for item_id in removed if item_id not in after]
if left:
    print(f"Bibliothèque Beets : {len(left)} titre(s) retiré(s), leur fichier a disparu.")

known = {(path,) for path in after.values()}
try:
    state = pickle.loads(state_path.read_bytes())
    history = state.setdefault("taghistory", set())
    missing = known - history
except Exception:
    # Comme Beets : un état absent ou illisible vaut un état vide.
    state = {"taghistory": set()}
    history = state["taghistory"]
    missing = known
forgotten = {
    entry
    for entry in history
    if isinstance(entry, tuple) and entry and entry not in known and all(gone(path) for path in entry)
}
if missing or forgotten:
    state["taghistory"] = (history | missing) - forgotten
    partial = state_path.with_name(".state.partial.pickle")
    partial.write_bytes(pickle.dumps(state))
    partial.replace(state_path)
if missing:
    print(f"Historique Beets : {len(missing)} fichier(s) déjà indexé(s) repris.")
if forgotten:
    print(f"Historique Beets : {len(forgotten)} fichier(s) disparu(s) oublié(s). Remis au même chemin, ils seront réindexés.")
PY
}

# Un fichier changé sur place, tag corrigé ou fichier remplacé, est relu (beet
# update), dans un dossier resté le même pendant la pause, comme pour l'import :
# Beets lirait sinon ses tags et sa durée sur un morceau. beet update ne fait que
# lire. Il ne relit qu'un fichier plus récent que la date qu'il a notée, et 2.5.1
# ne note pas la date de ce qu'il relit : il relirait le fichier à chaque tour,
# et ne relirait jamais une copie qui garde sa date d'origine, plus ancienne
# (Finder, cp -p). La boucle compare donc les dates elle-même, à la seconde comme
# Beets. Pour un fichier changé, elle met à 0 la date de la bibliothèque, puis y
# écrit celle qu'elle a vue, une fois Beets passé.
# - -e : les champs que la boucle pose d'après le dossier ne se relisent pas.
#   Relu, le regroupement sortirait le titre de sa sélection jusqu'au beet modify
#   qui suit, et à chaque tour pour un fichier que promote-inbox.sh réécrit.
# - -d : devant un fichier disparu entre-temps, Beets retire le titre, et élague
#   les dossiers vidés jusqu'à la racine de sa bibliothèque, la banque : une
#   banque vidée de son dernier titre disparaîtrait, et 20-archives avec elle.
#   Avec une racine hors de la banque, il n'élague rien.
# - -M : rien ne se déplace.
# Le gain ReplayGain se relit aussi dans les tags. Un fichier remplacé qui n'en a
# pas n'en a plus : le moteur le mesure avant de l'envoyer à l'antenne.
reread() { # dossier champ… (ceux que la boucle pose)
  python3 - "$@" <<'PY'
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

folder, *kept = sys.argv[1:]
beetsdir = os.environ.get("BEETSDIR", "")
library = Path(beetsdir) / "library.db"
top = os.path.join(os.fsencode(os.path.normpath(folder)), b"")
if not beetsdir or not library.is_file():
    sys.exit(0)
with closing(sqlite3.connect(library)) as con:
    if not con.execute("select 1 from sqlite_master where name = 'items'").fetchone():
        sys.exit(0)
    changed = {}
    for item_id, path, noted in con.execute("select id, path, mtime from items where path is not null"):
        path = os.fsencode(path)
        if not path.startswith(top):
            continue
        try:
            seen = int(os.stat(path).st_mtime)
        except OSError:
            continue
        if seen != int(noted or 0):
            changed[item_id] = seen
    if not changed:
        sys.exit(0)
    with con:
        con.executemany("update items set mtime = 0 where id = ?", [(item_id,) for item_id in changed])
    excluded = [arg for field in kept for arg in ("-e", field)]
    if subprocess.run(["beet", "-d", beetsdir, "update", "-M", *excluded, f"path:{folder}"]).returncode:
        print(
            f"{folder} : relecture impossible, l'erreur de Beets est au-dessus. La boucle réessaie au prochain tour.",
            file=sys.stderr,
        )
        sys.exit(1)
    with con:
        con.executemany("update items set mtime = ? where id = ?", [(seen, item_id) for item_id, seen in changed.items()])
print(f"{folder} : {len(changed)} fichier(s) changé(s), relu(s).")
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
  if follow_disk; then
    if [ -d "$MEDIA/10-rotation" ] && folder_state same "$MEDIA/10-rotation"; then
      reread "$MEDIA/10-rotation" grouping || true
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
      reread "$dir" grouping genre || true
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
