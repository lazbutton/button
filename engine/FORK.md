# Le moteur : un fork de Radiotomate

Ce dossier est le moteur de BUTTON. Il dérive de [Radiotomate](https://radiotomate.org/), écrit par Martin Kirchgessner ([dépôt amont](https://git.sr.ht/~martink/radiotomate)), et reste sous licence **AGPL-3.0-or-later**. Le [`README.md`](README.md), le [`CHANGELOG.md`](CHANGELOG.md), le [`TODO.md`](TODO.md) et les [`AUTHORS`](AUTHORS) de ce dossier sont ceux de l'amont, en anglais.

Ce qui change par rapport à l'amont est décrit en détail dans [`docs/moteur/changements-radiotomate.md`](../docs/moteur/changements-radiotomate.md). En bref :

- **Horloges à la place du cron.** APScheduler est retiré. Une horloge est un motif de positions (musique, jingle, son, pub), enchaînées ou calées sur une minute, avec des ancres dures ou molles.
- **Conducteur et vérité d'antenne.** Le scheduler prévoit une file (`rundown_items`), envoie des commandes au playout (`playout_commands`) et réconcilie ce qui a vraiment joué (`metadata_log`).
- **API JSON pour la console**, à côté de l'interface HTMX d'origine. Voir [`docs/api.md`](../docs/api.md).
- **Exploitation** : alertes (silence, playout injoignable, créneau live sans encodeur), métriques, rétention, sondes de santé.

## Où est quoi

| Chemin | Rôle |
|---|---|
| `radiotomate/scheduler/` | Horloge (`clock.py`), conducteur (`execution.py`, `rundown.py`), pupitre (`desk.py`), alertes, métriques, rétention |
| `radiotomate/interface/` | Interface web : pages HTMX et routes JSON de la console |
| `radiotomate/models/`, `domain/`, `services/` | Modèles SQLAlchemy, règles métier, opérations partagées |
| `radiotomate/commands/update/` | Migrations du schéma (`vN.py`), appliquées par `radiotomate update` |
| `playout/radiotomate.liq` | Le script Liquidsoap (2.4.5) qui produit le son |
| `tests/` | Tests du scheduler et des routes JSON (`tests/scheduler`), tests Playwright de l'interface (`tests/interface`) |

## Règles du fork

- **Patches minces.** Le script Liquidsoap ne se réécrit pas : on l'amende, et `liquidsoap --check` tourne en CI.
- **Compatibilité.** Les routes JSON gardent leur forme. Une migration de schéma s'ajoute toujours (`vN+1`) et sait se défaire (`downgrade`).
- **Le nom du paquet reste `radiotomate`** (commande, imports, migrations), pour garder la filiation et faciliter les échanges avec l'amont.

## Lancer le moteur seul

Il faut Python 3.11 ou plus, [Poetry](https://python-poetry.org/), et Liquidsoap 2.4.5 pour le son. Sans Liquidsoap, le mode démo suffit pour l'interface.

```bash
cd engine
poetry install
poetry run radiotomate develop            # crée radio_data/ (base et config locales, ignorées par git)
poetry run radiotomate -c radio_data/radiotomate.yaml users add <identifiant> --admin
poetry run radiotomate -c radio_data/radiotomate.yaml interface --demo --reload
```

L'interface répond sur http://127.0.0.1:6811. Pour le banc complet avec la console, voir [`docs/developpement.md`](../docs/developpement.md).

## Vérifier

```bash
poetry run ruff check && poetry run ruff format --check
poetry run pytest tests/scheduler tests/test_*.py
poetry run pytest tests/interface      # Playwright : `poetry run playwright install chromium` une fois
RTCONFIG=… liquidsoap --check playout/radiotomate.liq
```
