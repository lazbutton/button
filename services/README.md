# Services

Les services qui entourent le moteur. Chacun a son image, publiée par la CI ([`services.yml`](../.github/workflows/services.yml)). Pour y travailler : [AGENTS.md](AGENTS.md).

## catalog

Index de la banque de sons dans Meilisearch, recherche pour la console, réception des envois du navigateur et des sets des invités de l'Agenda, mots de passe du dossier partagé.

| Route | Rôle |
|---|---|
| `GET /search` | Recherche dans la banque (`q`, `limit`, `kind`, `grouping`, `folder`) |
| `GET /inbox.json` | File d'attente, rejets, quota de l'inbox et place sur le disque |
| `GET /media/…` | Lecture d'un fichier de la banque (requêtes Range) |
| `POST /banks.json` | Crée une collection, pour un admin |
| `GET /volume.json` | Nom et hôte du dossier partagé |
| `POST /volume-password.json` | Pose ou retire le mot de passe du dossier d'un compte, pour un admin |
| `POST /prune` | Retire de l'index de recherche les fichiers qui ne sont dans aucun bac, pour un admin |
| `POST /tus-hook` | Hook de tusd : accepte ou refuse un envoi, puis range le fichier. Un envoi d'équipe va dans `00-inbox` ; un set d'invité va dans `40-emissions`, après accord du moteur |
| `GET /health`, `/health/live` | Sondes |

La console joint le catalogue sous `/library/` : voir [docs/api.md](../docs/api.md#catalogue-service-à-part-du-moteur). Le catalogue demande au moteur qui est connecté, par `/account.json` avec le cookie du navigateur. Toutes ses routes demandent une session, sauf les sondes et `/tus-hook`, qu'appelle tusd.

Variables : `MEDIA_ROOT`, `MEILI_URL`, `MEILI_MASTER_KEY`, `MEILI_INDEX`, `CATALOG_PORT`, `AUTOMATE_URL`, `TUSD_DIR`, `TUSD_USER`, `INBOX_QUOTA_BYTES`, `STATION_NAME`, `SMB_HOST`, `SHARE_PRIVATE`.

Tests : `./scripts/verifier.sh services` lance les quinze fichiers de test de la CI. Un seul : `cd services/catalog && .venv/bin/python test_inbox_api.py`. Ils couvrent aussi nowplaying, et les scripts du dossier partagé, rangés dans `deploy/`.

## nowplaying

Reçoit les métadonnées du moteur et publie le titre en cours pour les sites et les players. Relaie aussi une sonde du playout.

| Route | Rôle |
|---|---|
| `POST /hook` | Métadonnées envoyées par le moteur (`metadata_log.relay_to`), avec `Authorization: Bearer <RT_NOWPLAYING_SECRET>` |
| `GET /now.json` | Titre en cours, avec CORS |
| `GET /machine.json` | Sonde du playout, d'après son `GET /health`, sans jeton : son état, le processeur, la mémoire, et la place sur le disque de la banque |

nowplaying ne relaie au playout rien d'autre : son port se joint sans session. Il n'a plus les routes d'un micro par-dessus l'antenne, `/voiceover` et `/voiceover/pcm`, que rien dans BUTTON n'appelait.

Variables : `RT_NOWPLAYING_PORT`, `RT_NOWPLAYING_SECRET`, `RT_NOWPLAYING_FILE`, `RT_PLAYOUT_URL`, `RT_PLAYOUT_YAML`, `BUTTON_MEDIA_ROOT`.

## icecast

Icecast 2, configuré au démarrage depuis [`icecast.xml`](icecast/icecast.xml).

Variables : `ICECAST_SOURCE_PASSWORD`, `ICECAST_ADMIN_PASSWORD`, `ICECAST_ADMIN_EMAIL` (contact affiché sur la page de statut).

Pour tester Icecast et nowplaying seuls, sans la station : [`deploy/local/`](../deploy/local/README.md).
