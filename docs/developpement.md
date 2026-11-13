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
| `licences` | les tests de `scripts/licences.py`, puis les licences des paquets npm, du moteur et du catalogue ([plus bas](#les-licences)) | Python 3.11 ou plus et Poetry, `poetry install` fait, `services/catalog/.venv` |
| `moteur` | `ruff check`, `ruff format --check`, puis `pytest` avec `TZ=Europe/Paris`, sans `tests/interface` ni `tests/e2e` | Poetry |
| `liquidsoap` | `liquidsoap --check engine/playout/radiotomate.liq`, avec un `RTCONFIG` minimal | Docker |
| `antenne` | le script du playout joué pour de bon, par `engine/playout/tests/antenna.py` ([plus bas](#lantenne)) | Docker, Python 3 |
| `conducteur` | le vrai scheduler et la vraie interface devant le vrai Liquidsoap, et l'heure du conducteur comparée à l'antenne, par `engine/playout/tests/rundown.py` ([plus bas](#le-conducteur-devant-lantenne)) | Docker, Python 3 |
| `console` | `npm test`, puis `tsc` et `vite build` | Node 22, `npm install` fait |
| `services` | les seize tests du catalogue listés dans `services.yml`, puis `test_compose.py` avec le Compose v2 de la CI, si Docker tourne | `services/catalog/.venv`, voir plus bas |
| `nginx` | `nginx -t` sur `console/docker/nginx.conf.template` et ses en-têtes de sécurité, rendus par le script de démarrage de l'image | Docker |
| `deploy` | `docker compose config` avec `.env.example`, aussi sur le `compose.yml` d'une station, sans ses `build:`. Puis ShellCheck sur les scripts du dépôt, et les tests `bats` de `deploy/station`, comme la CI | Docker, Python 3 |
| `version` | les tests de `scripts/version.py`, qui lisent aussi le CHANGELOG et `compose.yml`, puis les lignes du CHANGELOG ajoutées depuis `origin/main` ([plus bas](#publier-une-version)) | Python 3 |
| `e2e` | les parcours dans un navigateur, par `scripts/e2e.sh` ([plus bas](#les-parcours-dans-un-navigateur)) | Node 22 et Poetry, `npm install` et `poetry install` faits |

Sans argument, une partie à qui il manque un outil est sautée, et le résumé le dit. Nommée, elle échoue.

Sans argument, les parcours tournent aussi : la CI les lance sur chaque pull request qui touche la console ou le moteur, et un parcours cassé doit se voir avant elle. Ils prennent quelques minutes. Pour vérifier vite une partie, la nommer : `./scripts/verifier.sh moteur console`.

La partie `deploy` passe ShellCheck avec l'image et sur la liste de [`shellcheck.yml`](../.github/workflows/shellcheck.yml), le workflow qui lance le même contrôle en CI, sur chaque pull request qui touche un script. La liste prend `scripts/`, `deploy/station` et ses tests, `deploy/scripts/`, `deploy/share/entrypoint.sh` et les scripts de démarrage des images de la console et d'Icecast. Un script ailleurs s'y ajoute, sinon personne ne le vérifie.

Les tests de `deploy/station` tournent avec `bats`, dans l'image officielle, épinglée dans [`station.yml`](../.github/workflows/station.yml), le workflow qui les lance en CI. De faux outils y jouent la machine : `docker`, `curl`, `apt-get`, `ss`… Voir [deploy/AGENTS.md](../deploy/AGENTS.md#la-commande-station). `engine/dev.sh` et `engine/install.sh` viennent de l'amont, Radiotomate : ils restent dehors. L'image est épinglée, et Dependabot ne la suit pas : la monter à la main, puis corriger ce que la nouvelle version signale.

Le même workflow fait aussi une vraie installation, le job `install`, sur un runner Ubuntu 24.04 : ce que les faux outils ne voient pas. Il la fait dans deux cas, côte à côte :

- `neuf` : le runner est rendu semblable à un VPS neuf, sans Docker. `station install` l'installe alors depuis le dépôt de Docker ;
- `deja-la` : le runner garde son Docker, comme un VPS qui l'avait déjà, et `station install` n'installe rien. Son Compose est un v2, 2.38, comme celui qu'une station peut encore avoir : un avertissement le dit, s'il ne l'est plus.

Dans les deux cas, le runner garde l'ACL par défaut de `/opt`, ouverte à tous les comptes, que `station install` doit tenir à l'écart de `.env` et du dossier de la station. Le job fabrique l'archive d'une station depuis la branche, comme pour une version (`scripts/version.py station main`). Puis il lance `station install --from`, avec `--tls internal` et les images `:main` du registre. Il vérifie ensuite :

- le contrôle de la station, `smoke.sh`, sur les ports locaux ;
- `.env`, en droits 600 ; le dossier de la station, en 755 et sans ACL ; la commande `station`, dans `/usr/local/bin` ;
- le mot de passe admin : sans terminal, il reste dans `.env`, et la sortie ne le montre pas ;
- la relance : `sudo station install --from …` ne change ni un fichier du dossier, hors `data/` et `media/`, ni un conteneur ;
- les commandes de la station, le critère de la fiche INS-03 :
  - `station status`, puis un compte, une horloge, une émission, un direct de l'Agenda, un réglage et un son ajoutés ;
  - `station backup`, puis `station backup --with-media` hors du dossier, en droits 600 ;
  - `station uninstall --purge`, qui ne laisse ni dossier, ni commande, ni conteneur ;
  - une installation neuve, comme sur une autre machine, puis `station restore` : la station doit avoir les mêmes comptes, horloges, émissions, Agenda et réglages, d'après une empreinte de leurs lignes, et le même son. Le mot de passe admin de la sauvegarde doit ouvrir une session, par la console. Ni l'archive, ni aucune sortie ne doit le montrer.
- la sauvegarde hors de la machine, le critère de la fiche SAV-01, vers un stockage du runner, sans compte réel : le serveur S3 de rclone dans `neuf`, son serveur SFTP dans `deja-la`, avec l'image de rclone que la station épingle déjà. En SFTP, la clé SSH de la station est autorisée après un premier refus, comme sur un vrai stockage :
  - `station config --backup-remote`, avant `uninstall --purge`, puis les minuteurs, activés ; systemd lance la sauvegarde de la nuit et le test du mois par les services de leurs minuteurs, qui doivent réussir ;
  - `station restore --remote --list`, et `station status` ;
  - `uninstall --purge` retire aussi les minuteurs. Une fois la station remise de son archive, la machine se perd encore : une installation neuve reprend le dépôt, avec le mot de passe noté. Ses minuteurs attendent : la station neuve ne s'est jamais sauvegardée. Puis `station restore --remote`, sans ID, doit remettre la sauvegarde de la nuit, rendre la même station, son et compte admin compris, et rallumer les minuteurs. Aucune sortie ne doit montrer le mot de passe du dépôt.

Le job `update` fait une vraie mise à jour, le critère de la fiche MAJ-04. Il installe la plus haute version publiée, avec sa propre commande `station`, prise sur sa page comme sur un VPS. Puis il fait ce que demande la 1.0.0 à une station installée avant elle : il épingle dans `.env`, par `ICECAST_MOUNT`, le mount que la station sert. Il essaie alors deux versions cassées du dossier de la branche, le critère de la fiche MAJ-05. Dans la première, l'image de la console s'arrête aussitôt : une busybox faite sur place, que la mise à jour ne tire pas (`pull_policy: never`). Dans la seconde, `radiotomate-init` ajoute au moteur deux migrations, dont la seconde échoue. Chacune doit échouer, puis revenir seule à la version publiée : les mêmes images pour chaque service, les mêmes données, la base d'avant comprise, et l'antenne ; `HOLD` posé, `updates.log` et le journal du système qui le disent, et les journaux de la version cassée gardés. La commande de la branche retire ensuite `HOLD`. Il lance enfin `station update --from` avec l'archive et la commande de la branche, vers `main`. L'émission hebdomadaire qu'il ajoute tombe trois jours plus tard : la fenêtre ne l'arrête pas. Il vérifie ensuite :

- l'antenne, lue chaque seconde sur le port local d'Icecast pendant la mise à jour : elle doit se couper moins de 30 s ;
- les comptes, horloges, émissions, Agenda et réglages, d'après la même empreinte qu'avant ;
- la sauvegarde d'avant, dans `backups/`, la ligne de `updates.log` et `versions.json` ;
- `station status`, puis le contrôle de la station, `smoke.sh`, sur le même mount.

Chaque cas prend quelques minutes, mais tire les images de la station trois fois, 3 Go environ chaque fois : le job ne tourne donc que pour ce qu'une installation prend, `deploy/station` et ses tests, `compose.yml`, le `Caddyfile`, `deploy/scripts/` et `scripts/version.py`, sur une pull request comme sur `main`. À la main : « Run workflow » sur `station`. Les images sont celles de `main`, pas celles de la branche : une pull request qui change une image et le dossier ensemble ne se vérifie en entier qu'après sa fusion. En échec, la sortie de l'installation et les journaux de `docker compose` sont dans un artefact du cas, `installation-neuf-1` ou `installation-deja-la-1`, sans les secrets de `.env` ; le chiffre est celui de la tentative. Il reste 14 jours. `scripts/verifier.sh` ne fait pas cette installation : elle écrit dans `/opt/button`, et prend les ports 80 et 443 de la machine. Pour la refaire à la main, sur une machine jetable : voir [d'où viennent les fichiers](deploiement.md#doù-viennent-les-fichiers).

Les dépendances du catalogue vont dans un environnement à part, une fois :

```bash
python3 -m venv services/catalog/.venv
services/catalog/.venv/bin/pip install -r services/catalog/requirements.txt
```

Les tests Playwright des pages HTMX de l'amont ne tournent pas en CI : `cd engine && poetry run playwright install chromium`, une fois, puis `poetry run pytest tests/interface`.

## L'antenne

`liquidsoap --check` lit le script du playout sans le jouer. La partie `antenne` le joue, et écoute ce qui sort :

```bash
./scripts/verifier.sh antenne
python3 engine/playout/tests/antenna.py    # le même banc, sans le résumé
```

Il faut Docker, rien d'autre. Le banc monte le script dans le Liquidsoap de l'image du playout, lu dans `engine/playout/Containerfile`, avec l'Icecast de `services/icecast` et un faux scheduler, qui répond au playout et garde ses battements. Il pousse des titres comme le scheduler, deux d'avance dans la file, un son de bac qui coupe le premier, un jingle qui coupe le second, puis un jingle et un son de bac qui attendent la fin du troisième et du quatrième, et enregistre le mount WAV du casque : le son du flux public, avant son encodeur MP3. Pendant le premier titre, il lance le nettoyage des files, comme le scheduler chaque minute. Il échoue si un titre ne passe pas, si les titres passent dans le désordre, si la même trame de 20 ms passe en boucle, si le temps restant d'un titre ne bouge plus, si un titre ou le son de bac n'est pas annoncé pour sa durée, si le playout dit une autre source que celle qui joue, si un son qui devait attendre la fin d'un titre le coupe, si le nettoyage des files retire le prochain titre de l'auto-DJ ou laisse celui d'après, ou si l'antenne reste muette.

Les sons du banc sont des balayages, fabriqués par `sounds.py` : aucune trame n'y ressemble à la suivante. Une trame répétée ne peut donc venir que d'une file figée, comme celle que laissait le fondu de l'auto-DJ : l'antenne bourdonnait, sans rien au journal de Liquidsoap ([les changements du moteur](moteur/changements-radiotomate.md#conducteur-et-vérité-dantenne)).

Deux titres du banc sont des MP3 à débit variable sans en-tête Xing, l'un chargé puis muet, l'autre muet puis chargé : ffmpeg estime leur durée d'après leurs premières trames, 13 s et 102 s pour 20 s. Le banc compare la durée que le playout annonce de chaque titre, ce qu'il a joué plus ce qu'il lui reste, à sa durée réelle : le scheduler règle sur ce reste l'envoi des jingles et des coupures. Il vérifie aussi la source que disent les battements pendant chaque son : pendant un son de bac, le playout disait encore l'auto-DJ, avec le reste du titre coupé.

Le banc coupe enfin son dernier titre par un relais, celui de son propre flux public, puis par un direct, qu'il envoie lui-même au harbor comme l'encodeur d'un studio, par-dessus le relais. Le battement doit les dire `relay` et `stream`, puis `autodj` quand le titre revient. Le relais, lui, ne doit pas revenir : un direct arrête le relais qu'il coupe. Le scheduler et la console lisent ce battement pour savoir ce qui passe, et les tests du moteur le simulent : seul ce banc lit celui du vrai Liquidsoap.

Le banc prend des ports libres, et se défait à la fin, avec son volume et les deux images qu'il a construites. La CI le lance avant de construire les images du moteur ([`engine.yml`](../.github/workflows/engine.yml)) : un script qui ne joue pas n'atteint pas le registre.

## Le conducteur devant l'antenne

Les tests du moteur jouent le scheduler devant un battement simulé, et le banc d'antenne joue le playout devant un faux scheduler : un défaut entre les deux ne se voit ni dans les uns, ni dans l'autre. La partie `conducteur` les fait tourner ensemble :

```bash
./scripts/verifier.sh conducteur
python3 engine/playout/tests/rundown.py    # le même banc, sans le résumé
```

Il faut Docker, rien d'autre. Le banc monte une petite station (`rundown.compose.yml`) : l'Icecast de `services/icecast`, le playout, puis l'interface et le scheduler dans le réseau du playout, comme sur une station. L'image du moteur est construite depuis `engine/Containerfile`, deux à trois minutes la première fois ; le playout est le script du dépôt, dans le Liquidsoap de son image. La base est semée pour le passage (`rundown_seed.py`), comme le fait `radiotomate-init` : installation, migrations, deux comptes, vingt-deux titres dans Beets, quatre bacs, un relais, et une heure type d'un jingle pour deux titres. Les sons sont des balayages fabriqués par ffmpeg, les mots de passe sont d'essai : rien ne vient d'une station.

L'heure type a trois coupures à la minute, une minute après l'autre, posées juste après le démarrage :

1. une coupure « Coupe pile », qui lance un programme de 48 s. Le nettoyeur des files est réglé au plus bas, 30 s : derrière le programme, le titre que l'horloge garde prêt attend plus longtemps ;
2. une coupure « Attend la fin », un flash à la fin du titre à cheval sur sa minute ;
3. une seconde coupure « Coupe pile », due pendant le direct.

Entre la deuxième et la troisième, le banc lance un relais, celui de son propre flux, par « Diffuser maintenant », comme une console : le scheduler l'arrête au bout de sa durée maximale, 12 s. Puis il envoie un direct au harbor, comme l'encodeur d'un studio, avec le jeton que le compte du studio prend dans la console. Le direct tient l'antenne pendant la minute de la troisième coupure.

Une sonde (`rundown_probe.py`) tourne dans le réseau du playout. Elle lit le conducteur comme une console ouverte, six heures toutes les 3 s, la base du moteur, les battements que relaie le scheduler, le silence que le playout compte sur sa sortie, et ce que le nettoyeur retire des files. Sa console s'ouvre une fois l'antenne partie : ouverte avant, elle fait tirer la prévision par l'interface pendant que le scheduler tire la sienne, et les premiers sons passent en double, un démarrage sur six environ. C'est la fiche FON-60 ; `--console-au-demarrage` l'ouvre tout de suite, pour rejouer ce défaut. Le banc échoue si :

- un son part à plus de 5 s de l'heure que le conducteur lui donnait une minute avant ;
- la coupure « Coupe pile » ne part pas à sa minute, ou le titre qu'elle tranche revient après son son ;
- la coupure « Attend la fin » coupe le titre qu'elle attend ;
- une ligne envoyée au playout ne passe jamais, ou part dans une file qui en tient déjà une autre, prévue au même moment ou plus tard ;
- le nettoyeur des files retire un son ;
- l'antenne se tait 3 s ;
- le relais ne prend pas l'antenne, ou dépasse sa durée maximale ;
- pendant le direct, l'horloge envoie un son au playout, la coupure due passe, pendant ou après lui, sa ligne n'est pas fermée « retenue pendant le direct », ou l'interface accepte un « Diffuser maintenant » ;
- après le direct, le titre qu'il a coupé revient, ou la grille ne reprend pas.

Une heure donnée avant un relais ou le premier son du banc ne dit rien de ce qui passe après : le conducteur ne les prévoit pas. Ces sons-là ne sont pas comparés, et le relevé les dit « pas jugé ». À partir du direct, le banc ne compare plus d'heure, et ne relève plus ce que l'horloge envoie : le retour d'un direct n'est pas encore propre (FON-55, FON-62). Il y juge le direct lui-même, et finit 25 s après lui, une fois la grille repartie. Le blanc qui suit un direct est mesuré, et dit : c'est la fiche FON-55.

Le banc dure cinq à six minutes. Ses coupures tombent toutes dans l'heure où l'antenne démarre : dans les cinq dernières minutes d'une heure, il peut attendre la suivante. Il prend des ports libres, et se défait à la fin, avec ses volumes et ses images. La CI le lance avant de construire les images du moteur ([`engine.yml`](../.github/workflows/engine.yml)), sur une image du moteur qu'elle construit elle-même, avec le cache du dernier build de `main` (`RUNDOWN_ENGINE_IMAGE`).

Pour voir le banc échouer, couper un interrupteur du moteur dans sa base : `python3 engine/playout/tests/rundown.py features.titles_queued_close_to_air=0` pose cette clé dans la table `settings` avant le démarrage. `--journal relevé.json` garde ce que la sonde a noté, et `--relire relevé.json` le rejuge, sans Docker : en échec, la CI joint ce relevé au job, dans l'artefact `conducteur-1`, 14 jours ; le chiffre est celui de la tentative.

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
| Moteur | l'interface en mode démo (`radiotomate interface --demo --port …`), sur une base semée par `engine/tests/e2e/seed.py` : un compte par rôle, des carts, une horloge pour toute la semaine, les réglages d'une station d'exemple en `radio.example`, et une petite banque pour `MEDIA_ROOT` |
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
| `barre.spec.ts` | la barre du haut : ce qui passe, et le dernier titre connu quand le moteur ne répond plus, l'état de l'antenne et son détail, une antenne figée, simulée par `page.route`, qui dit quoi faire dans la barre et au pupitre, le casque et sa source, un casque sans flux réglé, qui dit quoi régler, un flux muet, qui s'arrête ou qui ne répond jamais, en PCM comme par l'élément audio, le menu du compte, le lien « Code source », qui télécharge le code de la version, la suit quand elle change sous une page ouverte, mène au code réglé pour une version modifiée, ou au dépôt |
| `direct.spec.ts` | « Passer en direct » : l'adresse réglée du direct, à copier ; sans hôte réglé, ce que voient l'admin et l'animateur ; face à un moteur sans la route (404), le panneau dit de le mettre à jour |
| `pupitre.spec.ts` | Espace, `/` et Entrée, la pré-écoute, « Diffuser », déplacer une ligne au clavier et à la souris, monter une ligne en tête devant une ligne déjà commencée, retirer puis annuler, le focus rendu à « Passer en direct » |
| `conducteur.spec.ts` | la page Conducteur dans les mots de la console ; une ligne sans son, que le bandeau compte et qui mène à « Réparer », et ce que l'animateur en voit ; le retrait d'une ligne de l'horloge au clavier, qui la nomme, puis « Annuler », un retrait sans réponse, et un conducteur qui ne répond plus, simulés par `page.route` devant le moteur de démo |
| `etats.spec.ts` | session expirée, droit manquant, moteur injoignable, moteur muet, moteur arrêté derrière nginx (502 en HTML), envoi trop lourd pour nginx (413 en HTML) et route absente, puis les gestes refusés ou sans réponse de la page Automate, simulés par `page.route` devant le moteur de démo et le faux catalogue |
| `bacs.spec.ts` | « Diffuser maintenant » sur un bac sans son prêt : la console dit que rien n'est parti |
| `messages.spec.ts` | les messages en bas à droite de l'écran : au-dessus d'une fenêtre ouverte, ils se lisent, s'annoncent et se ferment sans la fermer ; un refus du moteur, simulé par `page.route`, s'annonce en alerte, quels que soient ses mots |
| `roles.spec.ts` | ce que voient l'animateur, le programmateur et l'admin |
| `apparence.spec.ts` | le thème clair et le sombre, choisis dans le menu du compte ou suivant l'appareil |
| `telephone.spec.ts` | la console sur un téléphone de 360 px, au doigt |
| `station.spec.ts` | l'onglet Station de l'admin : un nom enregistré passe sans recharger dans le titre de l'onglet et la barre de navigation, et tient après un rechargement ; face à un moteur sans ces routes (404), la console garde `brand.json` ; une valeur refusée se dit sous son champ, qui prend le focus |

Un défaut connu de la console ou du moteur garde son parcours en `test.fixme`, avec la raison en commentaire : Playwright le saute. Pour le voir échouer, remplacer `test.fixme` par `test` le temps d'un lancement.

Un parcours échoue aussi sur un défaut d'accessibilité grave ou critique, au sens d'[axe-core](https://github.com/dequelabs/axe-core) : `banc.ts` passe axe sur la page où finit chaque parcours, et `accessibilite.spec.ts` passe chaque écran. Le rapport donne, pour chaque élément en défaut, la règle d'axe, son sélecteur et ce qui ne va pas. L'analyse se fait sans animation, une fois finies celles en cours : un menu qui s'ouvre encore fausserait les contrastes. Un défaut se corrige dans la console. `e2e/accessibilite.ts` peut en excuser un gardé en connaissance de cause, avec sa raison en commentaire : `DEFAUTS_CONNUS` par règle d'axe et par sélecteur, `TEXTES_PALES` par couleur de texte. Les deux listes sont vides : les défauts relevés à l'arrivée d'axe sont corrigés. Attention : une couleur de texte listée est excusée partout, même sur un écran neuf. Un défaut qui ne se voit qu'une fois, le temps que le moteur de démo fasse bouger la page, n'est pas rapporté : chaque page en défaut est analysée deux fois. axe ne voit pas un texte écrit par le CSS (`content`), comme le badge du nombre d'incidents : `contraste(élément)`, de `e2e/accessibilite.ts`, mesure son rapport de contraste avec son fond.

Un parcours s'écrit dans `console/e2e/<sujet>.spec.ts`. Il importe de `e2e/banc.ts` :

- `test` et `expect`. `test` fait échouer un parcours sur toute erreur JavaScript de la page, et sur un défaut d'accessibilité grave ou critique de la page où il finit. Pour vérifier un état en cours de route, un menu ouvert par exemple : `verifierAccessibilite(page, écran)`, de `e2e/accessibilite.ts`. `test` coupe aussi ce qui sortirait du banc : les réglages de sa station d'exemple, semés par `engine/tests/e2e/seed.py`, nomment un flux en `radio.example`, que le casque demande dès l'ouverture. Une requête vers un autre site échoue, et un lien vers un autre site ouvre une page vide à son adresse. Un parcours qui a besoin du flux le sert lui-même par `page.route`, qui passe avant le banc, comme dans `barre.spec.ts` ;
- `seConnecter(page, rôle)`, pour entrer avec un compte semé, ou `remplirLaConnexion(page, rôle)` quand l'écran de connexion est déjà affiché ;
- `antenne`, `file` et `bibliotheque`, les trois régions du pupitre, `avis` pour un message de la console annoncé comme un état, `alerte` pour un message annoncé comme une alerte, `tenirLAntenne` et `tenirLaFile`.

Un parcours trouve les éléments par leur rôle et leur nom accessible, jamais par une classe CSS. Un parcours neuf se vérifie une fois : casser dans la console ce qu'il vérifie, le voir échouer, puis défaire.

Un parcours n'attend pas pour de vrai une minuterie de la console, comme les 8 s que le casque laisse au flux. Il pose `page.clock.install()` avant d'ouvrir la page, puis avance l'horloge avec `page.clock.fastForward()`, comme dans `barre.spec.ts`. `page.clock.runFor()` déroule aussi chaque image des animations : le parcours devient bien plus lent.

Un parcours peut relayer un appel au moteur pour en changer la réponse : `route.fetch()`, puis `route.fulfill()` avec la réponse changée, comme dans `conducteur.spec.ts`. La console relit l'antenne toutes les 5 s, et le conducteur toutes les 3 s : un relais peut être en route quand le parcours finit. À la fermeture du contexte, Playwright jette sa réponse : `reponse.json()` lève « Response has been disposed », ou `route.fetch()` « Test ended », après un parcours réussi. `test` retire donc les `page.route` de chaque page à la fin, après l'analyse d'axe, sans attendre les relais en route, et tait leurs erreurs : un relais n'a pas besoin de `try`. Une erreur levée par un relais avant la fin du parcours le fait toujours échouer.

Le moteur de démo est partagé par tous les parcours d'un lancement, et il enchaîne seul les titres de son horloge. Un jingle n'y dure que 4 s : la file bouge à chaque fin de titre. Un parcours qui touche à la file appelle d'abord `tenirLAntenne(page)`, qui passe au titre suivant jusqu'à en trouver un qui tient l'antenne une minute. Après un « Suivant », le moteur de démo est en avance sur son horloge, et il date une ligne mise à la suite de l'heure de l'appui : la file la range parmi ce qui est passé. Pour ce geste, un parcours lit la demande envoyée au moteur, pas la file. À force de « Suivant », plus d'une centaine avec les six heures de conducteur que demande la console, la démo peut avoir joué toutes ses lignes : « Pas d'horloge », jusqu'à ce que le conducteur en tire d'autres.

Sur une station, le conducteur se réconcilie au journal d'antenne. Le moteur de démo n'en a pas. Il ferme lui-même la ligne d'un « Diffuser maintenant », jouée, dès qu'il passe à un autre titre. Pendant son propre titre, elle reste « Déjà partie », et la file la prend pour le titre à l'antenne, à son nom : aucune ligne de l'horloge n'est alors à l'antenne. Il ne rend plus « prévu » une ligne de l'horloge qu'il a jouée : il garde ces lignes en mémoire, le temps qu'il tourne. La tête de la file a donc « Déplacer » et « Retirer », et un parcours peut viser la première ligne, comme `telephone.spec.ts`. Deux cas, qu'aucun parcours ne fait, la verrouillent encore. Deux « Diffuser » au même instant, par un double clic ou deux onglets, peuvent y laisser la ligne du premier, « Déjà partie », jusqu'au titre suivant. Et le moteur de démo ne suit pas les déplacements de la file : il joue ses lignes dans l'ordre où il les a chargées. Une ligne montée au-dessus d'une autre du même titre est prise par la file pour le titre à l'antenne quand la démo joue l'autre, et celle-ci passe en tête, verrouillée. Un parcours qui déplace une ligne choisit donc deux titres différents, comme `voisines` dans `pupitre.spec.ts`.

La file bouge aussi quand l'antenne tient : une ligne en sort quand son heure de fin passe, et la page relit la file toutes les 3 s. Un geste qui réordonne la file, ou qui en retire une ligne, passe par `tenirLaFile(page, geste)`. L'antenne tenue, la page se recharge avec une horloge factice et lit la file. Puis son horloge s'arrête jusqu'à la fin du geste : la page ne relit plus la file, et le temps n'en fait plus sortir de ligne. Avec l'horloge factice, une erreur levée dans une minuterie de la page n'arrive qu'à sa console, pas au contrôle des erreurs JavaScript du banc.

Une ligne de la file se désigne par son heure exacte, l'attribut `datetime` de son heure : l'heure affichée, à la seconde, peut être celle de deux lignes. La file ne dit pas d'où vient une ligne, de l'horloge ou du pupitre. Un parcours qui en a besoin le lit au moteur, comme le parcours « Annuler » de `pupitre.spec.ts` : « Annuler » remet une ligne du pupitre retirée à la suite, à une autre heure.

Sur `main`, la CI publie aussi les images Docker, seulement si tout est vert. Un tag `vX.Y.Z` publie une version : voir [plus bas](#publier-une-version).

## Dépendances, licences et failles

Dependabot propose chaque mois les mises à jour ([`.github/dependabot.yml`](../.github/dependabot.yml)) : les actions GitHub, les dépendances de la console, du catalogue et du moteur, et les images de base des sept images. Pour le moteur, il ne déplace que `poetry.lock` : les contraintes de `pyproject.toml` suivent Radiotomate et Liquidsoap, et changent à la main. Il ne monte pas Python dans les images du moteur, du catalogue et de nowplaying, qui gardent celui de la CI : ce changement se fait à la main, avec `python-version` des workflows. Quand il monte Liquidsoap, le job `liquidsoap-check` d'`engine.yml` et `scripts/verifier.sh` suivent à la main.

### Les licences

Chaque dépendance npm ou Python livrée avec BUTTON, dans le build de la console ou dans une image, a une licence compatible avec l'AGPL. Les licences acceptées, et pourquoi, sont dans [`scripts/licences.toml`](../scripts/licences.toml). La CI les contrôle sur chaque pull request qui touche un fichier de dépendances ([`licences.yml`](../.github/workflows/licences.yml)). Les outils de développement ne sont pas livrés : ils ne sont pas contrôlés.

Sur cette machine, `./scripts/verifier.sh licences` lance le même contrôle, après les tests de `scripts/licences.py`. Sans Poetry, ou sans l'environnement du catalogue ([plus haut](#vérifier-avant-de-proposer-un-changement)), la partie contrôle le reste, puis se dit sautée ; nommée, elle échoue.

Le contrôle échoue sur une licence refusée, et sur une licence inconnue ou qui ne se lit pas. Une licence inconnue se vérifie, puis entre dans `licences.toml`, acceptée ou refusée, avec sa raison. Une exception ajoutée par `WITH` aussi : seules celles qui donnent des droits en plus sont acceptées. Un paquet dont les métadonnées ne disent pas la licence entre dans `[paquets]`, à sa version, une fois sa licence vérifiée à la main.

Le moteur se contrôle dans son environnement Poetry. Un paquet que `poetry.lock` réserve à une autre plateforme, ou à une autre version de Python, n'y est pas installé : le contrôle le saute, et le dit. La CI, elle, prend le Python de l'image, 3.13.

### Les failles des images

Trivy analyse chaque image juste après sa publication depuis `main`, les sept images d'une version une fois celle-ci publiée, et chaque lundi les sept images en `:main` et en `:stable`, celle que suivent les stations ([`failles.yml`](../.github/workflows/failles.yml)). Le job échoue sur toute faille critique. Il passe après la publication, jamais avant : une station qui suit `main` reçoit ses correctifs, même quand une faille reste ouverte.

Devant un job rouge :

- **Un correctif existe** : prendre la mise à jour qui l'apporte, une image de base plus récente ou un `poetry.lock` à jour. Quand l'image de base a déjà le correctif, relancer le workflow de l'image sur `main` (« Run workflow ») la reconstruit. Un paquet installé par le Dockerfile, comme ffmpeg et ce qu'il tire, garde en revanche sa version du cache de build tant que l'image de base ne change pas : vider d'abord le cache des Actions (`gh cache delete --all`), puis relancer.
- **Aucun correctif** : accepter la faille dans [`.trivyignore.yaml`](../.trivyignore.yaml), pour les seuls paquets touchés (`purls`), avec sa raison (`statement`) et une expiration à 90 jours au plus (`expired_at`). Passé cette date, le job échoue de nouveau : revoir la faille, puis repousser la date ou corriger.

Le job vérifie aussi que chaque faille acceptée a ses paquets, sa raison et une expiration à 90 jours au plus. Pour analyser une image à la main : « Run workflow » sur `failles`, avec sa référence complète (`ghcr.io/lazbutton/button-console:main`) ; sans référence, les sept images en `:main` et en `:stable`. Trivy est épinglé dans `failles.yml`, version et empreinte, et Dependabot ne le suit pas : le monter à la main, avec l'empreinte de `trivy_<version>_checksums.txt`.

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
3. Remplir `STATION_DATA`, dans `engine/tests/test_migrations.py` : une valeur pour chaque colonne nouvelle, ni NULL ni son défaut, sous le numéro de la migration, et les lignes que la montée transforme, sous un numéro d'avant. Le test monte chaque migration sur cette base, prise à la version d'avant, la redescend, puis la remonte : il échoue si la descente perd ce qui existait avant la montée, si elle laisse ce que la montée a ajouté, ou si la montée, relancée, échoue ou ne rend pas les mêmes tables. Ajouter aussi son propre test, comme `test_v18_encoder_token_up_then_down` : ce que la montée fait aux lignes, et ce que la descente fait des lignes écrites à la nouvelle version, que le test commun n'a pas.
4. Vérifier l'aller-retour sur une copie de base : `radiotomate update --target-version N-1`, puis `radiotomate update`.

`radiotomate-init` applique les migrations à chaque démarrage. Revenir à une image plus ancienne demande donc de redescendre d'abord le schéma : voir [`deploiement.md`](deploiement.md#revenir-en-arrière). C'est pourquoi une migration ne sort jamais dans un correctif : la version qui la porte est une mineure, au moins.

## Publier une version

Les stations installent des versions publiées, pas `main` : voir la décision [0003](decisions/0003-mettre-a-jour-par-des-versions.md). Le numéro `X.Y.Z` d'une version dit ce qu'elle demande aux stations : voir [`deploiement.md`](deploiement.md#mettre-à-jour). Ces règles valent dès `0.1.0`. Pour choisir le numéro :

- un correctif, `0.1.1` : des corrections seulement. Ni migration du schéma, que la CI refuse dans un correctif, ni réglage nouveau. Ses images marchent avec le dossier de station de la version d'avant ;
- une mineure, `0.2.0` : des fonctions nouvelles, une migration du schéma, un réglage nouveau qui a sa valeur par défaut ;
- une majeure, `1.0.0` : tout ce que la station doit faire elle-même, changer une variable ou remplacer un fichier par exemple.

Pour publier :

1. Une pull request renomme « Non publié » en `## X.Y.Z` dans le [CHANGELOG](../CHANGELOG.md), et rouvre au-dessus un « Non publié » vide. En tête des notes, ce que la version demande : la version du schéma quand elle migre, l'action pour une majeure. L'action d'une majeure est un paragraphe qui commence par `**Mise en service.**` : `station update` s'arrête devant une majeure, et le cite, d'après le `CHANGELOG.md` que la version joint à ses fichiers de station. Pour voir les notes telles qu'elles seront publiées : `python3 scripts/version.py notes X.Y.Z`.
2. Une fois la pull request fusionnée, poser le tag sur son commit de fusion, puis le pousser. Un tag à la fois : attendre la fin du job « release, X.Y and stable » avant le suivant.

   ```bash
   git switch main && git pull
   git tag -a vX.Y.Z -m "BUTTON X.Y.Z" <commit de fusion>
   git push origin vX.Y.Z
   ```

3. Le workflow [`version`](../.github/workflows/version.yml) fait le reste. Il vérifie d'abord, sans rien construire, les notes de la version, qu'aucune version plus haute n'est dans l'histoire du commit, et qu'un correctif n'ajoute aucune migration. Puis il lance les tests du moteur, de la console et des services, et publie les sept images en `X.Y.Z`. Une fois les sept publiées, il crée la page de la version, avec ses notes. Il y joint les fichiers d'une station, que `station install` et `station update` téléchargent : `station`, `station.tar.gz` et `SHA256SUMS` ([décision 0016](decisions/0016-le-dossier-vient-de-sa-version.md)). Il y joint aussi le code de la version, `button-X.Y.Z-source.tar.gz`, le même que l'image de la console porte et sert à chaque compte ([décision 0018](decisions/0018-la-station-sert-son-code-source.md)). Puis il pose `X.Y` et `stable` sur ces mêmes images. Trivy analyse enfin les sept images, sans rien retenir.

Pour voir ces fichiers avant de publier, ou pour essayer `main` sur une machine jetable : `python3 scripts/version.py station main /tmp/station`. Le `compose.yml` de l'archive n'a plus ses sections `build:`.

`stable` ne recule jamais : un correctif d'une ancienne version, publié après une plus récente, ne déplace que son `X.Y`. Seule la plus haute version reçoit d'office les correctifs ([SECURITY.md](../SECURITY.md)) : une ancienne n'en reçoit qu'au cas par cas. Un tel correctif part du tag de sa ligne, jamais de `main`, qui porte déjà la version suivante. Par exemple, une branche `version/0.1` tirée de `v0.1.1` reçoit la correction et la partie `## 0.1.2` de son CHANGELOG, puis le tag `v0.1.2` se pose sur son commit.

Une version publiée ne change plus : une correction fait une nouvelle version, et les workflows d'images refusent de reconstruire une version qui a sa page. Seuls les jobs en échec se relancent, par « Re-run failed jobs ». Tant que la page n'existe pas, rien n'est publié. Si les notes ou un test ont échoué, corriger par une pull request, retirer le tag (`git push origin :refs/tags/vX.Y.Z`), puis le reposer sur le nouveau commit de fusion (`git tag -f -a vX.Y.Z …`) et le pousser : les images déjà poussées en `X.Y.Z` sont reconstruites.

Après la coupe d'une version, une pull request ouverte avant elle range sa ligne du CHANGELOG sous la version coupée en fusionnant `main`. Une fois la version taguée, la CI le refuse, sur la pull request comme après la fusion sur `main` : remettre la ligne à la fin de « Non publié ». Le run d'un tag déplacé depuis ne publie rien : seul le run du tag actuel publie.
