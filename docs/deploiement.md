# Déployer une station

Une station complète tient dans [`deploy/compose.yml`](../deploy/compose.yml) : moteur, console, Icecast, titre en cours, catalogue et envoi reprenable. Les images sont publiées par la CI sur `ghcr.io/lazbutton`.

## Prérequis

- Une machine Linux avec Docker et Compose v2.
- De la place pour la banque de sons.
- Pour un accès public, un reverse proxy HTTPS devant la console et le flux, par exemple Caddy.

## Installer

```bash
git clone https://github.com/lazbutton/button.git
cd button/deploy
cp .env.example .env
chmod 600 .env
```

Dans `.env`, remplacer chaque `change-me`, puis choisir les chemins des données (`RT_DATA`, `BUTTON_MEDIA`…). Ensuite :

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
- crée le compte admin `RT_ADMIN_USER` s'il n'existe pas.

| Service | Adresse par défaut |
|---|---|
| Console | `http://<machine>:30126` |
| Flux Icecast | `http://<machine>:18000/button.mp3` |
| Titre en cours | `http://<machine>:6820/now.json` |
| Catalogue | `http://<machine>:30127` |

Le harbor (l'entrée du direct, port 6800) n'est pas publié par défaut. Pour qu'un encodeur se branche sur cette machine, ajouter un `compose.override.yml` :

```yaml
services:
  radiotomate-playout:
    ports:
      - "6800:6800"
```

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
