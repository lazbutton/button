# Déployer une station

Une station complète tient dans [`deploy/compose.yml`](../deploy/compose.yml) : moteur, console, Icecast, titre en cours, catalogue et envoi reprenable. Les images sont publiées par la CI sur `ghcr.io/lazbutton`.

## Prérequis

- Une machine Linux x86-64 avec Docker et Compose v2. Les images ne sont construites que pour `linux/amd64`.
- De la place pour la banque de sons.
- Pour un accès public, un reverse proxy HTTPS devant la console et le flux, par exemple Caddy.

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

**Docker contourne le pare-feu.** Par défaut, ces ports sont publiés sur toutes les interfaces, en IPv4 et en IPv6, et un port publié par Docker reste joignable même si ufw le ferme. Sur un réseau privé, où l'on ouvre la console par l'adresse de la machine, c'est ce qu'il faut. Sur un VPS exposé à Internet, derrière un reverse proxy HTTPS installé sur la machine, les lier à `127.0.0.1` dans `.env` :

```bash
BIND_ADDRESS=127.0.0.1
```

Puis `docker compose up -d`. Sur une station en service, il recrée la console, Icecast, nowplaying et le catalogue : les auditeurs d'Icecast sont déconnectés. Ces quatre ports ne répondent plus qu'à la machine elle-même. Le reverse proxy les joint par `127.0.0.1`, par exemple `127.0.0.1:30126` pour la console, et non par `localhost`, qui peut viser d'abord `::1`, où rien n'écoute alors. La console, le flux et `now.json` ne s'ouvrent plus que par lui. Vérifier ensuite depuis une autre machine, par exemple avec `nc -zv <machine> 30126`, et non avec `ufw status`.

`BIND_ADDRESS` vide garde l'écoute sur toutes les interfaces. `0.0.0.0` n'est pas pareil : il n'écoute qu'en IPv4. Une station qui suit l'ancienne consigne, une adresse dans chaque port (`CONSOLE_PORT=127.0.0.1:30126`), marche encore. Pour passer à `BIND_ADDRESS`, retirer ces adresses des quatre ports : avec les deux, `docker compose` refuse de démarrer, sur « invalid IP address ».

Le harbor (l'entrée du direct, port 6800) n'est pas publié par défaut. Pour qu'un encodeur se branche sur cette machine, ajouter un `compose.override.yml` :

```yaml
services:
  radiotomate-playout:
    ports:
      - "6800:6800"
```

Le harbor accepte aujourd'hui l'identifiant et le mot de passe du compte de l'animateur. Avant de l'ouvrir à Internet, lire la fiche SEC-04 de la [feuille de route](feuille-de-route/P1-mise-en-prod.md).

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

Une installation sur une machine exposée reste un essai tant que les fiches [P1](feuille-de-route/P1-mise-en-prod.md) ne sont pas faites, en particulier celles de sécurité : catalogue protégé, essais de connexion limités, identifiants d'encodeur, en-têtes. Sur une telle machine, fermer aussi les ports avec `BIND_ADDRESS=127.0.0.1`, derrière un reverse proxy : voir [Installer](#installer).

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

`Strict-Transport-Security` vient du reverse proxy HTTPS, pas de la console.

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

Chaque station a son propre dossier de données, sa propre base et son propre `.env`. Pour en faire tourner plusieurs sur une machine, donner à chacune un nom de projet Compose (`docker compose -p <station>`) et des ports distincts.
