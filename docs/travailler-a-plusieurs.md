# Travailler à plusieurs

Comment plusieurs agents, ou plusieurs personnes, font avancer BUTTON en même temps sans se marcher dessus. Les règles de base sont dans le [AGENTS.md](../AGENTS.md) de la racine. Les tâches sont dans la [feuille de route](feuille-de-route/README.md).

## Le principe

Une fiche, une branche, un worktree, un agent. Les fiches sont petites, S ou M. Une fiche ne commence que si ses conflits ne recoupent pas ceux d'une fiche en cours.

## Ouvrir un worktree

```bash
git worktree add ../button-sec-01 -b fiche/SEC-01-catalogue main
cd ../button-sec-01
(cd engine && poetry install && poetry run radiotomate develop)
(cd console && npm install)
```

Si la fiche touche les services, ajouter une fois :

```bash
python3 -m venv services/catalog/.venv
services/catalog/.venv/bin/pip install -r services/catalog/requirements.txt
```

Chaque worktree a son propre environnement, ignoré par git : l'environnement Poetry du moteur, `console/node_modules`, `services/catalog/.venv` et `engine/radio_data/`, qui porte la base de démo. Claude Code peut aussi créer ses worktrees lui-même, dans `.claude/worktrees/`, également ignoré par git.

Après la fusion :

```bash
git worktree remove ../button-sec-01
git branch -d fiche/SEC-01-catalogue
```

## Ce qui ne se partage pas sur une machine

