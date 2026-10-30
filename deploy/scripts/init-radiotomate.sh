#!/bin/sh
# Idempotent: yaml, Beets, banque /media, compte admin. Tourne dans button-radiotomate.
set -eu
DATA="${RADIOTOMATE_DATA:-/data}"
export BEETSDIR="${BEETSDIR:-$DATA/Beets}"
CONFIG="$DATA/radiotomate.yaml"
MEDIA="${MEDIA_ROOT:-/media}"

# true : le cookie de session porte Secure, le navigateur ne l'envoie qu'en HTTPS.
# false : accès en HTTP seul (banc local, réseau privé). Ce script ne tourne
# jamais en mode démo : l'avertissement vise toujours une vraie station.
# Vérifié avant tout : une valeur refusée ne laisse pas de schéma migré.
RT_COOKIE_SECURE="${RT_COOKIE_SECURE:-true}"
case "$RT_COOKIE_SECURE" in
  true) ;;
  false)
    echo "Attention : RT_COOKIE_SECURE=false, le cookie de session circule aussi en HTTP, en clair." >&2
    echo "À réserver à un accès en HTTP seul : banc local, réseau privé. Derrière HTTPS, retirer RT_COOKIE_SECURE de .env, puis recréer les trois services du moteur (docs/deploiement.md, « Le cookie de session »)." >&2
    ;;
  *)
    echo "RT_COOKIE_SECURE vaut « $RT_COOKIE_SECURE » : mettre true ou false dans .env, puis recréer les trois services du moteur (docs/deploiement.md, « Le cookie de session »)." >&2
    exit 1
    ;;
esac
export RT_COOKIE_SECURE

# Les secrets de .env.example valent change-me, connus de tous : refusés eux aussi
# avant tout. Personne ne tape les quatre secrets de machine : 24 caractères au
# moins. En secours, RT_ALLOW_SHORT_SECRETS=1 fait d'un secret trop court un
# avertissement. Le journal ne montre jamais une valeur.
RT_ALLOW_SHORT_SECRETS="${RT_ALLOW_SHORT_SECRETS:-}"
refused=""
short=""
check_secret() { # nom, valeur, longueur minimale
  if [ -z "$2" ]; then
    refused="$refused
  $1 : vide"
  elif [ "$2" = change-me ]; then
    refused="$refused
  $1 : vaut change-me, comme dans .env.example"
  else
    # En caractères : dash compterait ${#2} en octets.
    length=$(($(printf %s "$2" | LC_ALL=C.UTF-8 wc -m)))
    if [ "$length" -lt "$3" ]; then
      short="$short
  $1 : $length caractères, il en faut $3"
    fi
  fi
}
check_secret ICECAST_SOURCE_PASSWORD "${ICECAST_SOURCE_PASSWORD:-}" 24
check_secret ICECAST_ADMIN_PASSWORD "${ICECAST_ADMIN_PASSWORD:-}" 24
check_secret RT_NOWPLAYING_SECRET "${RT_NOWPLAYING_SECRET:-}" 24
check_secret MEILI_MASTER_KEY "${MEILI_MASTER_KEY:-}" 24
# Le mot de passe du compte admin, créé quand il manque, n'a pas de longueur
# minimale. Vide, il ne crée aucun compte : permis une fois la base créée, refusé
# à la première installation.
if [ -n "${RT_ADMIN_PASSWORD:-}" ]; then
  check_secret RT_ADMIN_PASSWORD "$RT_ADMIN_PASSWORD" 0
elif [ ! -f "$DATA/radiotomate.db" ]; then
  refused="$refused
  RT_ADMIN_PASSWORD : vide, la station démarrerait sans compte admin"
fi
if [ -n "$short" ] && [ "$RT_ALLOW_SHORT_SECRETS" = 1 ]; then
  echo "Attention : secrets trop courts, acceptés par RT_ALLOW_SHORT_SECRETS=1 :$short" >&2
  echo "Les remplacer dès que possible (openssl rand -hex 24), retirer RT_ALLOW_SHORT_SECRETS de .env, puis recréer toute la station : docker compose up -d --force-recreate (docs/deploiement.md, « Les secrets »)." >&2
  short=""
fi
if [ -n "$refused$short" ]; then
  # RT_ADMIN_PASSWORD ne sert qu'à radiotomate-init : le relancer suffit, sans
  # couper l'antenne. Un secret de machine se lit au démarrage de chaque service.
  restart="docker compose up -d"
  case "$refused$short" in
    *ICECAST_* | *RT_NOWPLAYING_SECRET* | *MEILI_MASTER_KEY*) restart="$restart --force-recreate" ;;
  esac
  echo "Secrets refusés dans .env : tant qu'ils restent, le moteur et l'antenne ne peuvent pas démarrer.$refused$short" >&2
  echo "Tirer chaque secret avec : openssl rand -hex 24" >&2
  echo "Mettre les nouvelles valeurs dans .env, puis lancer : $restart (docs/deploiement.md, « Les secrets »)." >&2
  if [ -n "$short" ]; then
    echo "En secours seulement, RT_ALLOW_SHORT_SECRETS=1 dans .env laisse démarrer avec un secret trop court : poser la ligne, puis docker compose up -d." >&2
  fi
  if [ "${RT_ADMIN_PASSWORD:-}" = change-me ] && [ -f "$DATA/radiotomate.db" ]; then
    echo "RT_ADMIN_PASSWORD ne change pas un compte admin déjà créé : le vider dans .env. S'il a été créé avec change-me, changer aussi son mot de passe dans la console, Mon compte." >&2
  fi
  exit 1
fi
# RT_INIT_CHECK_ONLY=1, passé par docker compose run -e avant une mise à jour :
# le contrôle seul. Rien n'est écrit, la station en service continue.
if [ "${RT_INIT_CHECK_ONLY:-}" = 1 ]; then
  echo "Secrets : rien ne bloque le démarrage."
  exit 0
fi

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
interface["cookie_secure"] = os.environ["RT_COOKIE_SECURE"] == "true"
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

# Un compte admin créé avec change-me le garde, quoi que dise .env : le rappeler
# à chaque démarrage, sans jamais bloquer, pour que la console reste ouverte à
# Mon compte. Une erreur imprévue s'affiche, et le démarrage continue.
export RT_ADMIN_USER
python3 - <<'PY' || true
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

db = Path(os.environ.get("RADIOTOMATE_DATA", "/data")) / "radiotomate.db"
user = os.environ["RT_ADMIN_USER"]
try:
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        row = con.execute("select password from users where username=?", (user,)).fetchone()
except sqlite3.Error:
    row = None
try:
    known = row is not None and PasswordHasher().verify(row[0], "change-me")
except (InvalidHashError, VerificationError):
    known = False
if known:
    print(
        f"Attention : le compte admin « {user} » a encore le mot de passe change-me, "
        "connu de tous. Le changer dans la console, Mon compte.",
        file=sys.stderr,
    )
PY

# Liquidsoap refuse de démarrer en root ; les images tournent en rtuser (uid 1000).
if id rtuser >/dev/null 2>&1; then
  chown -R rtuser:rtuser "$DATA"
  echo "chown rtuser $DATA"
fi
