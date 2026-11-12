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
| `radiotomate/fiches/` | Les fiches de la bibliothèque : les règles de Hopper qui reconnaissent un titre et proposent de corriger ses tags, et la recherche d'un titre en ligne. Sans Quart, sans Beets ; seuls `http.py`, `sources.py` et `search.py` parlent au réseau, par httpx, et `fingerprint.py` lance `fpcalc` ([ADR 0017](../docs/decisions/0017-une-fiche-ne-s-ecrit-qu-acceptee.md)) |
| `radiotomate/models/` | Modèles SQLAlchemy |
| `radiotomate/commands/` | La commande `radiotomate` (click). `update/vNN.py` : les migrations |
| `playout/radiotomate.liq` | Le script Liquidsoap 2.4.5 |
| `tests/scheduler/` | Tests du scheduler, du domaine et des routes JSON. Ils tournent en CI |
| `tests/fiches/` | Les cas de Hopper sur les règles et la recherche des fiches, un module par fichier. Les services y sont joués par un faux transport httpx et une horloge simulée (`fakes.py`). Ils tournent en CI |
| `tests/interface/` | Tests Playwright des pages HTMX de l'amont. Hors CI |
| `tests/e2e/` | Le semis des parcours de la console (`scripts/e2e.sh`). Hors pytest |

## Ajouter une route JSON

1. La route va dans le module de `interface/` de son domaine, avec `@login_required`, puis le droit : `forbidden_unless("carts")`, `forbidden_unless("autodj")`, ou un test sur `current_user.user`. Le chemin finit par `.json`.
2. Les règles vont dans `domain/` ou `services/`, pas dans la route. Une erreur métier lève une `DomainError` de `domain/errors.py`, avec un message en français : la route répond `{error, code, message, field?}` avec le bon statut, sans code de plus.
3. Les tests vont dans `tests/scheduler/test_<domaine>_json.py`. Les fixtures `client` et `auth` de `tests/scheduler/conftest.py`, et les aides `_interface_client` et `_login` de `tests/scheduler/test_studio_json.py`, montent une interface de test. Ne pas mettre ces tests dans `tests/interface/` : la CI ne les lance pas.
4. Puis la console, [docs/api.md](../docs/api.md) et la liste de nginx : voir le [AGENTS.md](../AGENTS.md) de la racine.

## Migrations

- Une migration est `radiotomate/commands/update/vNN.py`, avec `async def upgrade(conn)` et `async def downgrade(conn)`. La dernière est v18. Prendre le numéro libre au moment d'écrire, et le vérifier encore avant de fusionner : deux branches peuvent prendre le même.
- Une migration publiée ne se modifie jamais, même pour un nom ou un commentaire.
- `radiotomate update` applique les migrations, et `--target-version N` redescend. `radiotomate-init` lance `update` à chaque démarrage de la station. La version du schéma est la clé `SCHEMA_VERSION` de la table `settings`.
- Chaque version passe dans sa propre transaction, avec la mise à jour de `SCHEMA_VERSION` : celle qui échoue ne laisse rien. Une migration ne termine donc jamais la transaction : ni `commit`, ni `rollback`, ni `VACUUM`, ni changement de `journal_mode`. `tests/test_update_atomic.py` le vérifie pour chaque version.
- Les clés étrangères sont coupées pendant la migration, puis vérifiées par `PRAGMA foreign_key_check` avant la validation : la version échoue si elle laisse plus de violations qu'elle n'en a trouvé. Effacer une ligne parente ne touche donc plus ses lignes filles : les traiter d'abord.
- Ce qu'`ALTER TABLE` ne sait pas faire passe par une reconstruction, comme le dit SQLite : créer la nouvelle table sous un autre nom, copier les lignes, supprimer l'ancienne, renommer la nouvelle, recréer les index. Ne jamais renommer l'ancienne : SQLite ferait pointer vers elle les clés étrangères des tables filles. Un exemple est dans `tests/test_update_atomic.py`.
- `tests/test_migrations.py` monte une base vide jusqu'à la dernière version, puis vérifie qu'on peut relancer. Il monte aussi chaque migration sur une base remplie à la version d'avant, puis la redescend : rien de ce qui existait avant la montée ne doit manquer, ni table, ni colonne, ni index, ni clé étrangère, ni ligne, ni valeur ; rien de ce que la montée a ajouté ne doit rester, ni table, ni colonne, ni index, ni clé étrangère, ni ligne. Puis il la remonte : la montée doit repasser, et rendre les tables, colonnes, index et clés étrangères de son premier passage. Ni les `CHECK`, ni les vues, ni les déclencheurs ne sont comparés, à la descente comme à la remontée : une migration qui en touche les vérifie dans son propre test.
- Cette base est faite de `STATION_DATA`, rangé par version. Une nouvelle migration y met une valeur pour chacune de ses colonnes, ni NULL ni son défaut, sous son propre numéro : le test le demande. Les lignes que sa montée transforme vont sous un numéro d'avant, puisque son cas part de la version d'avant : le test ne peut pas le deviner. Un état qui ne tient pas dans la même base, comme une ligne qui a déjà la valeur que la montée écrit, va dans `STATION_VARIANTS`.
- Une nouvelle migration a aussi son propre test, comme celui de la v18 : ce que sa montée fait aux lignes, et ce que sa descente fait de celles écrites à sa version. Le test commun part de la version d'avant, sans elles : il vérifie que la descente retire ce que la montée a ajouté, et que la montée repasse.
- Les descentes publiées qui perdent des données, v7, v9, v13 et v14, sont dans `LOSSY_DOWNGRADES`, avec leur raison. Celles qui laissent ce que leur montée a créé, v1 et v12, sont dans `INCOMPLETE_DOWNGRADES` : leur montée ne repasse pas, et le test ne la relance pas. Le test ne laisse passer que ces exceptions-là, et échoue quand l'une d'elles disparaît. Une migration pas encore publiée n'y entre pas : on corrige sa descente.
- Le modèle SQLAlchemy suit la migration dans le même commit.

