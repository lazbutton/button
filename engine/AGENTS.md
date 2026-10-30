# Consignes pour le moteur

À lire avec le [AGENTS.md](../AGENTS.md) de la racine. Ce dossier est un fork de Radiotomate : [FORK.md](FORK.md) dit ce qui change par rapport à l'amont.

## Lancer et vérifier

```bash
cd engine
poetry install                     # une fois par worktree
poetry run radiotomate develop     # crée radio_data/, ignoré par git
poetry run radiotomate -c radio_data/radiotomate.yaml interface --demo
../scripts/verifier.sh moteur      # ruff, format, pytest comme la CI
```

La CI lance `pytest` avec `TZ=Europe/Paris`, sans `tests/interface` ni `tests/e2e`. `scripts/verifier.sh moteur` fait de même.

## Où est quoi

| Chemin | Rôle |
|---|---|
| `radiotomate/interface/` | Routes de l'interface : pages HTMX d'origine et routes JSON de la console. Un module = un blueprint, enregistré dans `interface_app.py` |
| `radiotomate/scheduler/` | Le scheduler : horloge (`clock.py`), conducteur (`rundown.py`, `execution.py`), pupitre (`desk.py`), Agenda (`agenda.py`), alertes, métriques, rétention |
| `radiotomate/domain/` | Règles métier pures, sans Quart. Les erreurs (`errors.py`) deviennent des réponses JSON |
| `radiotomate/services/` | Opérations partagées par l'interface et le scheduler : carts, auto-DJ, émissions, Agenda, banque |
| `radiotomate/models/` | Modèles SQLAlchemy |
| `radiotomate/commands/` | La commande `radiotomate` (click). `update/vNN.py` : les migrations |
| `playout/radiotomate.liq` | Le script Liquidsoap 2.4.5 |
| `tests/scheduler/` | Tests du scheduler, du domaine et des routes JSON. Ils tournent en CI |
| `tests/interface/` | Tests Playwright des pages HTMX de l'amont. Hors CI |

## Ajouter une route JSON

1. La route va dans le module de `interface/` de son domaine, avec `@login_required`, puis le droit : `forbidden_unless("carts")`, `forbidden_unless("autodj")`, ou un test sur `current_user.user`. Le chemin finit par `.json`.
2. Les règles vont dans `domain/` ou `services/`, pas dans la route. Une erreur métier lève une `DomainError` de `domain/errors.py`, avec un message en français : la route répond `{error, code, message, field?}` avec le bon statut, sans code de plus.
3. Les tests vont dans `tests/scheduler/test_<domaine>_json.py`. Les fixtures `client` et `auth` de `tests/scheduler/conftest.py`, et les aides `_interface_client` et `_login` de `tests/scheduler/test_studio_json.py`, montent une interface de test. Ne pas mettre ces tests dans `tests/interface/` : la CI ne les lance pas.
4. Puis la console, [docs/api.md](../docs/api.md) et la liste de nginx : voir le [AGENTS.md](../AGENTS.md) de la racine.

## Migrations

- Une migration est `radiotomate/commands/update/vNN.py`, avec `async def upgrade(conn)` et `async def downgrade(conn)`. La dernière est v17. Prendre le numéro libre au moment d'écrire, et le vérifier encore avant de fusionner : deux branches peuvent prendre le même.
- Une migration publiée ne se modifie jamais, même pour un nom ou un commentaire.
- `radiotomate update` applique les migrations, et `--target-version N` redescend. `radiotomate-init` lance `update` à chaque démarrage de la station. La version du schéma est la clé `SCHEMA_VERSION` de la table `settings`.
- `tests/test_migrations.py` monte une base vide jusqu'à la dernière version, puis vérifie qu'on peut relancer. Une nouvelle migration y ajoute son propre test : une base de la version d'avant, avec des données, qui monte puis redescend sans rien perdre de ce qui existait.
- Le modèle SQLAlchemy suit la migration dans le même commit.

## L'heure

- Les tables historiques (`metadata_log`, conducteur, alertes) stockent l'heure locale naïve du conteneur, réglée par `TZ`.
- L'Agenda et les tables nouvelles stockent de l'UTC naïf. Les conversions passent par les fonctions de `domain/agenda.py`.
- L'API rend l'heure de Paris avec son décalage, par exemple `2026-11-07T22:00+01:00`.
- Ne jamais comparer deux heures de conventions différentes. Les tests tournent avec `TZ=Europe/Paris`, comme la CI.

## Interrupteurs

Une fonction risquée se coupe par une clé de la table `settings` (modèle `Setting`). Une clé absente garde le comportement par défaut, choisi pour ne rien casser. Le modèle à suivre : `agenda_enabled`, dans `services/agenda.py`. Attention : une clé qui contient un point devient un sous-dictionnaire, mêlé à la configuration YAML. Choisir un préfixe absent du YAML, comme `features.`. Voir l'[ADR 0009](../docs/decisions/0009-interrupteurs.md).

## Pièges

- `radiotomate update` sert déjà aux migrations. Une nouvelle commande d'exploitation va sous `radiotomate maintenance …`, groupe à créer dans `commands/` à la première commande.
- Dans un service, une fonction nommée `update` masque le `update` de SQLAlchemy. Importer `update as sql_update` ; ruff le signale (F811).
- Les ports sont écrits en dur : 6811 pour l'interface (`commands/interface.py`), 6822 pour le scheduler, 6833 pour le playout (`scheduler_api.py`, `scheduler_app.py`). Un seul moteur de démo par machine.
- Liquidsoap 2.4 ne fond pas les transitions de `fallback` (savonet/liquidsoap#4179). Le script s'amende, il ne se réécrit pas. `liquidsoap --check` demande un `RTCONFIG` minimal : `scripts/verifier.sh liquidsoap` le fournit.
- `README.md`, `CHANGELOG.md`, `TODO.md` et `AUTHORS` de ce dossier sont ceux de l'amont, en anglais : ne pas les modifier. Les changements du fork se notent dans [docs/moteur/changements-radiotomate.md](../docs/moteur/changements-radiotomate.md).
