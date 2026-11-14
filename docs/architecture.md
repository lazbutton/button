# Architecture

BUTTON tient l'antenne d'une radio 24 h sur 24 : musique en rotation, habillage, émissions enregistrées, relais et directs. Une console web permet de la piloter sans connaître la mécanique.

## Vue d'ensemble

```
      encodeur du direct (BUTT, Mixxx)
                 │ source Icecast, port 6800
                 ▼
 ┌──────────────────────── moteur (engine/) ────────────────────────┐
 │  playout : Liquidsoap 2.4.5 ─ harbor :6800, API interne :6833     │
 │     │ état chaque seconde (POST /live)   ▲ files, saut, relais    │
 │     ▼                                    │                        │
 │  scheduler (:6822) ─ horloge, conducteur, alertes, métriques       │
 │     │ état d'antenne (flux SSE)                                    │
 │     ▼                                                              │
 │  interface (:6811) ─ pages HTMX + API JSON                         │
 └────────────────────────────────────────────────────────────────────┘
        ▲ /api                                │ flux MP3
        │                                     ▼
   console (React, nginx)                  Icecast ──► auditeurs
        │ /library, /tus/
        ▼
   catalogue (+ Meilisearch) ◄── tusd (envoi reprenable)
        │
   banque de sons ◄── dropbox (Beets, promotion de l'inbox)
        ▲
        ├── share (Samba, profil « share ») : la banque dans le Finder
        └── cloud-sync (rclone, profil « cloud ») : les bacs ouverts dans Dropbox

   nowplaying ◄── métadonnées du moteur ──► now.json, pour les sites et players
```

## Les composants

| Composant | Code | Image | Port |
|---|---|---|---|
| playout | `engine/playout/` | `button-playout` | 6833 interne, 6800 harbor, publié pour l'encodeur |
| interface | `engine/` | `button-radiotomate` | 6811 |
| scheduler | `engine/` | `button-radiotomate` | 6822 interne |
| dropbox | `engine/`, `deploy/scripts/` | `button-radiotomate` | — |
| console | `console/` | `button-console` | 80, publié en 30126 |
| catalogue | `services/catalog/` | `button-catalog` | 30127 |
| nowplaying | `services/nowplaying/` | `button-nowplaying` | 6820 |
| Icecast | `services/icecast/` | `button-icecast` | 8000, publié en 18000 |
| Meilisearch | — | `getmeili/meilisearch` | interne |
| tusd | — | `tusproject/tusd` | 8080 interne |
| radiotomate-init | `engine/`, `deploy/scripts/` | `button-radiotomate` | — : prépare la station à chaque démarrage, puis s'arrête |
| share | `deploy/share/` | `button-share` | 445, sur `127.0.0.1` par défaut, seulement avec `--profile share` |
| caddy | `deploy/Caddyfile` | `caddy` | 80 et 443, seulement avec `--profile vps` : le HTTPS devant la console, le flux et `now.json` |
| cloud-sync | `deploy/scripts/cloud-sync.sh` | `rclone/rclone` | — : seulement avec `--profile cloud`, copie dans son bac un son déposé dans Dropbox |

Malgré son nom, le service `radiotomate-dropbox` ne parle pas à Dropbox : il range l'inbox et tient Beets à jour. Le pont vers Dropbox est `cloud-sync` : [exploitation/bacs-dropbox.md](exploitation/bacs-dropbox.md).

L'interface et le scheduler partagent le réseau du playout (`network_mode: service:radiotomate-playout`). Redémarrer le playout seul les rend injoignables : on recrée toujours les trois ensemble.

## Comment l'antenne est tenue

1. **Liquidsoap publie son état** chaque seconde au scheduler : source à l'antenne, titre, temps restant, contenu des files.
2. **Le scheduler ne réfléchit que si c'est utile** : quand l'état change, au changement de minute, ou dans les dix dernières secondes d'un titre.
3. **L'horloge décide.** Le créneau en cours (`AutoDJSlot`) porte une horloge (`Clock`) : un motif de positions (musique, jingle, son, pub), enchaînées ou calées sur une minute, avec des ancres dures ou molles.
4. **La décision devient une ligne de conducteur** (`RundownItem`) et une commande (`PlayoutCommand`), envoyée à Liquidsoap par une *outbox* qui sait réessayer.
5. **Ce qui passe vraiment remonte** dans `metadata_log`, et le conducteur est réconcilié avec ce journal d'antenne.

