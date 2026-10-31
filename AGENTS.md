# Consignes pour les agents

Ce fichier est la source unique des consignes pour les agents de code : Claude Code, Codex, Cursor et les autres. `CLAUDE.md` l'importe. Chaque dossier principal a son propre `AGENTS.md`, plus précis, à lire avant d'y travailler. Pour les humains, le point d'entrée reste [CONTRIBUTING.md](CONTRIBUTING.md).

## Le projet

BUTTON est un automate de diffusion pour radios associatives, sous licence AGPL-3.0-or-later. Ce dépôt contient le logiciel. Les données d'une station n'y entrent jamais.

| Dossier | Contenu | Consignes |
|---|---|---|
| `engine/` | Le moteur, fork de Radiotomate : Python (Quart, SQLAlchemy, Beets) et Liquidsoap | [engine/AGENTS.md](engine/AGENTS.md) |
| `console/` | La console web : React, Vite, TypeScript | [console/AGENTS.md](console/AGENTS.md) |
| `services/` | Catalogue, titre en cours, Icecast | [services/AGENTS.md](services/AGENTS.md) |
| `deploy/` | Compose de la station, scripts de l'hôte, dossier partagé | [deploy/AGENTS.md](deploy/AGENTS.md) |
| `docs/` | La documentation, en français | [docs/README.md](docs/README.md) |
| `scripts/` | Banc local (`dev.sh`), parcours dans un navigateur (`e2e.sh`) et vérifications (`verifier.sh`) | ce fichier |

Pour comprendre le tout : [docs/architecture.md](docs/architecture.md). Pour le vocabulaire : [docs/glossaire.md](docs/glossaire.md).

## Avant de commencer

1. Lire la tâche, puis sa fiche dans la [feuille de route](docs/feuille-de-route/README.md) si elle en a une. La fiche dit quels fichiers elle touche.
2. Partir d'un arbre propre et d'une suite verte : `git status`, puis `./scripts/verifier.sh` sur la partie touchée.
3. Travailler sur une branche, jamais sur `main`. Plusieurs agents en même temps : un worktree chacun, et les règles de [docs/travailler-a-plusieurs.md](docs/travailler-a-plusieurs.md).

## Pendant

- Faire le plus petit changement qui remplit la fiche. Si une question de produit surgit, s'arrêter et la poser.
- Lire le code et ses tests avant de les changer. Suivre le style du code autour : nommage, densité des commentaires, idiomes.
- Ne pas mélanger deux sujets dans un commit. Un problème vu en passant va dans la feuille de route, pas dans le diff.

## Avant de rendre

`./scripts/verifier.sh` passe, sans option, ou sur les parties touchées. Puis :

- [ ] Ce qui change a des tests, et ils sont verts.
- [ ] Une route du moteur ajoutée ou changée : la console suit dans la même branche, [docs/api.md](docs/api.md) aussi, et la route est dans la liste de nginx (`console/docker/nginx.conf.template`). Le test `console/src/api/nginxRoutes.test.ts` vérifie ce dernier point.
- [ ] Le schéma de la base change : une nouvelle migration, avec son test dans `engine/tests/test_migrations.py`.
- [ ] Une ligne dans [CHANGELOG.md](CHANGELOG.md), sous « Non publié ».
- [ ] Les docs touchées par le changement sont à jour.
- [ ] Une nouvelle dépendance a une licence compatible avec l'AGPL, vérifiée avant l'ajout. Une police, une icône ou un son embarqués sont listés dans [AUTHORS.md](AUTHORS.md).
- [ ] Une fonction risquée a un interrupteur : [ADR 0009](docs/decisions/0009-interrupteurs.md).

## Les règles fixes

- **Aucune donnée de station dans ce dépôt** : pas de secret, de mot de passe, d'adresse IP, de nom d'hôte, de domaine ni de compte réel. Les exemples utilisent `radio.example` et des valeurs `change-me`. Les deux `brand.json` en contiennent encore : la fiche GEN-02 les retire, n'en ajoute pas.
- **Une migration publiée ne se modifie jamais.** Une évolution du schéma est une nouvelle migration, qui sait se défaire.
- **L'API JSON est un contrat** entre le moteur et la console : [ADR 0010](docs/decisions/0010-moteur-et-console-se-deploient-a-part.md).
- **Le moteur reste un fork mince de Radiotomate.** Le paquet garde son nom, `radiotomate`. Les fichiers de l'amont restent en anglais.
- **`radiotomate-playout` ne redémarre jamais seul** : l'interface et le scheduler partagent son réseau. On recrée les trois ensemble.
- **L'interface est en français**, en thème clair et sombre, au clavier et sur téléphone. Elle n'échoue jamais en silence.
- **Pas de push, de déploiement, ni d'accès à une machine de station sans demande explicite.** Une autorisation vaut pour une action, pas pour la suite.
- **Ajouter les fichiers un par un** : jamais `git add -A` ni `git add .`. Des fichiers locaux non suivis traînent dans l'arbre, comme les réglages d'outils ou `.claude/launch.json`.

## Commits

Un commit par sujet. Le message est en français, `Zone : résumé`, puis le pourquoi en quelques lignes. Zones déjà utilisées : Moteur, Console, Antenne, Programmation, Agenda, Sons, Médiathèque, Services, Déploiement, CI, Docs.

## Où chercher

| Question | Page |
|---|---|
| Comment tout tient ensemble | [docs/architecture.md](docs/architecture.md) |
| Ce que veut dire un mot | [docs/glossaire.md](docs/glossaire.md) |
| Pourquoi c'est fait ainsi | [docs/decisions/](docs/decisions/README.md) |
| Pour qui c'est fait, et ce qui les freine | [docs/personas/](docs/personas/README.md) |
| Ce qui reste à faire, et dans quel ordre | [docs/feuille-de-route/](docs/feuille-de-route/README.md) |
| Travailler à plusieurs, les pièges déjà rencontrés | [docs/travailler-a-plusieurs.md](docs/travailler-a-plusieurs.md) |
| Lancer le banc et vérifier | [docs/developpement.md](docs/developpement.md) |

## Graphe du code

Le bloc suivant vaut si l'outil `code-review-graph` est installé et branché à l'agent. Sinon, chercher avec `git grep` ou `rg`. Le graphe décrit la copie où il a été construit : dans un worktree, vérifier dans les fichiers du worktree.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**This project has a knowledge graph. Start with the code-review-graph
MCP tools to narrow scope, then read the source.** The graph is cheaper than scanning files and
gives you structural context (callers, dependents, test coverage) that file search cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

### Verify in the source

- Narrow scope with the graph, then read the source. Do not change code from graph output alone.
- For any non-trivial change, read the implementation and the relevant tests before concluding.
- Verify the exact source when touching behavior, database logic, migrations, retries, fallbacks,
  recovery, or compatibility code.
- When the graph and the source disagree, the source wins. The graph may be stale or may not
  model that relationship.
- An empty graph result can mean "not indexed" or "not statically visible", not "does not exist".

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review — token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.
<!-- /code-review-graph MCP tools -->