## L'heure

- Les tables historiques (`metadata_log`, conducteur, alertes) stockent l'heure locale naïve du conteneur, réglée par `TZ`.
- L'Agenda et les tables nouvelles stockent de l'UTC naïf. Les conversions passent par les fonctions de `domain/agenda.py`.
- L'API rend l'heure de Paris avec son décalage, par exemple `2026-11-07T22:00+01:00`.
- Ne jamais comparer deux heures de conventions différentes. Les tests tournent avec `TZ=Europe/Paris`, comme la CI.
- Un créneau ou un direct de l'Agenda se compare à l'instant : `now_paris()`, sans argument. `now_paris(datetime.now())` lit l'horloge du conteneur comme l'heure de Paris : c'est faux sur une station réglée sur un autre fuseau, et la CI ne le voit pas. Un test qui laisse le code lire l'horloge demande la fixture `container_tz` de `tests/scheduler/conftest.py` : il passe aussi sous `America/Montreal`.

## Interrupteurs

Une fonction risquée se coupe par une clé de la table `settings` (modèle `Setting`). Une clé absente garde le comportement par défaut, choisi pour ne rien casser. Le modèle à suivre : `agenda_enabled`, dans `services/agenda.py`. Attention : une clé qui contient un point devient un sous-dictionnaire, mêlé à la configuration YAML. Choisir un préfixe absent du YAML, comme `features.`. Voir l'[ADR 0009](../docs/decisions/0009-interrupteurs.md).

## Pièges

- `radiotomate update` sert déjà aux migrations. Une nouvelle commande d'exploitation va sous `radiotomate maintenance …`, dans `commands/maintenance.py`. La commande `station` les lance par `docker compose exec`, et montre ce qu'elles écrivent : en français, comme le reste de sa sortie. Leurs tests sont dans `tests/test_maintenance.py`.
- Dans un service, une fonction nommée `update` masque le `update` de SQLAlchemy. Importer `update as sql_update` ; ruff le signale (F811).
- Les ports par défaut : 6811 pour l'interface, 6822 pour le scheduler, 6833 pour le playout. `interface --port` et `scheduler --port` changent les deux premiers, et la démo suit le port de l'interface. Mais l'interface appelle toujours le scheduler sur 6822 (`scheduler_api.py`), et le scheduler le playout sur 6833 (`scheduler_app.py`) : voir DEV-01.
- Liquidsoap 2.4 ne fond pas les transitions de `fallback` (savonet/liquidsoap#4179). Le script s'amende, il ne se réécrit pas. `liquidsoap --check` demande un `RTCONFIG` minimal : `scripts/verifier.sh liquidsoap` le fournit.
- `radiotomate/fiches/` traduit le JavaScript de Hopper. Toute regex y passe par `js_regex`, qui lui donne les règles de JavaScript, dites dans sa docstring : un `\b` ASCII ; les espaces de JavaScript pour `\s`, où U+FEFF compte, mais pas les signes de contrôle 0x1C à 0x1F qu'un texte abîmé à l'import porte ; un `.` qui ne prend aucun saut de ligne ; et sous `re.IGNORECASE`, la casse des seules lettres ASCII, où le « İ » turc n'est pas un « i ». Un `trim` s'écrit `js_trim`, un `!durée` `js_falsy`, `Math.round` `js_round` ; `$` devient `\Z`, `\d` `[0-9]`, et `??` n'est pas `or`. Trois écarts restent, rares : Python compte les lettres d'un signe hors du plan de base d'Unicode, là où JavaScript compte deux unités UTF-16 ; `[^\W\d_]`, qui traduit `\p{L}`, prend aussi un nombre comme « ² » ; et Python et Node n'ont pas la même version d'Unicode. Un outil d'écriture peut changer un échappement comme `\u2013` en caractère : ruff le signale (RUF001), mais pas un U+FEFF.
- La recherche des fiches forme ses adresses comme Hopper, à la lettre près : un `encodeURIComponent` s'écrit `component`. Une panne d'un service lève `HttpError`, une absence rend `None` : l'une ne se change jamais en l'autre, un titre ne passe pas pour introuvable parce qu'un service est tombé. Une requête sur une personne, membre d'un groupe ou Wikidata, ne part que verdict allumé, et rien de ce qu'elle rend ne va dans les preuves gardées (`Search.evidence`).
- `README.md`, `CHANGELOG.md`, `TODO.md` et `AUTHORS` de ce dossier sont ceux de l'amont, en anglais : ne pas les modifier. Les changements du fork se notent dans [docs/moteur/changements-radiotomate.md](../docs/moteur/changements-radiotomate.md).
