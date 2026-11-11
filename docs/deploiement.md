# Déployer une station

Une station complète tient dans [`deploy/compose.yml`](../deploy/compose.yml) : moteur, console, Icecast, titre en cours, catalogue et envoi reprenable. Les images sont publiées par la CI sur `ghcr.io/lazbutton`.

## Prérequis

- Une machine Linux x86-64 avec Docker et Compose v2. Les images ne sont construites que pour `linux/amd64`.
- De la place pour la banque de sons.
- Pour un accès public, un domaine qui pointe sur la machine, et ses ports 80 et 443 libres. Caddy, dans `compose.yml`, s'occupe du HTTPS : voir [HTTPS](#https).

## Installer sur un VPS

Sur un VPS neuf, une commande installe la station. Elle installe Docker s'il manque, pose les fichiers de la version et `.env` avec ses secrets, met la station en HTTPS derrière Caddy, puis la contrôle.

### Avant de commencer

- Un VPS sous Debian 12 ou 13, ou Ubuntu 24.04, en x86-64, avec 10 Go de libre au moins.
- Son domaine, qui pointe déjà sur lui : un enregistrement A, et AAAA s'il a une adresse IPv6.
- Ses ports 80, 443 et 6800 ouverts dans le pare-feu de l'hébergeur.

### Lancer l'installation

Sur le VPS :

```bash
curl -fsSLO https://github.com/lazbutton/button/releases/latest/download/station
sudo bash station install
```

