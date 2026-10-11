# Services

Les services qui entourent le moteur. Chacun a son image, publiée par la CI ([`services.yml`](../.github/workflows/services.yml)).

## catalog

Index de la banque de sons dans Meilisearch, recherche pour la console, et réception des envois du navigateur.

| Route | Rôle |
|---|---|
| `GET /search` | Recherche dans la banque (`q`, `limit`, `kind`, `grouping`, `folder`) |
| `GET /inbox.json` | File d'attente, rejets et quota de l'inbox |
| `GET /media/…` | Lecture d'un fichier de la banque (requêtes Range) |
| `POST /tus-hook` | Hook de tusd : accepte ou refuse un envoi, puis range le fichier dans `00-inbox` |
| `GET /health` | Sonde |

Variables : `MEDIA_ROOT`, `MEILI_URL`, `MEILI_MASTER_KEY`, `MEILI_INDEX`, `CATALOG_PORT`, `AUTOMATE_URL`, `TUSD_DIR`, `INBOX_QUOTA_BYTES`.

Tests : `cd services/catalog && python test_inbox_api.py`.

## nowplaying

Reçoit les métadonnées du moteur et publie le titre en cours pour les sites et les players. Relaie aussi quelques sondes du playout vers la console.

| Route | Rôle |
|---|---|
| `POST /hook` | Métadonnées envoyées par le moteur (`metadata_log.relay_to`), avec `Authorization: Bearer <RT_NOWPLAYING_SECRET>` |
| `GET /now.json` | Titre en cours, avec CORS |
| `GET /machine.json`, `/voiceover` | Sondes du playout |

Variables : `RT_NOWPLAYING_PORT`, `RT_NOWPLAYING_SECRET`, `RT_NOWPLAYING_FILE`, `RT_PLAYOUT_URL`, `RT_PLAYOUT_PCM`, `RT_PLAYOUT_YAML`, `RT_PLAYOUT_TOKEN`, `BUTTON_MEDIA_ROOT`.

## icecast

Icecast 2, configuré au démarrage depuis [`icecast.xml`](icecast/icecast.xml).

Variables : `ICECAST_SOURCE_PASSWORD`, `ICECAST_ADMIN_PASSWORD`, `ICECAST_ADMIN_EMAIL` (contact affiché sur la page de statut).

Pour tester Icecast et nowplaying seuls, sans la station : [`deploy/local/`](../deploy/local/README.md).
