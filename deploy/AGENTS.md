# Consignes pour le déploiement

À lire avec le [AGENTS.md](../AGENTS.md) de la racine. Le guide d'installation est [docs/deploiement.md](../docs/deploiement.md).

## Vérifier

```bash
../scripts/verifier.sh deploy    # docker compose config avec .env.example, puis ShellCheck et bats comme la CI
```

La CI lance ShellCheck sur chaque pull request qui touche un script ([`shellcheck.yml`](../.github/workflows/shellcheck.yml)), et `verifier.sh` lit dans ce workflow la même image et la même liste. Elle lance aussi les tests de `station` ([`station.yml`](../.github/workflows/station.yml)), dont `verifier.sh` lit l'image. Un script nouveau hors de `deploy/scripts/` s'ajoute à la liste. Un avertissement voulu se garde par une directive, sous une ligne qui dit pourquoi, comme dans `promote-inbox.sh`.

`verifier.sh` ne passe pas encore le profil `vps` ni le `Caddyfile`. Après un changement de l'un ou de l'autre :

```bash
docker compose --env-file .env.example --profile vps config --quiet
docker run --rm -e DOMAIN=radio.example -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.11-alpine caddy validate --config /etc/caddy/Caddyfile
```

Rien de ce dossier ne se lance contre une station en service. Les essais se font sur le banc local ou sur une machine jetable.

## compose.yml