La 0.1.0 n'a pas ce script : jusqu'à la version publiée suivante, cette adresse ne trouve rien. Voir [d'où viennent les fichiers](#doù-viennent-les-fichiers).

La commande procède dans l'ordre :

1. **Elle vérifie la machine** : les droits root, le système, le processeur, les ports 80, 443 et 6800, et la place. Elle vérifie aussi Docker et Compose v2, et propose de les installer depuis le dépôt de Docker. Une ACL par défaut sur `/opt`, qui ouvrirait la station en écriture à d'autres comptes, ne passe pas à son dossier : la commande l'en retire, avec `setfacl`. Sans `setfacl`, elle s'arrête avant d'écrire, et dit quoi installer.
2. **Elle pose les questions.** Entrée garde la valeur proposée :
   - le nom de la station ;
   - son domaine ;
   - l'e-mail du compte Let's Encrypt ;
   - le fuseau ;
   - l'identifiant du compte admin ;
   - si les mises à jour seront automatiques. Elles se feront seules quand `station update` saura se lancer seule ; d'ici là, `station update` les fait à la main.
3. **Elle vérifie que chaque adresse du domaine mène à la machine**, sur le port 80. Elle le fait avant que Caddy demande un certificat : Let's Encrypt refuse un domaine un moment après quelques échecs.
4. **Elle pose la station dans `/opt/button`** :
   - les fichiers de la plus haute version publiée, vérifiés par leur somme : `compose.yml`, le `Caddyfile`, les scripts ;
   - `.env`, en droits 600, avec la version épinglée (`BUTTON_VERSION`), des secrets tirés par `openssl rand`, et les réglages du HTTPS : `COMPOSE_PROFILES=vps`, `DOMAIN`, `BIND_ADDRESS=127.0.0.1` ;
   - les dossiers des données, sous `data/` et `media/` ;
   - la commande `station`, dans `/usr/local/bin`.
5. **Elle démarre la station** : elle tire les images, démarre, attend le certificat, puis lance le [contrôle](#mettre-à-jour) sur les adresses publiques.
6. **Elle règle la station** :
   - au premier démarrage, `radiotomate-init` ferme le harbor au mot de passe du compte : seuls les jetons d'encodeur y entrent, voir [le direct](#le-direct) ;
   - la commande remplit **Réglages → Station** : le nom de la station et ses adresses publiques, c'est-à-dire le flux, `now.json`, le statut et l'hôte du direct.
7. **Elle affiche l'adresse de la console**, avec l'identifiant et le mot de passe du compte admin.
   - Le mot de passe ne s'affiche qu'une fois, et seulement dans un terminal, jamais dans un journal.
   - Il quitte ensuite `.env`.
   - Il se change dans la console, **Mon compte**.

### Relancer

`sudo station install` se relance sans danger :

- un fichier de la version qui manque revient ;
- un fichier changé est remis à la version, et l'ancien est gardé à côté, en `.local-…` ;
- une variable qui manque à `.env` s'ajoute.

Elle ne change jamais une valeur de `.env`, ni la version : changer de version, c'est `station update`, et changer un réglage, `station config`. Une installation interrompue reprend où elle en était. Une installation finie, relancée, ne change rien.

### Les options

Chaque réponse a son option, pour installer sans question, en CI par exemple : `--name`, `--domain`, `--email`, `--timezone`, `--admin`, `--updates auto` ou `--updates manual`. Les autres options :

| Option | Pour |
|---|---|
| `--yes` | ne rien demander : les options répondent, sinon les valeurs par défaut. Docker s'installe s'il manque |
| `--github-token-file <fichier>` | les images encore privées : un jeton GitHub qui lit les paquets (`read:packages`). Docker le garde, pour les mises à jour |
| `--version X.Y.Z` | une autre version publiée que la plus haute |
| `--dir <dossier>` | un autre dossier que `/opt/button` |
| `--tls internal` | un essai sans domaine public. Caddy signe lui-même le certificat, que les navigateurs refusent, et le domaine n'est pas vérifié |
| `--from <archive>` | prendre les fichiers de la station dans une archive `station.tar.gz`, plutôt que sur GitHub |
| `--no-domain-check` | ne pas vérifier le domaine, quand la machine ne se joint pas elle-même par son adresse publique |

### D'où viennent les fichiers

Ils viennent de la page de chaque version publiée : `station`, `station.tar.gz` et `SHA256SUMS`. Pourquoi : voir la décision [0016](decisions/0016-le-dossier-vient-de-sa-version.md).

Une version publiée avant la commande `station`, comme la 0.1.0, n'a pas ces fichiers. Elle s'installe [à la main](#installer). La première version qui s'installe par `station install` sera la prochaine publiée. D'ici là, `releases/latest/download/station` ne trouve rien.

Pour essayer `main`, fabriquer l'archive depuis un clone, puis la copier sur la machine avec le script :

```bash
python3 scripts/version.py station main /tmp/station
scp /tmp/station/station /tmp/station/station.tar.gz <machine>:
```

Puis, sur la machine :

```bash
sudo bash station install --from station.tar.gz --github-token-file <fichier du jeton>
```

### Exploiter la station

Une fois installée, la station s'exploite par la même commande, en root : `sudo station <commande>`. `station help` les liste, et `station help <commande>` donne les options de chacune.

| Commande | Pour |
|---|---|
| `update` | la mettre à jour, vers la plus haute version publiée : voir [mettre à jour](#avec-la-commande-station) |
| `rollback` | défaire la dernière mise à jour : voir [revenir en arrière](#avec-station-rollback) |
| `status` | l'état de la station : sa version et la plus haute publiée, ses services, la place sur le disque, le prochain direct, la dernière sauvegarde, et les mises à jour, bloquées ou non. Elle sort en erreur quand un service ne va pas |
| `logs [service]` | les journaux, les 200 dernières lignes. `-f` les suit |
| `backup [archive]` | une sauvegarde, sans couper l'antenne. `--with-media` y met la banque de sons |
| `restore <archive>` | remettre une sauvegarde, sur la même machine ou sur une autre. `--without-media` garde la banque de sons en place |
| `config` | voir ou changer le domaine, l'e-mail du compte Let's Encrypt, les mises à jour et leur heure |
| `hold [raison]`, `unhold` | bloquer, puis débloquer les mises à jour |
| `cli <commande>` | une commande du moteur, par exemple `station cli users add studio --admin` |
| `uninstall` | désinstaller, en gardant les données |

Sauvegarder et restaurer : voir [`exploitation/sauvegarde.md`](exploitation/sauvegarde.md#avec-la-commande-station).

**Changer le domaine.** D'abord, faire mener le nouveau domaine à la machine, dans le DNS. Puis `sudo station config --domain nouveau.example` :

- la commande vérifie que chaque adresse du domaine mène à la machine, comme `install`. Caddy s'arrête le temps de la vérification, pour libérer le port 80 : le flux se coupe un moment. Si le domaine ne mène pas ici, rien ne change, et Caddy repart ;
- elle pose `DOMAIN` dans `.env`, puis recrée Caddy, qui demande le certificat ;
- les adresses publiques de **Réglages → Station** qui suivaient l'ancien domaine passent au nouveau. Celles qu'un admin a changées restent ;
- les encodeurs du direct se branchent ensuite sur le nouveau domaine.

**Les mises à jour.** `station update` les fait, à la main : voir [mettre à jour](#avec-la-commande-station). Réglées en automatique, le défaut, elles se feront seules quand la commande saura se lancer seule. `station config --updates manual` les passe à la main, `--update-time 03:30` change leur heure, à celle de la station, 04:00 par défaut. `station hold la grille de Noël` les bloque : elle pose le fichier `HOLD` dans le dossier de la station, avec la date et la raison. `station unhold` le retire. Un retour arrière le pose aussi : voir [revenir en arrière](#revenir-en-arrière).

**Désinstaller.** `sudo station uninstall` arrête la station, et retire ses conteneurs, ses images, les fichiers de sa version et la commande `station`. Restent `.env`, `data/`, `media/` et `backups/` : le script d'une version publiée, `sudo bash station install`, reprend la même station. `sudo station uninstall --purge` efface tout le dossier, données et sauvegardes comprises, une fois le mot `effacer` tapé. Ce qui vit hors du dossier, comme une banque de sons ailleurs (`BUTTON_MEDIA`), reste, et la commande le dit. Docker reste installé, avec le jeton du registre s'il y en a un : `docker logout ghcr.io` le retire.

## Installer

À la main, depuis un clone du dépôt : sur un réseau privé, pour plusieurs stations sur une machine, ou pour une version publiée avant la commande `station`.

```bash
git clone https://github.com/lazbutton/button.git
cd button
git checkout v0.1.0      # la plus haute version publiée
cd deploy
cp .env.example .env
chmod 600 .env
```

La version à prendre est la plus haute de la [page des versions](https://github.com/lazbutton/button/releases), marquée « Latest » : la mettre à la place de `v0.1.0`. Un correctif d'une ancienne version peut être publié après elle, sans la remplacer. Le dossier de la station suit la version qu'elle fait tourner, et `.env` la pose aussi : `BUTTON_VERSION=0.1.0`. Voir [mettre à jour](#mettre-à-jour). Dans `.env`, remplacer ensuite chaque `change-me` : voir [les secrets](#les-secrets). Puis choisir les chemins des données (`RT_DATA`, `BUTTON_MEDIA`…). Sans HTTPS devant la console, poser aussi `RT_COOKIE_SECURE=false` : voir [le cookie de session](#le-cookie-de-session). Ensuite :

```bash
docker compose pull && docker compose up -d
docker compose ps        # attendre radiotomate-scheduler « healthy »
```

Au premier démarrage, `radiotomate-init` prépare tout, et peut être relancé sans danger :

- vérifie d'abord les secrets : avec ceux de `.env.example`, il s'arrête, et ni le moteur, ni Icecast, ni nowplaying, ni le catalogue ne démarrent ; puis les noms des mounts : voir [les mounts](#les-mounts) ;
- crée `radiotomate.yaml`, la base, et applique les migrations du schéma ;
- crée l'arborescence de la banque de sons ;
- configure Beets (ReplayGain) ;
- branche les sorties Icecast, sur les mounts de `.env`, et le relais des métadonnées vers nowplaying ;
- règle le cookie de session : `Secure`, sauf avec `RT_COOKIE_SECURE=false` ;
- sur une installation neuve, sans aucun compte, ferme le harbor au mot de passe du compte : voir [le direct](#le-direct) ;
- crée le compte admin `RT_ADMIN_USER` s'il n'existe pas.

| Service | Adresse par défaut |
|---|---|
| Console | `http://<machine>:30126` |
| Flux Icecast | `http://<machine>:18000/radio.mp3` |
| Titre en cours | `http://<machine>:6820/now.json` |
| Catalogue | `http://<machine>:30127` |
| Direct, pour l'encodeur | `<machine>:6800` |

**Docker contourne le pare-feu.** Par défaut, ces ports sont publiés sur toutes les interfaces, en IPv4 et en IPv6, et un port publié par Docker reste joignable même si ufw le ferme. Sur un réseau privé, où l'on ouvre la console par l'adresse de la machine, c'est ce qu'il faut. Sur un VPS exposé à Internet, derrière [Caddy](#https) ou un autre reverse proxy HTTPS installé sur la machine, les lier à `127.0.0.1` dans `.env` :

```bash
BIND_ADDRESS=127.0.0.1
```

Puis `docker compose up -d`. Sur une station en service, il recrée la console, Icecast, nowplaying et le catalogue : les auditeurs d'Icecast sont déconnectés. Ces quatre ports ne répondent plus qu'à la machine elle-même. Caddy n'en a pas besoin : il joint les services par le réseau de Docker. Un autre reverse proxy les joint par `127.0.0.1`, par exemple `127.0.0.1:30126` pour la console, et non par `localhost`, qui peut viser d'abord `::1`, où rien n'écoute alors. La console, le flux et `now.json` ne s'ouvrent plus que par le reverse proxy. Vérifier ensuite depuis une autre machine, par exemple avec `nc -zv <machine> 30126`, et non avec `ufw status`.

`BIND_ADDRESS` vide garde l'écoute sur toutes les interfaces. `0.0.0.0` n'est pas pareil : il n'écoute qu'en IPv4. Une station qui suit l'ancienne consigne, une adresse dans chaque port (`CONSOLE_PORT=127.0.0.1:30126`), marche encore. Pour passer à `BIND_ADDRESS`, retirer ces adresses des quatre ports : avec les deux, `docker compose` refuse de démarrer, sur « invalid IP address ».

Le direct a son propre port, ouvert au public : voir [le direct](#le-direct).

## HTTPS

Sur Internet, Caddy se place devant la station. Il obtient un certificat Let's Encrypt pour le domaine, le renouvelle sans personne, redirige `http://` vers `https://`, et pose l'en-tête `Strict-Transport-Security`. Il fait partie de `compose.yml`, derrière le profil Compose `vps`, et lit le modèle [`deploy/Caddyfile`](../deploy/Caddyfile). Sur le domaine :

| Adresse | Service |
|---|---|
| `https://radio.example/` | la console |
| `https://radio.example/radio.mp3` | le flux : chaque mount d'Icecast à la racine, en MP3, AAC ou Ogg. Son nom se règle : voir [les mounts](#les-mounts) |
| `https://radio.example/status-json.xsl` | le statut d'Icecast |
| `https://radio.example/now.json` | le titre en cours |

L'administration d'Icecast et le mount WAV du moniteur n'y passent pas. Le direct non plus : il a son propre port. Pourquoi le flux passe par Caddy : voir la décision [0015](decisions/0015-le-flux-passe-par-caddy.md).

Avant de commencer, le domaine pointe sur la machine : un enregistrement A, et AAAA si elle a une adresse IPv6. Ses ports 80 et 443 sont libres, et le pare-feu de l'hébergeur les laisse passer : Let's Encrypt vérifie le domaine par eux, et refuse le domaine un moment après quelques échecs. Docker publie ces ports sans passer par ufw : rien à y ouvrir. Dans `.env` :

```bash
COMPOSE_PROFILES=vps
DOMAIN=radio.example
ACME_EMAIL=admin@radio.example
BIND_ADDRESS=127.0.0.1
```

`COMPOSE_PROFILES=vps` ajoute Caddy à chaque commande `docker compose` lancée dans ce dossier. `ACME_EMAIL`, facultatif, est l'e-mail du compte Let's Encrypt. Puis :

```bash
docker compose up -d
docker compose logs caddy        # attendre « certificate obtained successfully »
```

Sans `DOMAIN`, Caddy ne démarre pas, et son journal le dit. Il garde ses certificats et son compte Let's Encrypt dans `data/caddy`, ou dans `CADDY_DATA`. Ce dossier se garde d'une version à l'autre : sans lui, Caddy redemande un certificat à chaque démarrage, et Let's Encrypt en limite le nombre.

Ensuite, dans la console, **Réglages → Station**, donner les adresses publiques : le flux `https://radio.example/radio.mp3`, le titre en cours `https://radio.example/now.json`, le statut `https://radio.example/status-json.xsl`, et l'hôte du direct, `radio.example`. Le flux et `now.json` sont alors sur le domaine de la console : sa CSP n'a rien à déclarer, `CSP_MEDIA_SRC` et `CSP_CONNECT_SRC` restent vides. Un flux sur un autre domaine ou un autre port s'y déclare : voir [les en-têtes de sécurité](#les-en-têtes-de-sécurité).

Vérifier depuis une autre machine. Seuls répondent 22 pour SSH, 80, 443, en TCP et en UDP pour HTTP/3, et le port du direct :

```bash
nc -zv radio.example 80 443 6800              # ouverts
nc -zv radio.example 30126 18000 6820 30127   # fermés
```

Puis le contrôle après déploiement, sur les adresses publiques. Il est décrit dans [mettre à jour](#mettre-à-jour) :

```bash
scripts/smoke.sh https://radio.example https://radio.example/radio.mp3
```

Caddy lit le `Caddyfile` à son démarrage. Un `Caddyfile` changé, à la main ou par une mise à jour, ne compte qu'une fois Caddy recréé. L'écoute à travers Caddy se coupe un instant :

```bash
docker compose up -d --force-recreate caddy
```

Pour un essai sans Let's Encrypt, sur une machine sans domaine public ou en CI, poser `CADDY_TLS=internal`. Caddy signe alors lui-même son certificat. Les navigateurs le refusent ; `curl` l'accepte avec `--cacert data/caddy/pki/authorities/local/root.crt`.

La console voit l'adresse de chaque client, pour limiter les essais de connexion : nginx croit celle que Caddy lui transmet, car Caddy est dans un réseau privé, celui de Docker. C'est le réglage par défaut de `TRUSTED_PROXIES` : voir [l'API](api.md#session).

Icecast voit l'adresse de Caddy pour chaque auditeur. Il compte toujours les auditeurs, mais ne connaît plus leurs adresses. Caddy ne tient pas de journal des accès, et retire l'adresse du client de ses messages, comme celui qui note le départ d'un auditeur : aucune adresse d'auditeur n'est gardée.

## Le direct

Le harbor, l'entrée du direct, est publié sur le port 6800 de la machine, ou sur `HARBOR_PORT`, et sur toutes ses interfaces : un encodeur s'y branche de n'importe où. `BIND_ADDRESS` ne le ferme pas, et il ne passe pas par Caddy. Avec un autre port que 6800, le régler aussi dans la console, **Réglages → Station** : le panneau « Passer en direct » le donne alors à chaque compte, avec l'hôte du direct. `station install` règle les deux. Sans hôte réglé, le panneau ne donne pas d'adresse : il dit qu'un admin la règle.

Pour l'écouter sur une seule adresse, la mettre devant le port : `HARBOR_PORT=127.0.0.1:6800` le ferme aux autres machines. Un ancien `compose.override.yml` qui publiait le harbor se retire **avant** la mise à jour : s'il le publiait sur une adresse précise, le port est pris deux fois, et le playout ne démarre plus.

Le harbor ne chiffre rien : l'identifiant et le mot de passe de l'encodeur passent en clair. Sur une machine exposée à Internet, il ne doit donc accepter que les jetons d'encodeur, qui n'ouvrent que le harbor, et refuser le mot de passe du compte : `features.allow_account_password` à faux. Une station neuve le règle dès son installation : `radiotomate-init` le pose, et chaque encodeur entre avec le jeton de son compte. Une station en service le règle quand chaque encodeur a son jeton. La marche à suivre : [refuser le mot de passe du compte](exploitation/passer-en-direct.md#refuser-le-mot-de-passe-du-compte).

## Les mounts

Icecast diffuse la station sur deux mounts, nommés dans `.env` :

| Variable | Sans elle | Le mount |
|---|---|---|
| `ICECAST_MOUNT` | `radio.mp3` | le flux public, en MP3 : `https://radio.example/radio.mp3` derrière Caddy |
| `ICECAST_MONITOR_MOUNT` | `studio.wav` | le casque de la console, en WAV, qui reste sur le réseau de la station |

Un nom seul, sans dossier ni espace, en lettres, chiffres, point, tiret ou souligné, en `.mp3` pour le flux public et en `.wav` pour le casque : Caddy ne relaie que les mounts à la racine. Avec un autre nom, `radiotomate-init` s'arrête et dit lequel corriger : l'antenne ne démarre pas.

Changer le mount public change l'adresse du flux, pour chaque auditeur : `radiotomate-init` le dit dans son journal. Recréer ensuite toute la station, Icecast compris, avec `docker compose up -d --force-recreate`. Puis, dans la console, **Réglages → Station**, changer aussi le flux public. `station install` et `station config --domain` prennent le mount de `.env`.

Une station installée avant ces deux variables diffusait sur `button.mp3`. Pour garder l'adresse de son flux, poser `ICECAST_MOUNT=button.mp3` dans `.env` avant de passer à la version qui les lit.

## Les secrets

`.env` porte cinq secrets. Les quatre secrets de machine, que personne ne tape, sont `ICECAST_SOURCE_PASSWORD`, `ICECAST_ADMIN_PASSWORD`, `RT_NOWPLAYING_SECRET` et `MEILI_MASTER_KEY`. Vide, l'un d'eux arrête déjà `docker compose`, qui le nomme. Ensuite, à chaque démarrage et avant de toucher à la base, `radiotomate-init` les vérifie. Il s'arrête si un secret vaut `change-me`, la valeur de `.env.example`, connue de tous, ou si un secret de machine fait moins de 24 caractères. Le moteur, Icecast, nowplaying et le catalogue l'attendent : aucun ne démarre, et l'antenne reste coupée. Pour tirer un secret :

```bash
openssl rand -hex 24
```

`RT_ADMIN_PASSWORD` est le mot de passe du compte admin `RT_ADMIN_USER`. `radiotomate-init` crée ce compte quand il manque : au premier démarrage, mais aussi après sa suppression ou un changement de son nom. Il n'a pas de longueur minimale. Une fois le compte créé, vider `RT_ADMIN_PASSWORD` : sinon, un compte admin supprimé revient au démarrage suivant, avec ce mot de passe. Vide, il n'est refusé qu'à la première installation, qui démarrerait sans compte admin. Le changer ne change pas un compte existant : un compte créé avec `change-me` garde ce mot de passe, à changer dans la console, Mon compte. D'ici là, `radiotomate-init` le rappelle dans son journal à chaque démarrage, sans bloquer.

Quand le contrôle refuse, le journal de `radiotomate-init` nomme chaque variable à changer, et la commande pour repartir : `docker compose logs radiotomate-init`. Il ne montre jamais la valeur d'un secret. Le contrôle passe à chaque `docker compose up`, pas au redémarrage de la machine. Un moteur déjà en marche continue donc de tourner, mais ne repart pas quand il est recréé, par une mise à jour par exemple.

Pour savoir avant une mise à jour si la station démarrera, lancer le contrôle seul, une fois le dossier passé à la nouvelle version et ses images tirées, avant `docker compose up`. Il n'écrit rien et n'arrête rien :

```bash
docker compose run --rm --no-deps -e RT_INIT_CHECK_ONLY=1 radiotomate-init
```

Il répond « Secrets : rien ne bloque le démarrage », ou nomme ce qu'il faut changer. `RT_INIT_CHECK_ONLY` se passe ainsi, sur la ligne de commande, jamais dans `.env`.

Pour changer un secret de machine, sur une station en service comme sur une station bloquée par le contrôle, modifier `.env`, puis recréer toute la station :

```bash
docker compose up -d --force-recreate
```

L'antenne se coupe le temps du redémarrage. Sur une station en service, un simple `docker compose up -d` ne suffit pas : il ne recrée que les services dont la configuration change. Icecast prend alors le nouveau mot de passe, mais le playout garde l'ancien, et le flux tombe. Pour `RT_ADMIN_PASSWORD` seul, `docker compose up -d` suffit : seul `radiotomate-init` le lit.

En secours seulement, poser `RT_ALLOW_SHORT_SECRETS=1` dans `.env`, puis lancer `docker compose up -d`, laisse démarrer une station dont un secret de machine est trop court. `radiotomate-init` le rappelle alors dans son journal à chaque démarrage. Un secret vide ou à `change-me` reste refusé. Remplacer ensuite les secrets trop courts, retirer la ligne, puis recréer toute la station. Pourquoi une variable de `.env` et non un réglage de la console : voir la décision [0014](decisions/0014-interrupteur-avant-le-moteur.md).

## Le cookie de session

Par défaut, le cookie de session porte l'attribut `Secure` : le navigateur ne l'accepte et ne le renvoie qu'en `https://`. Seule exception, Chrome et Firefox l'acceptent aussi sur `http://localhost`. Une fois connecté en HTTPS, ouvrir par erreur une adresse en `http://` n'envoie donc pas la session en clair.

Pour un accès en HTTP seul, sur un banc local ou un réseau privé, poser `RT_COOKIE_SECURE=false` dans `.env`. Sinon, personne ne peut se connecter : la console accepte le mot de passe, puis dit que le navigateur a refusé le cookie de session. En HTTP, le mot de passe et le cookie passent en clair : à réserver à un réseau de confiance. Avec `false`, `radiotomate-init` le rappelle dans son journal à chaque démarrage (`docker compose logs radiotomate-init`).

Pour changer `RT_COOKIE_SECURE` sur une station en service, modifier `.env`, puis recréer les trois services du moteur ensemble, comme pour [un réglage du moteur](#régler-le-moteur) : `radiotomate-init` repasse d'abord et réécrit `radiotomate.yaml`.

Derrière un reverse proxy, le journal de `radiotomate-interface` peut afficher « Secure cookies will be ignored on insecure requests » : le moteur ne voit que le HTTP de nginx. Quand le navigateur est en `https://`, ce message est sans conséquence.

## Avant d'exposer une station à Internet

Une installation sur une machine exposée reste un essai tant que les fiches [P1](feuille-de-route/P1-mise-en-prod.md) ne sont pas toutes faites. Celles de sécurité le sont : catalogue protégé, essais de connexion limités, identifiants d'encodeur, en-têtes. Restent surtout la commande de mise à jour, son retour arrière, les sauvegardes hors de la machine et les alertes. Sur une telle machine, fermer aussi les ports avec `BIND_ADDRESS=127.0.0.1`, derrière Caddy : voir [HTTPS](#https).

## Régler le moteur

`RT_DATA/radiotomate.yaml` porte les réglages fins : sorties audio, alertes (`alerts:`, webhook ou Vikunja), rétention (`retention:`), métriques (`metrics:`), relais des métadonnées (`metadata_log:`). Après un changement, recréer les trois services du moteur ensemble :

```bash
docker compose up -d --force-recreate radiotomate-playout radiotomate-interface radiotomate-scheduler
```

**Ne jamais redémarrer `radiotomate-playout` seul** : l'interface et le scheduler partagent son réseau, et deviendraient injoignables.

## Les en-têtes de sécurité

Le nginx de la console pose ces en-têtes sur chaque réponse :

| En-tête | Valeur | Pour |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | un fichier n'est jamais lu comme un script |
| `X-Frame-Options` | `DENY` | aucune page de la console dans un cadre d'un autre site |
| `Referrer-Policy` | `strict-origin-when-cross-origin`, et `no-referrer` pour un invité | l'adresse d'une page ne fuit pas vers un autre site |
| `Permissions-Policy` | `camera=(), microphone=()` | ni caméra ni micro |
| `Content-Security-Policy-Report-Only` | voir plus bas | les sources permises de chaque ressource |

`Strict-Transport-Security` vient du reverse proxy HTTPS, pas de la console : Caddy le pose, voir [HTTPS](#https).

La CSP est en rodage : elle ne bloque rien. Le navigateur signale dans sa console, celle des outils de développement, ce qu'elle bloquerait, sur des lignes qui commencent par `[Report Only]`. Elle permet l'origine de la console, plus `blob:` pour l'écoute. Quand le flux et `now.json` passent par le même domaine que la console, derrière le reverse proxy, il n'y a rien à régler.

Sinon, sur un autre domaine ou sur un port publié comme `18000` ou `6820`, déclarer leurs origines à la console, séparées par des espaces :

| Variable | Pour | Exemple |
|---|---|---|
| `CSP_MEDIA_SRC` | le flux et Icecast : l'écoute, le moniteur, le statut | `https://flux.radio.example` |
| `CSP_CONNECT_SRC` | `now.json`, et toute autre adresse que la console lit | `https://titre.radio.example` |

Les poser dans `.env` :

```bash
CSP_MEDIA_SRC=https://flux.radio.example
CSP_CONNECT_SRC=https://titre.radio.example
```

Puis `docker compose up -d console`. Une valeur qui contient autre chose que des adresses, comme un guillemet ou un point-virgule, empêche la console de démarrer : `docker compose logs console` dit pourquoi. Pour vérifier les deux variables, ouvrir la console, lancer l'écoute, puis chercher des lignes `[Report Only]` dans la console du navigateur.

## Mettre à jour

BUTTON se met à jour par versions publiées, numérotées `X.Y.Z`. Chacune a ses notes, sur la [page des versions](https://github.com/lazbutton/button/releases) et dans le [CHANGELOG](../CHANGELOG.md). Son numéro dit ce qu'elle demande :

| Version | Exemple | Ce qu'elle demande |
|---|---|---|
| un correctif | `0.1.0` → `0.1.1` | rien : ni migration du schéma, ni action. Revenir en arrière ne touche pas la base |
| une mineure | `0.1.1` → `0.2.0` | rien non plus, mais elle peut migrer le schéma : revenir en arrière demande alors de le redescendre |
| une majeure | `0.2.0` → `1.0.0` | une action, dite en tête de ses notes, à faire avant de mettre à jour |

`BUTTON_VERSION`, dans `.env`, choisit les sept images de BUTTON, ensemble :

| `BUTTON_VERSION` | La station tire |
|---|---|
| `0.1.0` | cette version, rien d'autre : le choix d'une station à l'antenne, avec son dossier à la même version |
| absente ou vide | `stable`, la plus haute version publiée : un `docker compose pull` peut alors changer de version sans que le dossier suive |
| `0.1` | les correctifs de la 0.1, jusqu'à la version suivante. Ensuite, plus rien, pas même un correctif de sécurité |
| `main` | chaque changement de `main`, pour les essais, jamais à l'antenne |

Le dossier de la station suit la même version que ses images : `compose.yml`, et les scripts qu'il monte dans les conteneurs, comme `init-radiotomate.sh`. Une station à l'antenne épingle donc sa version dans `.env`, et la change à chaque mise à jour, avec son dossier. Les images des autres projets, meilisearch, tusd, rclone et Caddy, sont épinglées dans `compose.yml`, et changent avec lui. Une station qui avait `RT_TAG` dans `.env` retire la ligne : il n'est plus lu, et, posé, il arrête `docker compose`, qui le dit.

### Avec la commande station

Une station installée par `station install` se met à jour en une commande, en root :

```bash
sudo station update
```

Elle passe à la plus haute version publiée, ou à celle de `--version X.Y.Z`, plus récente que la sienne. Dans l'ordre :

1. **Elle télécharge les fichiers de la version**, et vérifie leur somme, comme `station install`. La suite est faite par la commande `station` de cette version : elle sait ce que sa version demande.
2. **Elle vérifie que rien ne s'y oppose.** `HOLD` bloque toute mise à jour, et une restauration pas finie aussi. Une version majeure l'arrête : elle cite l'action que demandent ses notes, leur paragraphe « Mise en service », et ne change rien ; une fois l'action faite, la relancer avec `--major`. Un direct ou une diffusion de l'Agenda à l'antenne, ou qui commence dans les 30 minutes, l'arrête aussi : le moteur le dit, par `radiotomate maintenance window`, d'après la grille, l'Agenda et ce qui passe par le harbor. Un moteur d'avant cette commande ne le dit pas : la mise à jour se fait, et prévient. `--force` passe outre ce direct, pas `HOLD`.
3. **Elle sauvegarde la station**, comme `station backup`, sans les sons, dans `backups/`, avec le script de sauvegarde de la version : celui d'une 0.2.0 ne tourne pas dans l'image du moteur. Seules les cinq dernières archives de `backups/` restent, celles de `station backup` comprises.
4. **Elle ajoute à `.env` ce que la version y demande de nouveau**, avec sa valeur par défaut : un secret qui manque, ou une variable que la version d'avant ne connaissait pas. Une variable qu'elle connaissait, et que `.env` n'a plus, a été retirée exprès, comme `COMPOSE_PROFILES` derrière un autre proxy : elle ne revient pas, et la commande le dit. Puis elle **tire ses images**, pendant que l'antenne joue encore. Si elles ne se tirent pas, la station reste à sa version : seules la sauvegarde, et ce que `.env` a reçu, restent.
5. **Elle relit la fenêtre**, que le tirage a pu faire attendre : un direct qui s'est rapproché l'arrête encore, avant tout changement de la station.
6. **Elle pose les fichiers de la version.** `.env` et `compose.override.yml` restent, et `BUTTON_VERSION` passe à la version. Un fichier de la version que la station avait changé reste à côté, en `.local-…` : les changements d'une station vont dans `compose.override.yml`.
7. **Elle redémarre la station** : les trois services du moteur ensemble, puis les autres, puis ceux d'un autre profil qui tournaient, comme `share`. Un service à l'image épinglée qui monte un fichier changé de la version, comme Caddy et son `Caddyfile`, est recréé lui aussi. L'antenne se coupe le temps du redémarrage.
8. **Elle la contrôle** : son adresse en HTTPS, puis `scripts/smoke.sh`, décrit plus bas.

Si les fichiers ne se posent pas, si la station ne redémarre pas, ou si le contrôle échoue, elle revient seule à la version d'avant, base comprise, et bloque les mises à jour suivantes : voir [revenir en arrière](#seule-quand-une-mise-à-jour-échoue).

Au clavier, elle demande une confirmation avant la sauvegarde ; `--yes` répond pour un script. `--from station.tar.gz` prend les fichiers de la version dans une archive, comme `station install`, `main` compris, pour un essai. Sur une machine distante, la lancer dans `tmux` ou `screen` : une connexion SSH coupée en plein redémarrage l'arrête là, et la station revient alors à la version d'avant.

Chaque mise à jour se note dans `updates.log`, dans le dossier de la station, à l'heure de son début : faite, arrêtée, annulée quand la station est revenue seule à la version d'avant, ou échouée, avec la sauvegarde d'avant. `station status` dit la dernière.

La version de chaque service, d'après ses images, est relevée après chaque installation, mise à jour ou restauration, dans `versions.json`, avec les données du moteur. `GET /system/version.json` la donne aux admins : voir [api.md](api.md#système).

**Depuis la 0.2.0.** Sa commande `station` n'a pas `update`. Prendre celle de la version publiée, comme pour une installation, puis la lancer : elle trouve la station dans `/opt/button`.

```bash
curl -fsSLO https://github.com/lazbutton/button/releases/latest/download/station
sudo bash station update
```

### À la main

Une station installée depuis un clone du dépôt, sans `station install`, se met à jour à la main. Avant de mettre à jour, lire les notes de chaque version sautée, et s'assurer que les secrets laisseront la station démarrer : voir [les secrets](#les-secrets). Puis, depuis le dossier du dépôt, pour passer en `0.2.0` par exemple :

```bash
git fetch --tags --force
git checkout v0.2.0
cd deploy
# .env : BUTTON_VERSION=0.2.0
docker compose pull && docker compose up -d
```

Si `docker compose pull` échoue, sur une version mal écrite par exemple, ne pas lancer `up` : faute d'image, il la construirait sur la machine, depuis le dossier. Chaque version reconstruit ses sept images : `up -d` recrée tous les services, Icecast compris. L'antenne se coupe le temps du redémarrage du moteur, et les auditeurs se reconnectent.

Une station qui suit `main` reste sur la branche `main`, et `git pull` y remplace `git fetch` et `git checkout`. Pour la passer à une version publiée, regarder d'abord si `main` a migré le schéma plus loin que cette version, comme pour [revenir en arrière](#revenir-en-arrière).

Chaque image porte sa version. Pour vérifier celle qui tourne :

```bash
docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' \
  "$(docker compose ps -q radiotomate-scheduler)"
```

Elle répond `0.2.0`, ou pour `main` le tag daté de l'image, `AAAAMMJJ-sha7`.

Ensuite, vérifier que l'antenne tourne, sans compte, depuis le dossier de la station :

```bash
scripts/smoke.sh http://127.0.0.1:30126 http://127.0.0.1:18000/radio.mp3
```

Le contrôle prend l'adresse de la console, puis celle du flux public. Sur la machine, avec les ports par défaut, ce sont celles de l'exemple. Derrière un reverse proxy, donner plutôt leurs adresses publiques, en `https://`, pour le vérifier lui aussi : le contrôle ne suit pas les redirections. Il vérifie, dans l'ordre :

1. le playout, l'interface et le scheduler sont `healthy`, en attendant deux minutes au plus ;
2. la console répond et relaie le moteur : `/` et `/health/ready` répondent 200 ;
3. le scheduler est prêt : son `/health/ready`, lu dans son conteneur, répond 200 ;
4. sans cookie, la recherche de la médiathèque répond 401 ;
5. le flux envoie de l'audio, et `now.json`, lu dans le conteneur de nowplaying, répond.

Au premier point qui échoue, il s'arrête en erreur, nomme le point et ce qui ne va pas, et dit quel journal lire. Un service du moteur arrêté le fait échouer tout de suite, sans attendre. Le point 4 ne voit pas un catalogue arrêté : sans cookie, nginx répond 401 sans le joindre. Sur une machine lente, `SMOKE_WAIT=300 scripts/smoke.sh …` attend la santé du moteur cinq minutes. Le contrôle appelle `docker compose` sans option : une station lancée avec `-p <station>` ou `--env-file <fichier>` se contrôle avec `COMPOSE_PROJECT_NAME=<station>` ou `COMPOSE_ENV_FILES=<fichier>` devant la commande. Le contrôle ne change rien à la station : il sert aussi après une installation, ou à tout moment.

## Revenir en arrière

Une station installée par `station install` revient en arrière par sa commande : seule, quand une mise à jour échoue, ou par `station rollback`. Les autres reviennent à la main.

### Seule, quand une mise à jour échoue

`station update` se défait si les fichiers de la version ne se posent pas, si la station ne redémarre pas, ou si le contrôle échoue : une image qui ne démarre pas, une migration du schéma qui échoue à mi-chemin, un flux qui ne répond plus. La station revient à la version d'avant :

- ses fichiers, tels qu'ils étaient dans le dossier, et `BUTTON_VERSION` dans `.env` ;
- ses images, pour tous les services, recréés, les trois du moteur ensemble ;
- la base d'avant la mise à jour, si le schéma a migré : la version d'avant ne lit pas un schéma plus récent. C'est la copie que le moteur fait avant de migrer, dans `RT_DATA/backups/`. Ce qui s'est écrit depuis est perdu, et `updates.log` le dit. La base de la nouvelle version reste à côté, dans `RT_DATA/backups/avant-restauration-….db`.

Puis elle la contrôle, comme après une mise à jour. Avant de recréer les conteneurs de la nouvelle version, elle garde leurs journaux dans `updates-failed.log`, dans le dossier de la station, en droits 600 : de quoi voir pourquoi elle n'a pas démarré.

Elle pose ensuite `HOLD`, qui bloque les mises à jour suivantes jusqu'à ce qu'une personne le retire, la cause trouvée : `station unhold`. `updates.log` note la mise à jour « annulée », et `station status` la dit. L'alerte « mise à jour annulée » part dans le journal du système, `journalctl -t button` ; sur un téléphone et par e-mail, ce sera avec les alertes de SUR-01. La commande sort en erreur.

Si le retour échoue lui aussi, la commande le dit, `updates.log` le note « échouée », et `HOLD` bloque de même. `station rollback` refait le retour ; `station install` répare la station sur la version de `.env`.

Revenue en 0.2.0, une station retrouve la commande `station` de la 0.2.0, qui n'a ni `status` ni `unhold` : `rm /opt/button/HOLD` débloque les mises à jour, et la commande de la version publiée fait le reste, comme pour la première mise à jour.

### Avec station rollback

Une mise à jour passée peut décevoir ensuite. `sudo station rollback` défait la dernière, celle que note `updates.log`, et ramène la station à la version d'avant :

- ses fichiers, d'après l'archive de cette version, vérifiée par sa somme comme pour `station install`, ou celle de `--from`. Un fichier que la station avait changé reste à côté, en `.local-…` ;
- ses images, pour tous les services. Celles qui manquent se tirent d'abord, pendant que l'antenne joue ;
- la base d'avant la mise à jour, si le schéma a migré, comme quand une mise à jour échoue. La question au clavier dit de quand date cette base, et ce qui se perd : tout ce qui s'est écrit depuis, comptes, conducteur, Agenda et réglages compris. La base d'aujourd'hui reste à côté. Pour garder ces écritures, redescendre plutôt le schéma, à la main : voir plus bas.

Puis le contrôle, une ligne « retour arrière » dans `updates.log`, `HOLD`, et l'alerte. Au clavier, elle demande une confirmation ; `--yes` répond pour un script. Une mise à jour revenue seule, ou déjà défaite, n'a plus rien à défaire.

### À la main

Revenir à la version d'avant, `0.1.0` par exemple, c'est la reposer : le dossier de la station à `v0.1.0`, et `BUTTON_VERSION=0.1.0` dans `.env`. Le schéma de la base décide du reste. `radiotomate-init` applique les migrations à chaque démarrage, mais une image plus ancienne ne sait pas défaire celles qu'elle ne connaît pas : le playout ne démarre plus.

Le schéma a migré si une copie `avant-vNN-…` de la base est apparue dans `RT_DATA/backups/` depuis la mise à jour : `avant-v19-…` est la base d'avant la migration v19, donc en v18. Les notes d'une version qui migre donnent aussi la version de son schéma. Un correctif ne migre jamais : la CI refuse de le publier.

Sans migration, depuis le dossier du dépôt :

```bash
git checkout v0.1.0
cd deploy
# .env : BUTTON_VERSION=0.1.0
docker compose pull && docker compose up -d
```

Avec une migration, il y a deux chemins :

- redescendre le schéma **avec l'image récente**, celle qui tourne. Une migration défaite perd les données qu'elle avait ajoutées ;
- remettre la copie de la base faite avant la migration : voir [remettre la copie](exploitation/sauvegarde.md#remettre-la-copie). Ce qui a été écrit depuis la mise à jour est perdu.

Pour redescendre le schéma, arrêter le moteur, ses services ensemble, puis le redescendre à la version du schéma de l'ancienne version, avant de reposer celle-ci. Depuis `deploy/`, pour revenir en v18 :

```bash
docker compose stop radiotomate-scheduler radiotomate-interface radiotomate-playout radiotomate-dropbox
docker compose run --rm --no-deps --entrypoint radiotomate radiotomate-init \
  -c /data/radiotomate.yaml update --target-version 18
git checkout v0.1.0
# .env : BUTTON_VERSION=0.1.0
docker compose pull && docker compose up -d
```

L'antenne reste coupée de l'arrêt du moteur à son redémarrage. Sauvegarder avant : voir [`exploitation/sauvegarde.md`](exploitation/sauvegarde.md).

Une station installée par `station install` n'a pas de clone : les fichiers de la version d'avant sont dans son archive. Depuis le dossier de la station, pour revenir en `0.2.0` :

```bash
curl -fsSLO https://github.com/lazbutton/button/releases/download/v0.2.0/station.tar.gz
curl -fsSLO https://github.com/lazbutton/button/releases/download/v0.2.0/SHA256SUMS
grep station.tar.gz SHA256SUMS | sha256sum -c
tar -xzf station.tar.gz
# .env : BUTTON_VERSION=0.2.0
docker compose pull && docker compose up -d
```

Avec une migration, d'abord redescendre le schéma, ou remettre la copie de la base, comme plus haut. La sauvegarde que `station update` fait avant de changer, dans `backups/`, se remet par `station restore`, une fois la version d'avant reposée, si sa commande `station` a `restore` : la 0.2.0 ne l'a pas, et ses scripts de sauvegarde demandent `sqlite3`, que l'image du moteur n'a pas. Pour elle, remettre la copie de la base faite avant la migration : voir [remettre la copie](exploitation/sauvegarde.md#remettre-la-copie).

Une station qui suit `main` ne revient pas à un tag daté : il n'existe que pour les images reconstruites ce jour-là, pas pour les sept. Elle revient à une version publiée, de la même façon.

## Exploiter

| Fiche | Pour |
|---|---|
| [`passer-en-direct.md`](exploitation/passer-en-direct.md) | brancher un encodeur, les créneaux des animateurs |
| [`deposer-un-programme.md`](exploitation/deposer-un-programme.md) | envoyer de la musique et des émissions |
| [`dossier-reseau.md`](exploitation/dossier-reseau.md) | ouvrir la médiathèque dans le Finder |
| [`bacs-dropbox.md`](exploitation/bacs-dropbox.md) | ouvrir un bac aux sons déposés dans Dropbox (profil `cloud`) |
| [`decrochage.md`](exploitation/decrochage.md) | partager l'antenne avec une autre radio |
| [`le-flux-est-tombe.md`](exploitation/le-flux-est-tombe.md) | diagnostiquer une coupure |
| [`sauvegarde.md`](exploitation/sauvegarde.md) | sauvegarder et restaurer |

## Plusieurs stations

Chaque station a son propre dossier de données, sa propre base et son propre `.env`. Pour en faire tourner plusieurs sur une machine, donner à chacune un nom de projet Compose (`docker compose -p <station>`) et des ports distincts, `HARBOR_PORT` compris. Le profil `vps` ne sert qu'à l'une d'elles : les ports 80 et 443 ne se partagent pas.
