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

Dans `.env`, remplacer chaque `change-me`, puis choisir les chemins des données (`RT_DATA`, `BUTTON_MEDIA`…). Sans HTTPS devant la console, poser aussi `RT_COOKIE_SECURE=false` : voir [le cookie de session](#le-cookie-de-session). Ensuite :

```bash
docker compose pull
docker compose up -d
docker compose ps        # attendre radiotomate-scheduler « healthy »
```

Au premier démarrage, `radiotomate-init` prépare tout, et peut être relancé sans danger :

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

**Docker contourne le pare-feu.** Ces ports sont publiés sur toutes les interfaces, et un port publié par Docker reste joignable même si ufw le ferme. Sur une machine exposée à Internet, les lier à `127.0.0.1` dans `.env`, puis placer un reverse proxy HTTPS devant :

```bash
CONSOLE_PORT=127.0.0.1:30126
ICECAST_PORT=127.0.0.1:18000
NOWPLAYING_PORT=127.0.0.1:6820
CATALOG_PORT=127.0.0.1:30127
```

Vérifier ensuite depuis une autre machine, par exemple avec `nc -zv <machine> 30126`, et non avec `ufw status`.

Le harbor (l'entrée du direct, port 6800) n'est pas publié par défaut. Pour qu'un encodeur se branche sur cette machine, ajouter un `compose.override.yml` :

```yaml
services:
  radiotomate-playout:
    ports:
      - "6800:6800"
```

Le harbor accepte aujourd'hui l'identifiant et le mot de passe du compte de l'animateur. Avant de l'ouvrir à Internet, lire la fiche SEC-04 de la [feuille de route](feuille-de-route/P1-mise-en-prod.md).

## Le cookie de session

Par défaut, le cookie de session porte l'attribut `Secure` : le navigateur ne l'accepte et ne le renvoie qu'en `https://`. Seule exception, Chrome et Firefox l'acceptent aussi sur `http://localhost`. Une fois connecté en HTTPS, ouvrir par erreur une adresse en `http://` n'envoie donc pas la session en clair.

Pour un accès en HTTP seul, sur un banc local ou un réseau privé, poser `RT_COOKIE_SECURE=false` dans `.env`. Sinon, personne ne peut se connecter : la console accepte le mot de passe, puis dit que le navigateur a refusé le cookie de session. En HTTP, le mot de passe et le cookie passent en clair : à réserver à un réseau de confiance. Avec `false`, `radiotomate-init` le rappelle dans son journal à chaque démarrage (`docker compose logs radiotomate-init`).

Pour changer `RT_COOKIE_SECURE` sur une station en service, modifier `.env`, puis recréer les trois services du moteur ensemble, comme pour [un réglage du moteur](#régler-le-moteur) : `radiotomate-init` repasse d'abord et réécrit `radiotomate.yaml`.

Derrière un reverse proxy, le journal de `radiotomate-interface` peut afficher « Secure cookies will be ignored on insecure requests » : le moteur ne voit que le HTTP de nginx. Quand le navigateur est en `https://`, ce message est sans conséquence.

## Avant d'exposer une station à Internet

Une installation sur une machine exposée reste un essai tant que les fiches [P1](feuille-de-route/P1-mise-en-prod.md) ne sont pas faites, en particulier celles de sécurité : catalogue protégé, essais de connexion limités, identifiants d'encodeur, en-têtes, secrets d'exemple refusés, ports fermés.

## Régler le moteur

`RT_DATA/radiotomate.yaml` porte les réglages fins : sorties audio, alertes (`alerts:`, webhook ou Vikunja), rétention (`retention:`), métriques (`metrics:`), relais des métadonnées (`metadata_log:`). Après un changement, recréer les trois services du moteur ensemble :

```bash
docker compose up -d --force-recreate radiotomate-playout radiotomate-interface radiotomate-scheduler
```

**Ne jamais redémarrer `radiotomate-playout` seul** : l'interface et le scheduler partagent son réseau, et deviendraient injoignables.

## Mettre à jour

```bash
docker compose pull
docker compose up -d
```

Sans `RT_TAG`, la station suit `main`. Pour geler une version, mettre un tag daté dans `.env` : `RT_TAG=AAAAMMJJ-sha7`. Les tags existants sont listés sur la page des packages GitHub.

`RT_TAG` ne gèle que le moteur et le playout. La console, Icecast, nowplaying, le catalogue et le partage suivent `main` tant que les versions publiées n'existent pas : voir MAJ-01 dans la [feuille de route](feuille-de-route/P1-mise-en-prod.md).

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
