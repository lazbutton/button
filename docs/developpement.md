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
| `donnees` | `git grep` des adresses IP privées, des noms en `.ts.net`, des clés privées et des jetons, puis des motifs de la station ([plus bas](#aucune-donnée-de-station)) | git |
| `moteur` | `ruff check`, `ruff format --check`, puis `pytest` avec `TZ=Europe/Paris`, sans `tests/interface` ni `tests/e2e` | Poetry |
| `liquidsoap` | `liquidsoap --check engine/playout/radiotomate.liq`, avec un `RTCONFIG` minimal | Docker |
| `console` | `npm test`, puis `tsc` et `vite build` | Node 22, `npm install` fait |
| `services` | les dix tests du catalogue listés dans `services.yml` | `services/catalog/.venv`, voir plus bas |
| `nginx` | `nginx -t` sur `console/docker/nginx.conf.template` et ses en-têtes de sécurité, rendus par le script de démarrage de l'image | Docker |
| `deploy` | `docker compose config` avec `.env.example`, puis ShellCheck s'il est installé | Docker |
| `e2e` | les parcours dans un navigateur, par `scripts/e2e.sh` ([plus bas](#les-parcours-dans-un-navigateur)) | Node 22 et Poetry, `npm install` et `poetry install` faits |

Sans argument, une partie à qui il manque un outil est sautée, et le résumé le dit. Nommée, elle échoue.

Sans argument, les parcours tournent aussi : la CI les lance sur chaque pull request qui touche la console ou le moteur, et un parcours cassé doit se voir avant elle. Ils prennent quelques minutes. Pour vérifier vite une partie, la nommer : `./scripts/verifier.sh moteur console`.

Les dépendances du catalogue vont dans un environnement à part, une fois :

```bash
python3 -m venv services/catalog/.venv
services/catalog/.venv/bin/pip install -r services/catalog/requirements.txt
```

Les tests Playwright des pages HTMX de l'amont ne tournent pas en CI : `cd engine && poetry run playwright install chromium`, une fois, puis `poetry run pytest tests/interface`.

## Aucune donnée de station

La partie `donnees` cherche ce qui ne doit jamais entrer dans le dépôt : une adresse IP privée, un nom en `.ts.net`, une clé privée, un jeton GitHub ou GitLab. Les adresses privées sont celles de la RFC 1918, et celles de Tailscale, en IPv4 dans la plage de la RFC 6598 comme en IPv6. Une de ces plages entière, comme `10.0.0.0/8` dans une liste de proxys de confiance, n'est l'adresse de personne : elle passe. Elle lit les fichiers suivis par git, et les nouveaux fichiers qu'il n'ignore pas, sans tenir compte de la casse. Un fichier que git tient pour binaire n'est pas lu. La CI la lance sur chaque pull request et sur `main`, quels que soient les fichiers touchés ([`donnees.yml`](../.github/workflows/donnees.yml)).

Le rapport donne le fichier, la ligne et ce qui est trouvé, jamais la donnée : le journal de la CI est public. Pour un exemple : `radio.example`, `change-me`, ou une adresse de `192.0.2.0/24`, réservée à la documentation (RFC 5737). Un test qui a besoin d'une adresse privée la construit au moment de tourner, par exemple à partir d'une plage entière, ou passe par une exception.

Ce qui est propre à une station, comme son domaine, le nom de ses machines ou de ses comptes, va dans `.motifs-station`, à la racine du dépôt. Git l'ignore : la liste de ces motifs est elle-même une donnée de la station. Un motif par ligne, en expression étendue comme pour `git grep -E`, sans tenir compte de la casse. Une ligne qui commence par `#` est un commentaire. Un worktree sans motif à lui prend ceux de la copie principale.

Les exceptions sont dans `scripts/verifier.sh`, dans `exceptions_donnees`, chacune avec un commentaire qui dit pourquoi : un fichier, jamais un dossier, ce qu'elle y laisse passer, comme `adresse IP privée`, puis le motif des lignes concernées, jamais une donnée de station. Les motifs de la station n'ont pas d'exception. Une exception qui ne laisse plus rien passer fait échouer la partie : elle se retire.

## Les parcours dans un navigateur

Les parcours de la console passent par un vrai navigateur, avec [Playwright](https://playwright.dev/) :

```bash
./scripts/e2e.sh                          # tous les parcours
./scripts/e2e.sh e2e/antenne.spec.ts      # un fichier : les arguments vont à Playwright
./scripts/e2e.sh --headed                 # en voyant le navigateur
```

Il faut `poetry install` dans `engine/` et `npm install` dans `console/`, rien d'autre. Au premier lancement, Playwright télécharge Chromium, une fois par machine, hors du dépôt (`~/Library/Caches/ms-playwright` sur macOS). Sous Linux, les bibliothèques dont il a besoin s'installent avec `cd console && npx playwright install-deps chromium`, qui demande les droits d'administration. `./scripts/verifier.sh` les lance aussi, partie `e2e`, et la CI sur chaque pull request qui touche `console/` ou `engine/` ([`e2e.yml`](../.github/workflows/e2e.yml)).

Le script monte un banc à part, dans `.e2e/<date>-<pid>/`, ignoré par git :

| Pièce | Ce que c'est |
|---|---|
| Moteur | l'interface en mode démo (`radiotomate interface --demo --port …`), sur une base semée par `engine/tests/e2e/seed.py` : un compte par rôle, des carts, une horloge pour toute la semaine, et une petite banque pour `MEDIA_ROOT` |
| Comptes | `comptes.json` : `admin`, `programmateur` et `animateur`, avec un mot de passe tiré à chaque lancement |
| Faux services | `console/e2e/stubs/` : le catalogue (recherche et fichiers de la banque) et tusd (envois tus), sans Meilisearch ni Docker. Comme en prod, ils demandent au moteur une session ou, pour tusd, le lien d'un invité |
| Console | le build de production, servi par `vite preview`, qui relaie comme nginx : les routes du moteur lues dans `console/docker/nginx.conf.template`, `/library` vers le catalogue, `/tus` vers tusd |

Chaque pièce prend un port libre, jamais ceux du banc de dev : deux lancements tournent en même temps, et à côté de `scripts/dev.sh`. Dans un lancement, les parcours passent un par un, dans un seul navigateur.

Tout s'arrête à la fin, même après un échec ou un `Ctrl-C`. Si tout passe, le dossier du lancement est effacé. Sinon il reste, avec le journal de chaque pièce (`moteur.log`, `console.log`…) et, dans `resultats/`, les captures et les traces d'un parcours raté. Pour rejouer une trace : `cd console && npx playwright show-trace ../.e2e/<lancement>/resultats/<parcours>/trace.zip`. Rien ne purge ces dossiers : `rm -rf .e2e` les efface tous, quand aucun lancement ne tourne.

En CI, un lancement raté garde les mêmes journaux, captures et traces dans un artefact du job, `parcours-1`, en bas du résumé de l'exécution ; le chiffre est celui de la tentative. Il reste 14 jours. Il contient le dossier du lancement. Pour rejouer une trace : décompresser l'artefact, puis `cd console && npx playwright show-trace <artefact>/<lancement>/resultats/<parcours>/trace.zip`.

Les parcours, dans `console/e2e/` :

| Fichier | Ce qu'il vérifie |
|---|---|
| `antenne.spec.ts` | se connecter, puis voir l'antenne |
| `accessibilite.spec.ts` | chaque écran et chaque onglet passés à axe-core, avec les menus et les panneaux de l'antenne, une confirmation rouge et deux incidents ouverts simulés par `page.route` : en clair et en sombre avec le compte admin, puis la barre latérale repliée et la largeur d'une tablette, et sur un téléphone avec l'animateur |
| `barre.spec.ts` | la barre du haut : ce qui passe, et le dernier titre connu quand le moteur ne répond plus, l'état de l'antenne et son détail, le casque et sa source, un flux muet, qui s'arrête ou qui ne répond jamais, en PCM comme par l'élément audio, le menu du compte, le lien « Code source » |
| `pupitre.spec.ts` | Espace, `/` et Entrée, la pré-écoute, « Diffuser », déplacer une ligne au clavier et à la souris, retirer puis annuler, le focus rendu à « Passer en direct » |
| `etats.spec.ts` | session expirée, droit manquant, moteur injoignable, moteur muet, moteur arrêté derrière nginx (502 en HTML), envoi trop lourd pour nginx (413 en HTML) et route absente, puis les gestes refusés ou sans réponse de la page Automate, simulés par `page.route` devant le moteur de démo et le faux catalogue |
| `bacs.spec.ts` | « Diffuser maintenant » sur un bac sans son prêt : la console dit que rien n'est parti |
| `roles.spec.ts` | ce que voient l'animateur, le programmateur et l'admin |
| `apparence.spec.ts` | le thème clair et le sombre, choisis dans le menu du compte ou suivant l'appareil |
| `telephone.spec.ts` | la console sur un téléphone de 360 px, au doigt |
| `station.spec.ts` | l'onglet Station de l'admin : un nom enregistré passe sans recharger dans le titre de l'onglet et la barre de navigation, et tient après un rechargement ; face à un moteur sans ces routes (404), la console garde `brand.json` ; une valeur refusée se dit sous son champ, qui prend le focus |

Un défaut connu de la console garde son parcours en `test.fixme`, avec la raison en commentaire : Playwright le saute. Pour le voir échouer, remplacer `test.fixme` par `test` le temps d'un lancement.

Un parcours échoue aussi sur un défaut d'accessibilité grave ou critique, au sens d'[axe-core](https://github.com/dequelabs/axe-core) : `banc.ts` passe axe sur la page où finit chaque parcours, et `accessibilite.spec.ts` passe chaque écran. Le rapport donne, pour chaque élément en défaut, la règle d'axe, son sélecteur et ce qui ne va pas. L'analyse se fait sans animation, une fois finies celles en cours : un menu qui s'ouvre encore fausserait les contrastes. Un défaut se corrige dans la console. `e2e/accessibilite.ts` peut en excuser un gardé en connaissance de cause, avec sa raison en commentaire : `DEFAUTS_CONNUS` par règle d'axe et par sélecteur, `TEXTES_PALES` par couleur de texte. Les deux listes sont vides : les défauts relevés à l'arrivée d'axe sont corrigés. Attention : une couleur de texte listée est excusée partout, même sur un écran neuf. Un défaut qui ne se voit qu'une fois, le temps que le moteur de démo fasse bouger la page, n'est pas rapporté : chaque page en défaut est analysée deux fois. axe ne voit pas un texte écrit par le CSS (`content`), comme le badge du nombre d'incidents : `contraste(élément)`, de `e2e/accessibilite.ts`, mesure son rapport de contraste avec son fond.

Un parcours s'écrit dans `console/e2e/<sujet>.spec.ts`. Il importe de `e2e/banc.ts` :

- `test` et `expect`. `test` fait échouer un parcours sur toute erreur JavaScript de la page, et sur un défaut d'accessibilité grave ou critique de la page où il finit. Pour vérifier un état en cours de route, un menu ouvert par exemple : `verifierAccessibilite(page, écran)`, de `e2e/accessibilite.ts`. `test` coupe aussi ce qui sortirait du banc : `brand.json` nomme le flux d'une vraie station, que le casque demande dès l'ouverture. Une requête vers un autre site échoue, et un lien vers un autre site ouvre une page vide à son adresse. Un parcours qui a besoin du flux le sert lui-même par `page.route`, qui passe avant le banc, comme dans `barre.spec.ts` ;
- `seConnecter(page, rôle)`, pour entrer avec un compte semé, ou `remplirLaConnexion(page, rôle)` quand l'écran de connexion est déjà affiché ;
- `antenne`, `file` et `bibliotheque`, les trois régions du pupitre, `avis` pour un message de la console annoncé comme un état, `alerte` pour un message annoncé comme une alerte, et `tenirLAntenne`.

Un parcours trouve les éléments par leur rôle et leur nom accessible, jamais par une classe CSS. Un parcours neuf se vérifie une fois : casser dans la console ce qu'il vérifie, le voir échouer, puis défaire.

Un parcours n'attend pas pour de vrai une minuterie de la console, comme les 8 s que le casque laisse au flux. Il pose `page.clock.install()` avant d'ouvrir la page, puis avance l'horloge avec `page.clock.fastForward()`, comme dans `barre.spec.ts`. `page.clock.runFor()` déroule aussi chaque image des animations : le parcours devient bien plus lent.

Le moteur de démo est partagé par tous les parcours d'un lancement, et il enchaîne seul les titres de son horloge. Un jingle n'y dure que 4 s : la file bouge à chaque fin de titre. Un parcours qui touche à la file appelle d'abord `tenirLAntenne(page)`, qui passe au titre suivant jusqu'à en trouver un qui tient l'antenne une minute. Après un « Suivant », le moteur de démo est en avance sur son horloge, et il date une ligne mise à la suite de l'heure de l'appui : la file la range parmi ce qui est passé. Pour ce geste, un parcours lit la demande envoyée au moteur, pas la file.

Sur `main`, la CI publie aussi les images Docker, seulement si tout est vert.

## Dépendances, licences et failles

Dependabot propose chaque mois les mises à jour ([`.github/dependabot.yml`](../.github/dependabot.yml)) : les actions GitHub, les dépendances de la console, du catalogue et du moteur, et les images de base des sept images. Pour le moteur, il ne déplace que `poetry.lock` : les contraintes de `pyproject.toml` suivent Radiotomate et Liquidsoap, et changent à la main. Quand il monte la version de Python d'une image de base, `python-version` des workflows suit à la main ; pour Liquidsoap, le job `liquidsoap-check` d'`engine.yml` et `scripts/verifier.sh`.

### Les licences

Chaque dépendance npm ou Python livrée avec BUTTON, dans le build de la console ou dans une image, a une licence compatible avec l'AGPL. Les licences acceptées, et pourquoi, sont dans [`scripts/licences.toml`](../scripts/licences.toml). La CI les contrôle sur chaque pull request qui touche un fichier de dépendances ([`licences.yml`](../.github/workflows/licences.yml)). Les outils de développement ne sont pas livrés : ils ne sont pas contrôlés.

`scripts/verifier.sh` ne le lance pas encore. Le même contrôle, sur cette machine :

```bash
python3 scripts/licences.py npm console/package-lock.json engine/sass/package-lock.json
(cd engine && poetry run python ../scripts/licences.py poetry poetry.lock)
services/catalog/.venv/bin/python scripts/licences.py pip
```

Il échoue sur une licence refusée, et sur une licence inconnue ou qui ne se lit pas. Une licence inconnue se vérifie, puis entre dans `licences.toml`, acceptée ou refusée, avec sa raison. Une exception ajoutée par `WITH` aussi : seules celles qui donnent des droits en plus sont acceptées. Un paquet dont les métadonnées ne disent pas la licence entre dans `[paquets]`, à sa version, une fois sa licence vérifiée à la main.

Le moteur se contrôle dans son environnement Poetry. Un paquet que `poetry.lock` réserve à une autre plateforme, ou à une autre version de Python, n'y est pas installé : le contrôle le saute, et le dit. La CI, elle, prend le Python de l'image, 3.13.

### Les failles des images

Trivy analyse chaque image juste après sa publication depuis `main`, et les sept images `:main` chaque lundi ([`failles.yml`](../.github/workflows/failles.yml)). Le job échoue sur toute faille critique. Il passe après la publication, jamais avant : une station qui suit `main` reçoit ses correctifs, même quand une faille reste ouverte.

Devant un job rouge :

- **Un correctif existe** : prendre la mise à jour qui l'apporte, une image de base plus récente ou un `poetry.lock` à jour. Quand l'image de base a déjà le correctif, relancer le workflow de l'image sur `main` (« Run workflow ») la reconstruit. Un paquet installé par le Dockerfile, comme ffmpeg et ce qu'il tire, garde en revanche sa version du cache de build tant que l'image de base ne change pas : vider d'abord le cache des Actions (`gh cache delete --all`), puis relancer.
- **Aucun correctif** : accepter la faille dans [`.trivyignore.yaml`](../.trivyignore.yaml), pour les seuls paquets touchés (`purls`), avec sa raison (`statement`) et une expiration à 90 jours au plus (`expired_at`). Passé cette date, le job échoue de nouveau : revoir la faille, puis repousser la date ou corriger.

Le job vérifie aussi que chaque faille acceptée a ses paquets, sa raison et une expiration à 90 jours au plus. Pour analyser une image à la main : « Run workflow » sur `failles`, avec sa référence complète (`ghcr.io/lazbutton/button-console:main`) ; sans référence, les sept images `:main`. Trivy est épinglé dans `failles.yml`, version et empreinte, et Dependabot ne le suit pas : le monter à la main, avec l'empreinte de `trivy_<version>_checksums.txt`.

## Règles du projet

Elles sont dans le [AGENTS.md](../AGENTS.md) de la racine, communes aux personnes et aux agents, et dans le `AGENTS.md` de chaque dossier. Les plus importantes :

- **L'API JSON est un contrat.** Une route du moteur ne change de forme qu'avec la console, dans la même branche, et [`docs/api.md`](api.md) suit. Une route nouvelle entre dans la liste de nginx : un test le vérifie.
- **Le moteur reste un fork mince.** Les changements y sont minimaux et rétro-compatibles. Le script Liquidsoap s'amende, il ne se réécrit pas. Voir [`engine/FORK.md`](../engine/FORK.md).
- **Le schéma de la base ne recule jamais.** Toute évolution est une nouvelle migration, et une migration publiée ne se modifie plus.
- **Aucune donnée de station dans le dépôt** : ni secret, ni adresse, ni compte réel. La partie `donnees` le vérifie, en CI aussi.
- **L'interface est en français**, en thème clair et sombre, utilisable au clavier et sur téléphone.
- **Un commit par sujet.** Le message dit ce qui change, puis pourquoi.

## Écrire une migration

1. Ajouter `engine/radiotomate/commands/update/vNN.py`, avec le numéro libre suivant, `async def upgrade(conn)` et `async def downgrade(conn)`. La dernière publiée est v18. Chacune passe dans sa propre transaction, clés étrangères coupées : ni `commit` ni `VACUUM`, et une suppression ne cascade plus. Le détail est dans [`engine/AGENTS.md`](../engine/AGENTS.md#migrations).
2. Mettre à jour le modèle SQLAlchemy concerné, dans le même commit.
3. Ajouter son test dans `engine/tests/test_migrations.py` : une base de la version d'avant, avec des données, qui monte puis redescend.
4. Vérifier l'aller-retour sur une copie de base : `radiotomate update --target-version N-1`, puis `radiotomate update`.

`radiotomate-init` applique les migrations à chaque démarrage. Revenir à une image plus ancienne demande donc de redescendre d'abord le schéma : voir [`deploiement.md`](deploiement.md#revenir-en-arrière).