Liquidsoap choisit la source dans cet ordre : **direct (harbor) > relais > carts > jingles > auto-DJ**. Toutes les transitions se font en coupe franche, d'une source à l'autre comme entre deux titres de l'auto-DJ. Les transitions de `fallback` sont cassées dans Liquidsoap 2.4 ([savonet/liquidsoap#4179](https://github.com/savonet/liquidsoap/issues/4179)), et son fondu enchaîné, `crossfade`, fige la file de l'auto-DJ : voir [les changements du moteur](moteur/changements-radiotomate.md#conducteur-et-vérité-dantenne).

L'**Agenda** ajoute des diffusions à une date précise : un set déposé passe à son heure (`scheduler/agenda.py`), et un direct daté ouvre le harbor au compte prévu. Un invité dépose son set par un lien privé, sans compte : le fichier passe par tusd, puis le catalogue le range dans `40-emissions` et le déclare au moteur. L'interrupteur `agenda_enabled` coupe tout l'Agenda.

## La recherche des fiches

Les fiches d'un titre sont ce que la bibliothèque sait de lui, corrigé et complété d'après des sources en ligne, par des propositions que l'équipe relit : rien ne s'écrit d'office ([ADR 0017](decisions/0017-une-fiche-ne-s-ecrit-qu-acceptee.md)). La recherche est une tâche de fond du scheduler (`engine/radiotomate/scheduler/fiches.py`), comme l'analyse ReplayGain : un titre à la fois, dans un fil à part, sans faire attendre l'antenne. Elle relit ses interrupteurs entre deux titres : `features.fiches`, éteint par défaut, la coupe toute.

- **Ce qu'elle joint** : AcoustID, avec l'empreinte que `fpcalc` prend des deux premières minutes du fichier ; Deezer, MusicBrainz et Wikidata ; Tidal, Apple Music et Bandcamp, chacun derrière son réglage. Chaque service a son seau et son disjoncteur (`engine/radiotomate/fiches/http.py`). Ce qui part de la station : l'artiste, le titre, l'album et l'empreinte de ses fichiers, rien de l'équipe ni des auditeurs.
- **L'ordre** : les titres arrivés depuis qu'elle est allumée, puis ceux dont la clé a changé, puis le reste du catalogue, puis ceux à reprendre : un introuvable après 90 jours, une erreur après une attente qui double.
- **Ce qu'elle garde**, dans la base du moteur : `fiches`, un titre cherché, par son identifiant de Beets, avec sa clé, son niveau, sa source et ses preuves ; `fiche_propositions`, un champ proposé et son état ; `fiche_decisions`, chaque acceptation et chaque refus, par la clé du titre, qui survit au titre. La clé : l'empreinte, sinon l'artiste, le titre et la durée, normalisés. Un fichier déplacé revient avec la même clé : ses preuves refont ses propositions sans réseau, et une valeur refusée ne se propose plus.
- **Ce qu'elle montre** : la vue « À relire » de Sons → Banque lit les fiches par `GET /fiches.json` et `GET /fiches/{id}.json` (`engine/radiotomate/services/fiches_review.py`), en lecture ; Réglages → Fiches règle la recherche et ses sources par `/fiches/reglages.json`, qui dit si une clé est posée, jamais sa valeur ([docs/exploitation/fiches.md](exploitation/fiches.md)).
- **Dans Beets**, le plugin `engine/beetsplug/fiches.py` déclare les champs flexibles que les fiches écriront une fois acceptées, `famille`, `fmg` et `fmg_source`, et `beet fiches`, qui dit où en est la recherche, comme `radiotomate maintenance fiches`.

Pendant un direct, l'horloge se met en pause et laisse tomber les ancres dues : leurs lignes passent « sauté » au conducteur. Un relais en cours s'arrête quand le direct prend l'antenne. À la fin, les files jingles et auto-DJ sont vidées et le titre auto-DJ entamé est sauté : la grille reprend sur un morceau entier.

## Les données

| Quoi | Où | Notes |
|---|---|---|
| Base de la station | `RT_DATA/radiotomate.db` (SQLite) | une par station ; schéma migré par `radiotomate update` au démarrage |
| Configuration du moteur | `RT_DATA/radiotomate.yaml` | sorties, alertes, rétention, métriques ; écrite par `radiotomate-init` |
| Banque de sons | `BUTTON_MEDIA` | `00-inbox`, `10-rotation`, `20-archives`, `30-habillage`, `40-emissions`, `50-carts`… Chaque composant nomme ces dossiers à un seul endroit : `media_bank.py` pour le moteur, `layout.py` pour le catalogue, la tête de chaque script pour la station ; la console n'en nomme aucun ([décision 0019](decisions/0019-le-rangement-de-la-banque.md)) |
| Bibliothèque Beets | `RT_DATA/Beets` | index de la banque, ReplayGain, et les champs flexibles des fiches acceptées |
| Fiches de la bibliothèque | `RT_DATA/radiotomate.db` | tables `fiches`, `fiche_propositions` et `fiche_decisions` : ce que la recherche a trouvé, ce qu'elle propose, et ce que l'équipe en a décidé |
| Index de recherche | `MEILI_DATA` | reconstruit par le catalogue |
| Envois en cours | volume `tusd-data` | les morceaux d'un envoi reprenable |
| Comptes du dossier partagé | volume `share-private` | les mots de passe, écrits par le catalogue, et les rôles, par la boucle Beets ; lus par `share`, jamais dans la banque |
| Certificats HTTPS | `CADDY_DATA` | les certificats et le compte Let's Encrypt de Caddy, avec le profil `vps` |
| Jeton Dropbox | `CLOUD_SYNC_CONFIG/rclone.conf` | la configuration de rclone, avec le profil `cloud` ; rclone y renouvelle le jeton. Jamais dans `.env` ni dans le dépôt |
| Copies depuis Dropbox | volume `cloud-sync-state` | ce que `cloud-sync` a copié, et le dernier compte rendu de chaque dossier : un son retiré dans la console ne revient pas |

Les heures ne sont pas stockées de la même façon partout : heure locale dans les tables historiques, UTC dans l'Agenda. Voir l'[ADR 0008](decisions/0008-deux-conventions-d-heure.md).

## Ce que le moteur surveille

- **Alertes** : silence, playout injoignable, battement perdu, antenne figée sur le même son, sortie Icecast coupée, créneau de direct sans encodeur, diffusion de l'Agenda qui ne peut pas passer, disque presque plein. La console les montre même sans cible ; `enabled: false` les coupe. Elles partent dans le journal, vers un webhook JSON, en tâche Vikunja, sur un téléphone par ntfy, ou par e-mail (bloc `alerts:` du YAML, que le scheduler relit seul). ntfy et l'e-mail se règlent par `station config`. La commande `station` donne aussi ses propres alertes par eux : mise à jour annulée, sauvegarde ratée. Voir [exploitation/alertes.md](exploitation/alertes.md).
- **Métriques** : `/metrics.json` sur le scheduler, et un export JSONL par heure.
- **Rétention** : le conducteur joué, les commandes acquittées et le vieux journal d'antenne sont purgés, et le journal est exporté avant suppression.
- **Sondes** : `/health/live` et `/health/ready` sur l'interface et le scheduler, et `/health` sur le playout.

## Le dépôt

| Dossier | Contenu |
|---|---|
| [`engine/`](../engine/) | Le moteur, fork de Radiotomate : Python (Quart, SQLAlchemy, Beets) et Liquidsoap |
| [`console/`](../console/) | La console web |
| [`services/`](../services/) | Catalogue, nowplaying, Icecast |
| [`deploy/`](../deploy/) | Compose de la station, scripts d'initialisation, banc audio local |
| [`docs/`](./) | Cette documentation |
| [`scripts/`](../scripts/) | Le banc local (`dev.sh`) et les vérifications de la CI (`verifier.sh`) |

Chaque dossier principal a son `AGENTS.md` : les règles et les pièges pour y travailler. Les choix qui structurent le tout sont dans [decisions/](decisions/README.md).
