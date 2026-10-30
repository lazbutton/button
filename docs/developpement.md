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

Un seul `scripts/dev.sh` à la fois par machine : il prend les ports par défaut. Les parcours dans un navigateur, eux, prennent des ports libres et tournent à côté ([plus bas](#les-parcours-dans-un-navigateur)). Pour faire travailler plusieurs agents en même temps, voir [travailler-a-plusieurs.md](travailler-a-plusieurs.md).

## Vérifier avant de proposer un changement

```bash
./scripts/verifier.sh                   # tout ce qui peut tourner sur cette machine
./scripts/verifier.sh moteur console    # seulement ces parties
```

Le script lance les mêmes commandes que la CI ([`.github/workflows/`](../.github/workflows/)) :

| Partie | Ce qui tourne | Il faut |
|---|---|---|
| `moteur` | `ruff check`, `ruff format --check`, puis `pytest` avec `TZ=Europe/Paris`, sans `tests/interface` ni `tests/e2e` | Poetry |
| `liquidsoap` | `liquidsoap --check engine/playout/radiotomate.liq`, avec un `RTCONFIG` minimal | Docker |
| `console` | `npm test`, puis `tsc` et `vite build` | Node 22, `npm install` fait |
| `services` | les sept tests du catalogue listés dans `services.yml` | `services/catalog/.venv`, voir plus bas |
| `nginx` | `nginx -t` sur `console/docker/nginx.conf.template` et ses en-têtes de sécurité, rendus par le script de démarrage de l'image | Docker |
| `deploy` | `docker compose config` avec `.env.example`, puis ShellCheck s'il est installé | Docker |

Sans argument, une partie à qui il manque un outil est sautée, et le résumé le dit. Nommée, elle échoue.

Les dépendances du catalogue vont dans un environnement à part, une fois :

```bash
python3 -m venv services/catalog/.venv
services/catalog/.venv/bin/pip install -r services/catalog/requirements.txt
```

Les tests Playwright des pages HTMX de l'amont ne tournent pas en CI : `cd engine && poetry run playwright install chromium`, une fois, puis `poetry run pytest tests/interface`.

## Les parcours dans un navigateur

Les parcours de la console passent par un vrai navigateur, avec [Playwright](https://playwright.dev/) :

```bash
./scripts/e2e.sh                          # tous les parcours
./scripts/e2e.sh e2e/antenne.spec.ts      # un fichier : les arguments vont à Playwright
./scripts/e2e.sh --headed                 # en voyant le navigateur
```

Il faut `poetry install` dans `engine/` et `npm install` dans `console/`, rien d'autre. Au premier lancement, Playwright télécharge Chromium, une fois par machine, hors du dépôt (`~/Library/Caches/ms-playwright` sur macOS). Sous Linux, les bibliothèques dont il a besoin s'installent avec `cd console && npx playwright install-deps chromium`, qui demande les droits d'administration. Ni `verifier.sh` ni la CI ne lancent encore les parcours : c'est la fiche TST-03.

Le script monte un banc à part, dans `.e2e/<date>-<pid>/`, ignoré par git :

| Pièce | Ce que c'est |
|---|---|
| Moteur | l'interface en mode démo (`radiotomate interface --demo --port …`), sur une base semée par `engine/tests/e2e/seed.py` : un compte par rôle, des carts, une horloge pour toute la semaine, et une petite banque pour `MEDIA_ROOT` |
| Comptes | `comptes.json` : `admin`, `programmateur` et `animateur`, avec un mot de passe tiré à chaque lancement |
| Faux services | `console/e2e/stubs/` : le catalogue (recherche et fichiers de la banque) et tusd (envois tus), sans Meilisearch ni Docker. Comme en prod, ils demandent au moteur une session ou, pour tusd, le lien d'un invité |
| Console | le build de production, servi par `vite preview`, qui relaie comme nginx : les routes du moteur lues dans `console/docker/nginx.conf.template`, `/library` vers le catalogue, `/tus` vers tusd |

Chaque pièce prend un port libre, jamais ceux du banc de dev : deux lancements tournent en même temps, et à côté de `scripts/dev.sh`. Dans un lancement, les parcours passent un par un, dans un seul navigateur.

Tout s'arrête à la fin, même après un échec ou un `Ctrl-C`. Si tout passe, le dossier du lancement est effacé. Sinon il reste, avec le journal de chaque pièce (`moteur.log`, `console.log`…) et, dans `resultats/`, les captures et les traces d'un parcours raté. Pour rejouer une trace : `cd console && npx playwright show-trace ../.e2e/<lancement>/resultats/<parcours>/trace.zip`. Rien ne purge ces dossiers : `rm -rf .e2e` les efface tous, quand aucun lancement ne tourne.

Un parcours s'écrit dans `console/e2e/<sujet>.spec.ts`. Il importe `test` et `expect` de `e2e/banc.ts`, qui fait aussi échouer un parcours sur toute erreur JavaScript de la page, et `seConnecter(page, rôle)` pour entrer avec un compte semé.

Sur `main`, la CI publie aussi les images Docker, seulement si tout est vert.

## Règles du projet

Elles sont dans le [AGENTS.md](../AGENTS.md) de la racine, communes aux personnes et aux agents, et dans le `AGENTS.md` de chaque dossier. Les plus importantes :

- **L'API JSON est un contrat.** Une route du moteur ne change de forme qu'avec la console, dans la même branche, et [`docs/api.md`](api.md) suit. Une route nouvelle entre dans la liste de nginx : un test le vérifie.
- **Le moteur reste un fork mince.** Les changements y sont minimaux et rétro-compatibles. Le script Liquidsoap s'amende, il ne se réécrit pas. Voir [`engine/FORK.md`](../engine/FORK.md).
- **Le schéma de la base ne recule jamais.** Toute évolution est une nouvelle migration, et une migration publiée ne se modifie plus.
- **Aucune donnée de station dans le dépôt** : ni secret, ni adresse, ni compte réel.
- **L'interface est en français**, en thème clair et sombre, utilisable au clavier et sur téléphone.
- **Un commit par sujet.** Le message dit ce qui change, puis pourquoi.

## Écrire une migration

1. Ajouter `engine/radiotomate/commands/update/vNN.py`, avec le numéro libre suivant, `async def upgrade(conn)` et `async def downgrade(conn)`. La dernière publiée est v18. Chacune passe dans sa propre transaction, clés étrangères coupées : ni `commit` ni `VACUUM`, et une suppression ne cascade plus. Le détail est dans [`engine/AGENTS.md`](../engine/AGENTS.md#migrations).
2. Mettre à jour le modèle SQLAlchemy concerné, dans le même commit.
3. Ajouter son test dans `engine/tests/test_migrations.py` : une base de la version d'avant, avec des données, qui monte puis redescend.
4. Vérifier l'aller-retour sur une copie de base : `radiotomate update --target-version N-1`, puis `radiotomate update`.

`radiotomate-init` applique les migrations à chaque démarrage. Revenir à une image plus ancienne demande donc de redescendre d'abord le schéma : voir [`deploiement.md`](deploiement.md#revenir-en-arrière).
