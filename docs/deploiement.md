# Déployer une station

Une station complète tient dans [`deploy/compose.yml`](../deploy/compose.yml) : moteur, console, Icecast, titre en cours, catalogue et envoi reprenable. Les images sont publiées par la CI sur `ghcr.io/lazbutton`.

## Prérequis

- Une machine Linux x86-64 avec Docker et Compose v2. Les images ne sont construites que pour `linux/amd64`.
- De la place pour la banque de sons.
- Pour un accès public, un domaine qui pointe sur la machine, et ses ports 80 et 443 libres. Caddy, dans `compose.yml`, s'occupe du HTTPS : voir [HTTPS](#https).

## Installer

```bash
git clone https://github.com/lazbutton/button.git
cd button/deploy
cp .env.example .env
chmod 600 .env
```

Dans `.env`, remplacer chaque `change-me` : voir [les secrets](#les-secrets). Puis choisir les chemins des données (`RT_DATA`, `BUTTON_MEDIA`…). Sans HTTPS devant la console, poser aussi `RT_COOKIE_SECURE=false` : voir [le cookie de session](#le-cookie-de-session). Ensuite :

```bash
docker compose pull
docker compose up -d
docker compose ps        # attendre radiotomate-scheduler « healthy »
```

Au premier démarrage, `radiotomate-init` prépare tout, et peut être relancé sans danger :

- vérifie d'abord les secrets : avec ceux de `.env.example`, il s'arrête, et ni le moteur, ni Icecast, ni nowplaying ne démarrent ;
- crée `radiotomate.yaml`, la base, et applique les migrations du schéma ;
- crée l'arborescence de la banque de sons ;
- configure Beets (ReplayGain) ;
- branche la sortie Icecast et le relais des métadonnées vers nowplaying ;
- règle le cookie de session : `Secure`, sauf avec `RT_COOKIE_SECURE=false` ;
- crée le compte admin `RT_ADMIN_USER` s'il n'existe pas.

| Service | Adresse par défaut |
|---|---|
| Console | `http://<machine>:30126` |
| Flux Icecast | `http://<machine>:18000/button.mp3` |
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
| `https://radio.example/button.mp3` | le flux : chaque mount d'Icecast à la racine, en MP3, AAC ou Ogg |
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

Ensuite, dans la console, **Réglages → Station**, donner les adresses publiques : le flux `https://radio.example/button.mp3`, le titre en cours `https://radio.example/now.json`, le statut `https://radio.example/status-json.xsl`, et l'hôte du direct, `radio.example`. Le flux et `now.json` sont alors sur le domaine de la console : sa CSP n'a rien à déclarer, `CSP_MEDIA_SRC` et `CSP_CONNECT_SRC` restent vides. Un flux sur un autre domaine ou un autre port s'y déclare : voir [les en-têtes de sécurité](#les-en-têtes-de-sécurité).

Vérifier depuis une autre machine. Seuls répondent 22 pour SSH, 80, 443, en TCP et en UDP pour HTTP/3, et le port du direct :

```bash
nc -zv radio.example 80 443 6800              # ouverts
nc -zv radio.example 30126 18000 6820 30127   # fermés
```

Puis le contrôle après déploiement, sur les adresses publiques. Il est décrit dans [mettre à jour](#mettre-à-jour) :

```bash
scripts/smoke.sh https://radio.example https://radio.example/button.mp3
```

Caddy lit le `Caddyfile` à son démarrage. Un `Caddyfile` changé, à la main ou par une mise à jour, ne compte qu'une fois Caddy recréé. L'écoute à travers Caddy se coupe un instant :

```bash
docker compose up -d --force-recreate caddy
```

Pour un essai sans Let's Encrypt, sur une machine sans domaine public ou en CI, poser `CADDY_TLS=internal`. Caddy signe alors lui-même son certificat. Les navigateurs le refusent ; `curl` l'accepte avec `--cacert data/caddy/pki/authorities/local/root.crt`.

Icecast voit l'adresse de Caddy pour chaque auditeur. Il compte toujours les auditeurs, mais ne connaît plus leurs adresses. Caddy ne tient pas de journal des accès, et retire l'adresse du client de ses messages, comme celui qui note le départ d'un auditeur : aucune adresse d'auditeur n'est gardée.

## Le direct

Le harbor, l'entrée du direct, est publié sur le port 6800 de la machine, ou sur `HARBOR_PORT`, et sur toutes ses interfaces : un encodeur s'y branche de n'importe où. `BIND_ADDRESS` ne le ferme pas, et il ne passe pas par Caddy. Avec un autre port que 6800, le donner aux animateurs : le panneau « Passer en direct » de la console affiche encore 6800.

Pour l'écouter sur une seule adresse, la mettre devant le port : `HARBOR_PORT=127.0.0.1:6800` le ferme aux autres machines. Un ancien `compose.override.yml` qui publiait le harbor se retire **avant** la mise à jour : s'il le publiait sur une adresse précise, le port est pris deux fois, et le playout ne démarre plus.

Le harbor ne chiffre rien : l'identifiant et le mot de passe de l'encodeur passent en clair. Sur une machine exposée à Internet, il ne doit donc accepter que les jetons d'encodeur, qui n'ouvrent que le harbor, et refuser le mot de passe du compte : `features.allow_account_password` à faux. Une station neuve le règle tout de suite, une station en service quand chaque encodeur a son jeton. La marche à suivre : [refuser le mot de passe du compte](exploitation/passer-en-direct.md#refuser-le-mot-de-passe-du-compte).

## Les secrets

`.env` porte cinq secrets. Les quatre secrets de machine, que personne ne tape, sont `ICECAST_SOURCE_PASSWORD`, `ICECAST_ADMIN_PASSWORD`, `RT_NOWPLAYING_SECRET` et `MEILI_MASTER_KEY`. Vide, l'un d'eux arrête déjà `docker compose`, qui le nomme. Ensuite, à chaque démarrage et avant de toucher à la base, `radiotomate-init` les vérifie. Il s'arrête si un secret vaut `change-me`, la valeur de `.env.example`, connue de tous, ou si un secret de machine fait moins de 24 caractères. Le moteur, Icecast et nowplaying l'attendent : aucun ne démarre, et l'antenne reste coupée. Pour tirer un secret :

```bash
openssl rand -hex 24
```

`RT_ADMIN_PASSWORD` est le mot de passe du compte admin `RT_ADMIN_USER`. `radiotomate-init` crée ce compte quand il manque : au premier démarrage, mais aussi après sa suppression ou un changement de son nom. Il n'a pas de longueur minimale. Une fois le compte créé, vider `RT_ADMIN_PASSWORD` : sinon, un compte admin supprimé revient au démarrage suivant, avec ce mot de passe. Vide, il n'est refusé qu'à la première installation, qui démarrerait sans compte admin. Le changer ne change pas un compte existant : un compte créé avec `change-me` garde ce mot de passe, à changer dans la console, Mon compte. D'ici là, `radiotomate-init` le rappelle dans son journal à chaque démarrage, sans bloquer.

Quand le contrôle refuse, le journal de `radiotomate-init` nomme chaque variable à changer, et la commande pour repartir : `docker compose logs radiotomate-init`. Il ne montre jamais la valeur d'un secret. Le contrôle passe à chaque `docker compose up`, pas au redémarrage de la machine. Un moteur déjà en marche continue donc de tourner, mais ne repart pas quand il est recréé, par une mise à jour par exemple.

Pour savoir avant une mise à jour si la station démarrera, lancer le contrôle seul, après `git pull` et avant `docker compose up`. Il n'écrit rien et n'arrête rien :

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

Une installation sur une machine exposée reste un essai tant que les fiches [P1](feuille-de-route/P1-mise-en-prod.md) ne sont pas faites, en particulier celles de sécurité : catalogue protégé, essais de connexion limités, identifiants d'encodeur, en-têtes. Sur une telle machine, fermer aussi les ports avec `BIND_ADDRESS=127.0.0.1`, derrière Caddy : voir [HTTPS](#https).

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

Avant, s'assurer que les secrets laisseront la station démarrer : voir [les secrets](#les-secrets).

```bash
docker compose pull
docker compose up -d
```

Sans `RT_TAG`, la station suit `main`. Pour geler une version, mettre un tag daté dans `.env` : `RT_TAG=AAAAMMJJ-sha7`. Les tags existants sont listés sur la page des packages GitHub.

`RT_TAG` ne gèle que le moteur et le playout. La console, Icecast, nowplaying, le catalogue et le partage suivent `main` tant que les versions publiées n'existent pas : voir MAJ-01 dans la [feuille de route](feuille-de-route/P1-mise-en-prod.md).

Ensuite, vérifier que l'antenne tourne, sans compte, depuis le dossier de la station :

```bash
scripts/smoke.sh http://127.0.0.1:30126 http://127.0.0.1:18000/button.mp3
```

Le contrôle prend l'adresse de la console, puis celle du flux public. Sur la machine, avec les ports par défaut, ce sont celles de l'exemple. Derrière un reverse proxy, donner plutôt leurs adresses publiques, en `https://`, pour le vérifier lui aussi : le contrôle ne suit pas les redirections. Il vérifie, dans l'ordre :

1. le playout, l'interface et le scheduler sont `healthy`, en attendant deux minutes au plus ;
2. la console répond et relaie le moteur : `/` et `/health/ready` répondent 200 ;
3. le scheduler est prêt : son `/health/ready`, lu dans son conteneur, répond 200 ;
4. sans cookie, la recherche de la médiathèque répond 401 ;
5. le flux envoie de l'audio, et `now.json`, lu dans le conteneur de nowplaying, répond.

Au premier point qui échoue, il s'arrête en erreur, nomme le point et ce qui ne va pas, et dit quel journal lire. Un service du moteur arrêté le fait échouer tout de suite, sans attendre. Le point 4 ne voit pas un catalogue arrêté : sans cookie, nginx répond 401 sans le joindre. Sur une machine lente, `SMOKE_WAIT=300 scripts/smoke.sh …` attend la santé du moteur cinq minutes. Le contrôle appelle `docker compose` sans option : une station lancée avec `-p <station>` ou `--env-file <fichier>` se contrôle avec `COMPOSE_PROJECT_NAME=<station>` ou `COMPOSE_ENV_FILES=<fichier>` devant la commande. Le contrôle ne change rien à la station : il sert aussi après une installation, ou à tout moment.

## Revenir en arrière

`radiotomate-init` applique les migrations à chaque démarrage. Si la version récente a migré le schéma, une image plus ancienne ne sait pas le défaire, et le playout ne démarre plus. Il faut donc redescendre le schéma **avec l'image récente**, puis épingler l'ancienne :

```bash
docker compose run --rm --no-deps --entrypoint radiotomate radiotomate-init \
  -c /data/radiotomate.yaml update --target-version <version de l'ancienne image>
# .env : RT_TAG=<tag daté de l'ancienne image>
docker compose up -d
```

Une migration défaite perd les données qu'elle avait ajoutées. Sauvegarder avant : voir [`exploitation/sauvegarde.md`](exploitation/sauvegarde.md).

## Exploiter

| Fiche | Pour |
|---|---|
| [`passer-en-direct.md`](exploitation/passer-en-direct.md) | brancher un encodeur, les créneaux des animateurs |
| [`deposer-un-programme.md`](exploitation/deposer-un-programme.md) | envoyer de la musique et des émissions |
| [`dossier-reseau.md`](exploitation/dossier-reseau.md) | ouvrir la médiathèque dans le Finder |
| [`decrochage.md`](exploitation/decrochage.md) | partager l'antenne avec une autre radio |
| [`le-flux-est-tombe.md`](exploitation/le-flux-est-tombe.md) | diagnostiquer une coupure |
| [`sauvegarde.md`](exploitation/sauvegarde.md) | sauvegarder et restaurer |

## Plusieurs stations

Chaque station a son propre dossier de données, sa propre base et son propre `.env`. Pour en faire tourner plusieurs sur une machine, donner à chacune un nom de projet Compose (`docker compose -p <station>`) et des ports distincts, `HARBOR_PORT` compris. Le profil `vps` ne sert qu'à l'une d'elles : les ports 80 et 443 ne se partagent pas.
