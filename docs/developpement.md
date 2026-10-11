# Développer

## Prérequis

| Outil | Pour | Version |
|---|---|---|
| Python et [Poetry](https://python-poetry.org/) | le moteur | Python 3.11 ou plus (la CI utilise 3.13) |
| Node | la console | 22 |
| Docker et Compose v2 | les services, la station complète | — |
| Liquidsoap | le son, et `liquidsoap --check` | 2.4.5, facultatif en dev |

## Le banc local

Le banc lance l'interface du moteur en **mode démo**, sans Liquidsoap : l'antenne est simulée. La console tourne à côté, en mode développement.

Une fois :

```bash
cd engine
poetry install
poetry run radiotomate develop     # crée engine/radio_data/ (base et YAML locaux, ignorés par git)
poetry run radiotomate -c radio_data/radiotomate.yaml users add <identifiant> --admin
cd ../console && npm install
```

Ensuite, depuis la racine du dépôt :

```bash
./scripts/dev.sh
```

- Interface du moteur : http://127.0.0.1:6811
- Console : http://127.0.0.1:5175

`Ctrl-C` arrête les deux. Pour tester le tuyau audio (Icecast et titre en cours) sans la station entière, voir [`deploy/local/`](../deploy/local/README.md).

## Vérifier avant de proposer un changement

| Partie | Commandes |
|---|---|
| Moteur | `cd engine && poetry run ruff check && poetry run ruff format --check && poetry run pytest tests/scheduler tests/test_*.py` |
| Interface du moteur | `poetry run pytest tests/interface`, après `poetry run playwright install chromium` une fois |
| Script Liquidsoap | `RTCONFIG=… liquidsoap --check engine/playout/radiotomate.liq` |
| Console | `cd console && npm test && npm run build` |
| Catalogue | `cd services/catalog && python test_inbox_api.py` |
| Compose | `cd deploy && docker compose config --quiet`, avec un `.env` rempli |

La CI ([`.github/workflows/`](../.github/workflows/)) relance ces vérifications sur chaque pull request, pour les dossiers touchés, sauf les tests Playwright et le Compose. Sur `main`, elle publie aussi les images Docker, seulement si tout est vert.

## Règles du projet

- **L'API JSON est un contrat.** Une route du moteur ne change de forme qu'avec la console, dans le même commit, et [`docs/api.md`](api.md) suit.
- **Le moteur reste un fork mince.** Les changements y sont minimaux et rétro-compatibles. Le script Liquidsoap s'amende, il ne se réécrit pas. Voir [`engine/FORK.md`](../engine/FORK.md).
- **Le schéma de la base ne recule jamais.** Toute évolution est une nouvelle migration `engine/radiotomate/commands/update/vN.py`, avec `upgrade` et `downgrade`.
- **L'interface est en français**, en thème clair et sombre, utilisable au clavier et sur téléphone.
- **Un commit par sujet.** Le message dit ce qui change, puis pourquoi.

## Écrire une migration

1. Ajouter `vN.py` (le numéro suivant) avec `async def upgrade(conn)` et `async def downgrade(conn)`.
2. Mettre à jour le modèle SQLAlchemy concerné.
3. Vérifier l'aller-retour sur une copie de base : `radiotomate update --target-version N-1`, puis `radiotomate update`.

`radiotomate-init` applique les migrations à chaque démarrage. Revenir à une image plus ancienne demande donc de redescendre d'abord le schéma : voir [`deploiement.md`](deploiement.md#revenir-en-arrière).