- Le projet Compose s'appelle `button` (`name: button`). Le renommer recrée vides les volumes nommés `button_tusd-data`, `button_share-private` et `button_cloud-sync-state`, et change le nom des conteneurs que citent des scripts et des docs.
- L'interface et le scheduler partagent le réseau du playout (`network_mode: service:radiotomate-playout`). **On ne redémarre jamais `radiotomate-playout` seul** : on recrée les trois services du moteur ensemble.
- `BUTTON_VERSION` choisit les sept images de BUTTON, ensemble, `stable` par défaut : [docs/deploiement.md](../docs/deploiement.md#mettre-à-jour). Une image nouvelle de BUTTON la prend aussi, sous la forme `${BUTTON_IMAGES:-ghcr.io/lazbutton}/button-<nom>:${BUTTON_VERSION:-stable}` : `version.yml` et `failles.yml` lisent la liste des images dans `compose.yml` (`scripts/version.py images`). Son build va dans l'un des trois workflows d'images, que `scripts/test_version.py` compare à cette liste. Les images des autres projets, meilisearch, tusd, rclone et Caddy, restent épinglées à leur version. `x-rt-tag` arrête `docker compose` quand l'ancien `RT_TAG` est encore posé : ignoré, il laisserait un moteur épinglé repartir sur `stable`, et migrer son schéma. Le `tty` de `radiotomate-init` le reprend : il vaut `false`, ou une phrase que Compose refuse comme booléen, en la citant.
- **Docker contourne le pare-feu.** Un port publié sur toutes les interfaces reste joignable même si ufw le ferme. Les ports de la console, d'Icecast, de nowplaying et du catalogue écoutent donc sur `BIND_ADDRESS` : vide, sur toutes les interfaces, en IPv4 et en IPv6 (`0.0.0.0` n'écouterait qu'en IPv4) ; `127.0.0.1` sur une machine exposée, derrière le reverse proxy. Un port nouveau que seul le reverse proxy doit joindre prend le même préfixe, `${BIND_ADDRESS:-}${BIND_ADDRESS:+:}` ; un port ouvert au public, comme le harbor, n'en a pas. Vérifier depuis une autre machine, pas avec `ufw status`.
- Une variable nouvelle a une valeur par défaut dans `compose.yml` (`${NOM:-défaut}`) et une ligne commentée dans `.env.example`. Un secret vaut `change-me` dans l'exemple, jamais une vraie valeur. Un secret nouveau passe aussi par `radiotomate-init`, qui le vérifie avec `check_secret`, avant tout le reste. Le service qui s'en sert attend `radiotomate-init` (`depends_on`, `service_completed_successfully`), comme le playout, Icecast, nowplaying et le catalogue.
- Le service `caddy` ne démarre qu'avec `--profile vps`, ou `COMPOSE_PROFILES=vps` dans `.env`. Il joint les services par leur nom, sur le réseau de Docker, jamais par les ports de `BIND_ADDRESS`. Le `Caddyfile` dit ce qui passe sur le domaine public : la console, les mounts d'Icecast en lecture, `status-json.xsl` et `now.json`, rien d'autre. Un chemin nouveau s'y ajoute exprès. Le flux passe par Caddy : [ADR 0015](../docs/decisions/0015-le-flux-passe-par-caddy.md).
- Le service `share` ne démarre qu'avec `--profile share`. `SMB_BIND` n'est jamais `0.0.0.0` : `share/entrypoint.sh` le refuse, sauf avec `SMB_ALLOW_PUBLIC=1`, qui n'a pas sa place sur une machine exposée.
- Le service `cloud-sync`, le pont des bacs ouverts dans Dropbox, ne démarre qu'avec `--profile cloud`. Il tourne sur l'image officielle de rclone, épinglée, et monte la banque à `/media`, comme le moteur : les liens de `Carts/` visent `/media`. Sa configuration, `rclone.conf` avec le jeton Dropbox, vient du dossier `CLOUD_SYNC_CONFIG`, jamais de `.env`. Son volume `cloud-sync-state` garde ce qu'il a copié : vidé, il ferait revenir de Dropbox les sons retirés dans la console.
- Les images sont construites pour `linux/amd64` seulement : une machine ARM ne les lance pas.

## Les scripts

| Où tourne le script | Forme |
|---|---|
| Dans un conteneur : `init-radiotomate.sh`, `beets-import-loop.sh`, `promote-inbox.sh`, `setup-media-tree.sh`, `cloud-sync.sh`, `share/entrypoint.sh` | `#!/bin/sh` et `set -eu` : POSIX, sans bash |
| Sur l'hôte : `backup-radiotomate.sh`, `restore-radiotomate.sh`, `smoke.sh`, et `station`, en root | `#!/usr/bin/env bash` et `set -euo pipefail` |

- Un script se relance sans danger : il ne refait que ce qui manque, et n'écrase rien.
- Un nouveau script de l'hôte n'a besoin que de Docker, de curl et d'openssl. Les deux scripts de sauvegarde demandent aussi `sqlite3` et `tar` sur l'hôte. `station` demande aussi ce que Debian et Ubuntu ont toujours, `tar`, `sha256sum` et `ss`, et apt pour installer Docker.
- Chaque message d'erreur dit quoi faire ensuite.
- ShellCheck passe sur chaque script.
- Les tests de `restore-radiotomate.sh` sont dans `engine/tests/test_update_backup.py`, avec la copie qu'il remet : après une modification du script, lancer aussi `../scripts/verifier.sh moteur`. La CI du moteur ne se déclenche pas pour `deploy/`.
- Les scripts Python (`export_share_roles.py`, `refresh_volume.py`, `share/apply_share.py`) n'utilisent que la bibliothèque standard. Leurs tests sont dans `services/catalog/` (`test_share.py`, `test_refresh_volume.py`).
- Les tests du contrôle des secrets d'`init-radiotomate.sh` sont aussi dans `services/catalog/` (`test_init_secrets.py`), comme ceux de `promote-inbox.sh` : la CI des services les lance à chaque changement de `deploy/scripts/` ou de `compose.yml`. Le passage complet du script, avec ses blocs Python, l'avertissement sur le compte admin et le réglage du harbor posé à la première installation, est dans `engine/tests/test_init_admin.py` : après une modification du script, lancer aussi `../scripts/verifier.sh moteur`.
- Les tests de `beets-import-loop.sh` sont aussi dans `services/catalog/` (`test_beets_import_loop.py`) : un faux `beet` y joue Beets, sur une bibliothèque et un historique d'import aux formats du vrai, et `PROMOTE_INBOX` y fait lancer le vrai `promote-inbox.sh` par la boucle. Le passage avec le vrai Beets, sur les réglages que pose `init-radiotomate.sh`, est dans `engine/tests/test_beets_import_loop.py` : après une modification du script, lancer aussi `../scripts/verifier.sh moteur`.
- Les tests de `smoke.sh`, le contrôle après déploiement, sont aussi dans `services/catalog/` (`test_smoke.py`) : un faux `docker` et un petit serveur HTTP y jouent la station.
- Les tests de `cloud-sync.sh`, le pont Dropbox, sont aussi dans `services/catalog/` (`test_cloud_sync.py`) : un faux `rclone` y joue Dropbox, sur une banque temporaire avec ses liens `Carts/`. Le script tourne en vrai sous le `sh` de busybox, dans l'image de rclone, et les tests sous celui de la machine : il s'en tient à POSIX, et `file_stat` y lit aussi le `stat` des BSD.

## La commande station

`station` est la commande d'exploitation d'une station sur un VPS. Elle n'a aujourd'hui que `install` (INS-02). Les autres commandes s'y ajouteront, une fonction `cmd_<nom>` chacune, avec les mêmes aides :

- `status`, `logs`, `backup`, `restore`, `config`, `hold`, `unhold`, `cli` et `uninstall` (INS-03) ;
- `update` (MAJ-04) ;
- `rollback` (MAJ-05).

C'est un seul fichier, sans extension, celui de la commande posée dans `/usr/local/bin`. Ses règles :

- **Où elle tourne.** Sur l'hôte, en root, sur Debian 12 ou 13 et Ubuntu 24.04 seulement : bash 5, GNU coreutils, iproute2. Elle demande Docker, curl et openssl, comme les autres scripts de l'hôte, puis ce que ces systèmes ont toujours, et apt pour installer Docker.
- **D'où elle vient.** Pas d'un clone : chaque version publiée la joint à sa page, avec `station.tar.gz`, le dossier d'une station à cette version, et `SHA256SUMS` ([décision 0016](../docs/decisions/0016-le-dossier-vient-de-sa-version.md)).
  - `scripts/version.py station` les fabrique.
  - Un fichier que `compose.yml` monte depuis le dossier doit être dans l'archive : sinon, `version.py` refuse, et `test_version.py` échoue.
- **`.env`.** Il ne se réécrit jamais : une relance n'y ajoute que ce qui manque. Une commande qui change un réglage de `.env`, comme `config` (INS-03), le dit.
- **Le mot de passe admin.** Il ne s'écrit nulle part ailleurs que dans `.env`, en droits 600, et seulement jusqu'à son affichage, dans un terminal.
- **Les droits.** Le umask ne suffit pas : une ACL par défaut sur le dossier passe outre, comme celle de `/opt` sur un runner de GitHub.
  - Un fichier à protéger, comme `.env`, naît vide avec son mode, avant d'y écrire : `install -m 600 /dev/null`.
  - Le dossier de la station perd une ACL par défaut qui l'ouvrirait en écriture : `check_acl`, puis `make_station_dir`. Sans `setfacl`, rien ne s'installe.
- **L'environnement du shell.** Ce que `.env` règle n'en vient jamais : `env_isolate` retire ces variables avant `docker compose`. sudo garde `TZ`, par exemple.
- **Les questions.** Chacune a son option, pour la CI : sans terminal, ou avec `--yes`, rien ne se demande.
- **Les tests.** Ils sont dans `tests/`, lancés par `bats`, dans l'image officielle épinglée par [`station.yml`](../.github/workflows/station.yml).
  - De faux outils jouent la machine : ceux de `tests/fakes/`, puis `tests/docker` et `tests/setfacl`, que la machine n'a que si le test les pose.
  - `STATION_ROOT` met les fichiers du système, comme `/etc/os-release` ou `/usr/local/bin`, dans un dossier temporaire.
  - Le script se lit aussi avec `source` : ses fonctions se définissent sans rien lancer, et un test peut remplacer `interactive` ou `terminal`.
  - Une vraie installation tourne aussi en CI, le job `install` de `station.yml` : `station install --yes --tls internal`, avec les images `:main`, sur un runner Ubuntu 24.04 dont `/opt` a une ACL par défaut ouverte à tous, dans deux cas. `neuf` : le runner n'a plus Docker, que `station install` installe. `deja-la` : il garde le sien, avec un Compose v2, et `station install` n'installe rien. Puis une relance, qui ne doit changer ni un fichier du dossier, hors `data/` et `media/`, ni un conteneur. Voir [docs/developpement.md](../docs/developpement.md#vérifier-avant-de-proposer-un-changement).
- **ShellCheck** passe sur le script et sur ses tests : ils sont dans la liste de `shellcheck.yml`.

## Pièges

- Une station installée par `station install` n'a pas les sources : son `compose.yml` n'a pas de sections `build:`. Une image qui manque y fait échouer `docker compose`.
- Une station peut avoir encore Compose v2. Il évalue tout ce qu'un `${…}` contient, même la branche qui ne sert pas : un `:?` dans un `:-`, un `:+` ou un `:?` arrête toujours `docker compose`, sur son message. Compose 5, celui de `ubuntu-latest` dans la CI, ne l'évalue que s'il sert. Un garde qui arrête Compose sous condition passe donc par un champ typé, comme `x-rt-tag`. `services/catalog/test_compose.py` lit `compose.yml` avec le Compose de la machine, puis avec un Compose v2, dans la CI comme dans `verifier.sh services`.

- Les scripts que `compose.yml` monte dans les conteneurs, comme `init-radiotomate.sh`, viennent du dossier de la station, pas de l'image. Une station qui suit `X.Y` reçoit les images d'un correctif sans changer de dossier : un correctif marche avec le `compose.yml` et les scripts de la version d'avant.
- `init-radiotomate.sh` tourne à chaque démarrage : il applique les migrations du schéma. Revenir à une image plus ancienne demande de redescendre le schéma d'abord : [docs/deploiement.md](../docs/deploiement.md#revenir-en-arrière). Une migration ratée ne laisse rien, mais celles passées avant elle au même démarrage restent, et l'image d'avant ne lit plus la base : [docs/exploitation/sauvegarde.md](../docs/exploitation/sauvegarde.md#remettre-la-copie).
- Beets saute ce que son historique d'import connaît (`import.incremental`, dans `state.pickle`) : un dossier entier quand il importe par album, un fichier avec `-s`. `beets-import-loop.sh` importe donc par titre. Avant chaque import, il inscrit dans l'historique les fichiers que la bibliothèque connaît déjà, et n'importe rien tant qu'il n'y arrive pas : une bibliothèque indexée par dossier, ou un historique perdu, ferait sinon tout réimporter, sous de nouveaux identifiants. Il ne donne aussi à Beets qu'un dossier resté le même pendant sa pause : `beet modify` écrit ses tags dans les fichiers, et abîme un fichier encore en cours de copie. Ce que la boucle écrit pendant son tour ne compte pas, et `promote-inbox.sh` passe pour cela après l'import : il réécrit à chaque tour un fichier dont il ne lit pas les tags, Ogg, Opus ou nom sans artiste, et le dossier n'aurait jamais de repos. L'historique n'oublie rien de lui-même : la boucle en retire les fichiers disparus que la bibliothèque ne connaît plus, sans quoi un fichier remis au même chemin ne serait plus jamais indexé. Elle retire elle-même de la bibliothèque un fichier disparu, avec `beet remove -f id:… , id:…` par paquets de 200 : SQLite refuse une requête de plus d'un millier d'`id:`. Pas avec `beet update` : devant un fichier disparu, il retire le titre en effaçant son fichier, au cas où, et élague les dossiers vidés jusqu'à `directory`, la banque. Reproduit : une banque vidée de son dernier titre, puis `20-archives`, supprimés. `beet update` ne sert qu'à relire un fichier changé, avec `-d` hors de la banque, pour qu'il n'élague rien, et `-e` pour les champs que la boucle pose d'après le dossier. Beets 2.5.1 ne relit qu'un fichier plus récent que la date notée dans la bibliothèque, et `beet update` n'y note pas la date de ce qu'il relit : `mtime` n'est pas un champ du fichier. La boucle compare donc les dates elle-même, met à 0 celle d'un fichier changé, puis y écrit celle qu'elle a vue.
- `deploy/local/` est un banc audio avec des mots de passe de test publics. Il ne sert jamais pour une station.
- `radiotomate.yaml` est monté seul dans nowplaying et le catalogue. Un service qui monte un fichier de `RT_DATA` attend `radiotomate-init` (`service_completed_successfully`), qui l'écrit : sinon, sur un dossier de données vide, Docker crée un dossier à la place du fichier, et le premier `docker compose up` laisse la moitié de la station en « Created ». `services/catalog/test_compose.py` le vérifie.
- Le `Caddyfile` est monté seul : un éditeur ou un `git pull` qui le remplace laisse l'ancien dans le conteneur, et `caddy reload` relit l'ancien. Un `Caddyfile` changé demande `docker compose up -d --force-recreate caddy`.
- Derrière Caddy, nginx reçoit du HTTP et le dit à tusd (`X-Forwarded-Proto $scheme`), qui répond alors une adresse d'envoi en `http://`. Le `Caddyfile` la réécrit en `https://` pour `/tus/`.
- tusd ne tourne pas en root (`user: "1000:1000"`), et Docker crée le volume `tusd-data` au nom de root : chaque envoi y échouerait, « open /tusd/… : permission denied ». Le catalogue, en root, donne ce volume à son `TUSD_USER` au démarrage. `services/catalog/test_compose.py` vérifie que les deux services disent le même utilisateur. Un service qui ne tourne pas en root et écrit dans un volume nommé demande la même chose.
- Le volume `share-private` naît aussi à root, et la boucle Beets (`radiotomate-dropbox`), en `rtuser`, y écrit les rôles du dossier partagé (`roles.json`). Mais root y garde les mots de passe : le volume ne se donne pas à la boucle, qui pourrait alors déplacer ou remplacer les fichiers de root. Le catalogue l'ouvre au démarrage en 1777, comme `/tmp`, et `share` le fait à chaque tour : la boucle n'y touche qu'à ses propres fichiers. `test_compose.py` vérifie que les trois services montent ce volume là où ils s'en servent. Avant de l'ouvrir, l'un et l'autre y prennent `pending/` et `samba/` à root (`claim_dir`) : sinon, la boucle pourrait les créer avant root, et lire ce qu'il y écrit. Un dossier qui n'est pas à root est repris, mais refusé s'il garde un fichier d'un autre compte : `share` ne démarre pas, et le catalogue ne dépose plus de mot de passe. Tout cela est dans les images, comme `apply_share.py`, et non dans un script monté : une station qui suit `X.Y` le reçoit avec un correctif.
