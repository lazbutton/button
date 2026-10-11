#!/bin/sh
# Idempotent: yaml, Beets, banque /media, compte admin. Tourne dans button-radiotomate.
set -eu
DATA="${RADIOTOMATE_DATA:-/data}"
export BEETSDIR="${BEETSDIR:-$DATA/Beets}"
CONFIG="$DATA/radiotomate.yaml"
MEDIA="${MEDIA_ROOT:-/media}"

mkdir -p "$DATA/carts" "$BEETSDIR"
# Compose bind-mount of a missing yaml creates a directory; wipe it so install can write the file.
if [ -d "$CONFIG" ]; then
  rm -rf "$CONFIG"
fi
if [ -x /setup-media-tree.sh ]; then
  /bin/sh /setup-media-tree.sh "$MEDIA"
else
  mkdir -p "$DATA/Music"
fi

# `radiotomate install` refuses RTCONFIG when the yaml does not exist yet.
if [ ! -f "$CONFIG" ]; then
  env -u RTCONFIG radiotomate install --no-revert-on-failure -d "$DATA"
fi
export RTCONFIG="$CONFIG"
radiotomate -c "$RTCONFIG" update

# Pas de mot de passe par défaut : compose refuse déjà de démarrer sans .env complet.
ICECAST_SOURCE_PASSWORD="${ICECAST_SOURCE_PASSWORD:?ICECAST_SOURCE_PASSWORD manquant}"
RT_NOWPLAYING_SECRET="${RT_NOWPLAYING_SECRET:?RT_NOWPLAYING_SECRET manquant}"
# 1 = sortie Icecast tenue vers une adresse injoignable : Liquidsoap démarre sans
# envoyer de flux (quand un autre moteur tient déjà le mount public). Vide = sorties normales.
RT_SKIP_ICECAST_OUTPUTS="${RT_SKIP_ICECAST_OUTPUTS:-}"
export ICECAST_SOURCE_PASSWORD RT_NOWPLAYING_SECRET RT_SKIP_ICECAST_OUTPUTS

python3 - <<'PY'
from pathlib import Path
import os
from ruamel.yaml import YAML

path = Path(os.environ["RTCONFIG"])
yaml = YAML()
yaml.preserve_quotes = True
data = yaml.load(path)
interface = data.setdefault("interface", {})
interface["cookie_secure"] = False
ppc = data.setdefault("playout_process_config", {})
# RT_SKIP_ICECAST_OUTPUTS=1 : une seule sortie, injoignable, pour que Liquidsoap
# démarre sans envoyer de flux à Icecast.
if os.environ.get("RT_SKIP_ICECAST_OUTPUTS") == "1":
    outputs = [
        {
            "driver": "icecast",
            "encoder": "mp3cbr",
            "quality": 128,
            "host": "127.0.0.1",
            "port": 9,
            "mount": "hold.mp3",
            "password": os.environ["ICECAST_SOURCE_PASSWORD"],
        }
    ]
    print("icecast outputs held")
else:
    outputs = [
        {
            "driver": "icecast",
            "encoder": "mp3cbr",
            "quality": 128,
            "host": "icecast",
            "port": 8000,
            "mount": "button.mp3",
            "password": os.environ["ICECAST_SOURCE_PASSWORD"],
        },
        {
            "driver": "icecast",
            "encoder": "wav",
            "quality": 1,
            "host": "icecast",
            "port": 8000,
            "mount": "studio.wav",
            "password": os.environ["ICECAST_SOURCE_PASSWORD"],
        },
    ]
ppc["outputs"] = outputs
ml = data.setdefault("metadata_log", {})
ml["relay_to"] = [
    {
        "url": "http://nowplaying:6820/hook",
        "add_header": {
            "Authorization": f"Bearer {os.environ['RT_NOWPLAYING_SECRET']}",
        },
        "add_field": {"SOURCE_NAME": "button"},
    }
]
import io
buf = io.StringIO()
yaml.dump(data, buf)
new_text = buf.getvalue()
if path.read_text() != new_text:
    path.write_text(new_text)
    print("patched", path)
else:
    print("unchanged", path)
# Contains Icecast passwords and the Vikunja bot password: owner + group only.
os.chmod(path, 0o640)
PY

MEDIA="${MEDIA_ROOT:-/media}"
BEETS_CONFIG="$BEETSDIR/config.yaml"
export BEETS_LIBRARY_DIR="$MEDIA"
python3 - <<'PY'
from pathlib import Path
import os
from ruamel.yaml import YAML

media = os.environ.get("MEDIA_ROOT", "/media")
beetsdir = os.environ["BEETSDIR"]
path = Path(beetsdir) / "config.yaml"
yaml = YAML()
yaml.preserve_quotes = True
if path.exists():
    data = yaml.load(path) or {}
else:
    data = {}
data["directory"] = media
data["library"] = str(Path(beetsdir) / "library.db")
imp = data.setdefault("import", {})
imp["move"] = False
imp["copy"] = False
imp["quiet_fallback"] = "asis"
imp["write"] = True
imp["incremental"] = True
plugins = data.get("plugins") or "info random replaygain"
if "drop2beets" in str(plugins):
    plugins = " ".join(p for p in str(plugins).split() if p != "drop2beets")
data["plugins"] = plugins
rg = data.setdefault("replaygain", {})
rg["backend"] = "ffmpeg"
rg["overwrite"] = True
data.pop("drop2beets", None)
import io
buf = io.StringIO()
yaml.dump(data, buf)
new_text = buf.getvalue()
if not path.exists() or path.read_text() != new_text:
    path.write_text(new_text)
    print("patched beets", path)
else:
    print("unchanged beets", path)
os.chmod(path, 0o640)
PY

RT_ADMIN_USER="${RT_ADMIN_USER:-button}"
RT_ADMIN_PASSWORD="${RT_ADMIN_PASSWORD:-}"
if [ -n "$RT_ADMIN_PASSWORD" ]; then
  export RT_ADMIN_USER
  set +e
  python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

db = Path(os.environ.get("RADIOTOMATE_DATA", "/data")) / "radiotomate.db"
user = os.environ["RT_ADMIN_USER"]
if not db.exists():
    raise SystemExit(0)
con = sqlite3.connect(db)
try:
    n = con.execute("select count(*) from users where username=?", (user,)).fetchone()[0]
except sqlite3.OperationalError:
    n = 0
con.close()
raise SystemExit(0 if n == 0 else 10)
PY
  add_status=$?
  set -e
  if [ "$add_status" -eq 0 ]; then
    radiotomate -c "$RTCONFIG" users add "$RT_ADMIN_USER" --admin --password "$RT_ADMIN_PASSWORD"
    echo "admin user $RT_ADMIN_USER created"
  else
    echo "admin user $RT_ADMIN_USER already exists"
  fi
fi

# Liquidsoap refuse de démarrer en root ; les images tournent en rtuser (uid 1000).
if id rtuser >/dev/null 2>&1; then
  chown -R rtuser:rtuser "$DATA"
  echo "chown rtuser $DATA"
fi
