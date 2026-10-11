# BUTTON

**Automate de diffusion pour radios associatives.** BUTTON tient l'antenne 24 h sur 24 : musique en rotation, habillage, émissions enregistrées, relais et directs. Une console web permet de la piloter sans connaître la mécanique.

[English version](README.en.md) · [Documentation](docs/README.md) · Licence [AGPL-3.0-or-later](LICENSE)

> **Projet jeune.** BUTTON fait tourner l'antenne de la radio BUTTON. L'API, le déploiement et la configuration peuvent encore changer entre deux versions.

## Ce que fait BUTTON

- **Une grille qui se tient seule.** Des horloges enchaînent musique, jingles, sons et pubs, avec des ancres dures ou molles à la minute. Une grille hebdomadaire choisit l'horloge de chaque créneau.
- **Un auto-DJ qui varie.** La musique sort d'une bibliothèque [Beets](https://beets.io/), avec des règles de séparation des artistes et des titres, et un volume égalisé (ReplayGain).
- **Des directs sans manipulation.** L'animateur branche son encodeur (BUTT, Mixxx…) et prend l'antenne. Un animateur nommé n'entre que sur son créneau, et la grille reprend seule à la fin.
- **Des relais et des décrochages** avec d'autres radios.
- **Une console web** pour l'antenne au quotidien (file, bibliothèque, idents, passage en direct), le conducteur, la programmation, les sons et les comptes. Elle tient sur téléphone et suit le thème clair ou sombre.
- **Le dépôt de musique par le navigateur**, avec un envoi reprenable, ou par simple dossier partagé.
- **Une antenne surveillée** : alertes en cas de silence, de playout injoignable ou de direct manquant, métriques et sauvegardes.

## Comment c'est fait

Le moteur est un fork de [Radiotomate](https://radiotomate.org/), de Martin Kirchgessner : Python (Quart, SQLAlchemy, Beets) pour la programmation, [Liquidsoap](https://www.liquidsoap.info/) pour le son. La console est une application React. Autour, de petits services : le catalogue de la banque de sons (Meilisearch), le titre en cours, Icecast. Le tout se déploie avec Docker Compose.

Le détail est dans [docs/architecture.md](docs/architecture.md).

## Démarrer

**Installer une station** :

```bash
git clone https://github.com/lazbutton/button.git
cd button/deploy
cp .env.example .env      # puis remplacer chaque « change-me »
docker compose up -d
```

La suite est dans [docs/deploiement.md](docs/deploiement.md).

**Développer** : le banc local lance le moteur en mode démo et la console. Voir [docs/developpement.md](docs/developpement.md).

```bash
./scripts/dev.sh          # moteur sur :6811, console sur :5175
```

## Le dépôt

| Dossier | Contenu |
|---|---|
| [`engine/`](engine/) | Le moteur, fork de Radiotomate, et son script Liquidsoap |
| [`console/`](console/) | La console web (React) |
| [`services/`](services/) | Catalogue, titre en cours, Icecast |
| [`deploy/`](deploy/) | Compose de la station, scripts d'initialisation, banc audio local |
| [`docs/`](docs/) | Documentation (en français) |
| [`scripts/`](scripts/) | Outils de développement |

## Contribuer

Les contributions sont bienvenues : signalements, corrections, traductions, documentation. Lire [CONTRIBUTING.md](CONTRIBUTING.md) avant de proposer un changement, et [SECURITY.md](SECURITY.md) pour signaler une faille. Le projet suit un [code de conduite](CODE_OF_CONDUCT.md).

## Licence et crédits

BUTTON est distribué sous licence [GNU Affero General Public License v3.0 ou ultérieure](LICENSE). Si vous faites tourner une version modifiée pour d'autres personnes, par exemple en hébergeant une station, vous devez leur donner accès à son code source.

Le moteur dérive de [Radiotomate](https://git.sr.ht/~martink/radiotomate), écrit par Martin Kirchgessner. Auteurs et ressources incluses : [AUTHORS.md](AUTHORS.md).
