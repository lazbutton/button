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
        └── share (Samba, profil « share ») : la banque dans le Finder

   nowplaying ◄── métadonnées du moteur ──► now.json, pour les sites et players
```

## Les composants

| Composant | Code | Image | Port |
|---|---|---|---|
| playout | `engine/playout/` | `button-playout` | 6833 interne, 6800 harbor |
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

L'interface et le scheduler partagent le réseau du playout (`network_mode: service:radiotomate-playout`). Redémarrer le playout seul les rend injoignables : on recrée toujours les trois ensemble.

## Comment l'antenne est tenue

1. **Liquidsoap publie son état** chaque seconde au scheduler : source à l'antenne, titre, temps restant, contenu des files.
2. **Le scheduler ne réfléchit que si c'est utile** : quand l'état change, au changement de minute, ou dans les dix dernières secondes d'un titre.
3. **L'horloge décide.** Le créneau en cours (`AutoDJSlot`) porte une horloge (`Clock`) : un motif de positions (musique, jingle, son, pub), enchaînées ou calées sur une minute, avec des ancres dures ou molles.
4. **La décision devient une ligne de conducteur** (`RundownItem`) et une commande (`PlayoutCommand`), envoyée à Liquidsoap par une *outbox* qui sait réessayer.
5. **Ce qui passe vraiment remonte** dans `metadata_log`, et le conducteur est réconcilié avec ce journal d'antenne.

Liquidsoap choisit la source dans cet ordre : **direct (harbor) > relais > carts > jingles > auto-DJ**. Les titres de l'auto-DJ s'enchaînent avec un fondu de 3 s. Les autres transitions se font en coupe franche ([savonet/liquidsoap#4179](https://github.com/savonet/liquidsoap/issues/4179)).

L'**Agenda** ajoute des diffusions à une date précise : un set déposé passe à son heure (`scheduler/agenda.py`), et un direct daté ouvre le harbor au compte prévu. Un invité dépose son set par un lien privé, sans compte : le fichier passe par tusd, puis le catalogue le range dans `40-emissions` et le déclare au moteur. L'interrupteur `agenda_enabled` coupe tout l'Agenda.

Pendant un direct, l'horloge se met en pause et laisse tomber les ancres dues. À la fin, les files jingles et auto-DJ sont vidées et le titre auto-DJ entamé est sauté : la grille reprend sur un morceau entier.

## Les données

| Quoi | Où | Notes |
|---|---|---|
| Base de la station | `RT_DATA/radiotomate.db` (SQLite) | une par station ; schéma migré par `radiotomate update` au démarrage |
| Configuration du moteur | `RT_DATA/radiotomate.yaml` | sorties, alertes, rétention, métriques ; écrite par `radiotomate-init` |
| Banque de sons | `BUTTON_MEDIA` | `00-inbox`, `10-rotation`, `20-archives`, `30-habillage`, `40-emissions`, `50-carts`… |
| Bibliothèque Beets | `RT_DATA/Beets` | index de la banque, ReplayGain |
| Index de recherche | `MEILI_DATA` | reconstruit par le catalogue |
| Envois en cours | volume `tusd-data` | les morceaux d'un envoi reprenable |
| Mots de passe du dossier partagé | volume `share-private` | écrits par le catalogue, lus par `share` ; jamais dans la banque |

Les heures ne sont pas stockées de la même façon partout : heure locale dans les tables historiques, UTC dans l'Agenda. Voir l'[ADR 0008](decisions/0008-deux-conventions-d-heure.md).

## Ce que le moteur surveille

- **Alertes** : silence, playout injoignable, battement perdu, sortie Icecast coupée, créneau de direct sans encodeur. Elles partent dans le journal, vers un webhook JSON, ou en tâche Vikunja (bloc `alerts:` du YAML).
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