| Ressource | Pourquoi | Que faire |
|---|---|---|
| Ports 6811, 6822 et 6833 | Écrits en dur dans le moteur | Un seul moteur de démo par machine. `scripts/dev.sh` refuse de démarrer si 6811 est pris. Voir DEV-01 |
| Port 5175 | La console de dev le prend en `strictPort` | Une deuxième console, branchée sur le même moteur : `npx vite --port 5176 --strictPort` |
| Projet Compose `button` | Deux `docker compose up`, depuis deux worktrees, se marchent dessus | `docker compose -p <nom>` et d'autres ports, ou une seule station de test à la fois |
| Le graphe du code | Il décrit la copie où il a été construit | Voir [plus bas](#le-graphe-du-code) |

Les tests, eux, tournent en parallèle sans souci : pytest travaille dans des dossiers temporaires, et les tests de la console n'ouvrent aucun port.

## Les fichiers qui se disputent

| Fichier | Pourquoi | La règle |
|---|---|---|
| `engine/radiotomate/commands/update/vNN.py` | Deux branches prennent le même numéro | La deuxième à fusionner renumérote la sienne : [ADR 0006](decisions/0006-le-paquet-reste-radiotomate.md) |
| `docs/api.md`, `console/src/api/types.ts` | Chaque route y passe | Ne toucher que sa section, et rebaser avant de fusionner |
| `console/docker/nginx.conf.template` | La liste des routes tient sur une ligne | Une fiche à la fois |
| `deploy/compose.yml`, `deploy/.env.example` | Chaque service, chaque variable | Une fiche à la fois |
| `engine/radiotomate/interface_app.py` | La liste des blueprints | Ajouter sa ligne à la fin |
| `console/src/App.tsx`, `engine/radiotomate/interface/spa.py` | Les pages de premier niveau | Les deux dans la même fiche |
| `CHANGELOG.md` | Tout le monde y écrit | Une ligne à la fin de « Non publié ». Un conflit s'y règle en gardant les deux lignes |
| Les tableaux de la feuille de route | Tout le monde y passerait | Seule la personne qui fusionne les modifie |
| `console/src/pages/ImporterPage.tsx`, `lib/useMonitor.ts`, `components/agenda/DiffusionDialog.tsx`, `pages/AntennePage.tsx`, `pages/AgendaPage.tsx`, `pages/SemainePage.tsx` | Des centaines de lignes, beaucoup de dépendances | Un agent à la fois sur chacun |
| `engine/radiotomate/scheduler/clock.py` (`tick`), `scheduler/rundown.py` (`build_rundown`) | Toute l'antenne en dépend | Un agent à la fois, et les tests du scheduler en entier avant de fusionner |

## Rendre une fiche

1. Rebaser sur `main`.
2. `./scripts/verifier.sh` sur tout, pas seulement sur la partie touchée : un rebase peut casser ailleurs.
3. Relire son diff : rien d'une station, pas de fichier de travail, pas de trace de débogage.
4. Faire relire par un agent qui n'a pas le contexte de l'auteur, par exemple avec `/code-review` dans Claude Code. La relecture part du diff et de la fiche, pas du résumé de l'auteur.
5. La personne qui fusionne met à jour le tableau de la feuille de route.

## Le graphe du code

L'outil `code-review-graph`, s'il est installé, garde un graphe du code dans `.code-review-graph/`, ignoré par git. Un hook de commit le met à jour. Dans Claude Code, un hook le met aussi à jour après chaque écriture.

`code-review-graph install` écrit aussi des réglages pour chaque outil d'agent : `.mcp.json`, `.claude/settings.json`, `.claude/skills/`, `.cursor/`, `GEMINI.md`, `.github/instructions/` et d'autres. Ils ne sont pas versionnés, car ils dépendent de la machine : `.mcp.json` porte un chemin absolu. Pour ne plus les voir dans `git status`, les lister dans `.git/info/exclude`, qui vaut pour la copie et ses worktrees.

Le graphe décrit la copie où il a été construit. Dans un worktree, le hook de commit ne fait rien, sauf avec `CRG_HOOK_WORKTREES=1`, et le serveur de l'outil peut répondre pour la copie principale. Dans un worktree, toujours vérifier dans les fichiers du worktree.

## Les pièges déjà rencontrés

**Routes et pages**

- Une route du moteur absente de la liste de nginx marche en dev, par le proxy de Vite, et reçoit en prod la page HTML de la console. `console/src/api/nginxRoutes.test.ts` le vérifie maintenant.
- Une page de premier niveau de la console s'ajoute aussi dans `engine/radiotomate/interface/spa.py`.
- Une console plus récente que son moteur reçoit un 404 sur une route nouvelle : [ADR 0010](decisions/0010-moteur-et-console-se-deploient-a-part.md).

**Moteur**

- `radiotomate update` sert aux migrations. Une commande d'exploitation va sous `radiotomate maintenance …`.
- Dans un service, une fonction nommée `update` masque le `update` de SQLAlchemy : importer `update as sql_update`. ruff le signale (F811).
- Les tables historiques stockent l'heure locale, l'Agenda de l'UTC naïf : [ADR 0008](decisions/0008-deux-conventions-d-heure.md). De plus, Liquidsoap donne l'heure murale avec un décalage `%z` parfois faux en été : `now_from_live` l'ignore exprès.
- Liquidsoap 2.4 ne fond pas les transitions de `fallback` (savonet/liquidsoap#4179).
- `liquidsoap --check` exige un `RTCONFIG` minimal. Sans lui, le contrôle échoue pour une mauvaise raison. `scripts/verifier.sh liquidsoap` le fournit.

**Console**

- En dev, le mode strict de React lance les effets deux fois. Une instance Uppy se garde au niveau du module, sans destruction au nettoyage.
- Une heure de l'Agenda s'affiche à Paris dans la console, et à l'heure locale chez l'invité. Toujours passer par les fonctions du domaine, jamais par `Date` brut.

**Services et déploiement**

- tusd 2.8 envoie ses hooks sans en-tête `Hook-Name`, avec un corps `{"Type", "Event": {"Upload", "HTTPRequest"}}`. Lire le type avec `hook_event`.
- `radiotomate-playout` ne redémarre jamais seul : l'interface et le scheduler partagent son réseau. Voir ARC-01.
- Docker contourne le pare-feu ufw. Vérifier les ports depuis une autre machine, pas avec `ufw status`.
- Les images ne sont construites que pour `linux/amd64` : une machine ARM ne les lance pas.
- Le projet Compose s'appelle `button`. Le renommer recrée vides les volumes `button_tusd-data` et `button_share-private`.
- La CI publie les images sous le propriétaire du dépôt. Transférer le dépôt change donc le registre, sans aucune erreur visible.
- Un contrôle sans compte ne peut pas lire `/antenne/state.json`. Il lit les `/health/ready` de l'interface et du scheduler.
- Pour valider nginx dans Docker sur macOS, le gabarit passe par l'entrée standard : le dossier temporaire du Mac n'est pas toujours monté dans la VM. `scripts/verifier.sh nginx` le fait.

**Outils**

- Chercher la marque : `button` en minuscules attrape aussi l'élément HTML `<button>`. Chercher `BUTTON` en majuscules.
- Sur macOS, `\b` ne marche pas dans `git grep -E` et rend des comptes faux sans erreur. Utiliser `-w`, ou `(^|[^a-z_])` devant le mot.
- macOS vide tout seul `/private/tmp`. Rien d'utile ne doit rester dans un dossier temporaire : un script de travail qui compte va dans le dépôt, ou nulle part.
- `git add -A` ramasse des fichiers locaux non suivis, comme les réglages d'outils ou `.claude/launch.json`. Ajouter les fichiers un par un.
