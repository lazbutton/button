# Glossaire

Les mots de la radio et ceux du code. Quand la console et le code n'emploient pas le même mot, les deux sont donnés.

| Mot | Sens | Dans le code |
|---|---|---|
| Admin | Le rôle qui gère les comptes et les réglages | droit `admin` |
| Agenda | Les émissions à une date précise : un set enregistré ou un direct | `agenda_diffusions`, `domain/agenda.py` |
| Ancre | Une position d'horloge calée sur une minute. Dure : elle coupe le titre en cours. Molle : elle attend sa fin | `Clock`, positions ancrées |
| Animateur | Le rôle qui tient l'antenne depuis le pupitre. L'interrupteur « Peut passer en direct » lui permet aussi de brancher un encodeur | droits `live`, puis `stream` |
| Antenne | Ce qui part vers les auditeurs. Aussi la page principale de la console | `AntennePage.tsx`, `/antenne/state.json` |
| Auto-DJ | La musique que le moteur choisit seul dans la banque, selon les catégories | file Liquidsoap `autodj` |
| Bac | Le mot de la console pour un cart : des sons joués selon un mode, en liste, en boucle, au hasard, ou un relais | `Cart` |
| Banque | Les dossiers de fichiers audio de la station : `00-inbox`, `10-rotation`, `20-archives`, `30-habillage`, `40-emissions`, `50-carts`… Une banque d'archives est un dossier de `20-archives` | `BUTTON_MEDIA`, `MEDIA_ROOT` |
| Catalogue | Le service qui indexe la banque, répond aux recherches et range les envois | `services/catalog/` |
| Catégorie | Une requête Beets qui choisit des titres, comme `genre:Jazz` | `MusicCategory` |
| Conducteur | Ce qui va passer, puis ce qui est passé, calculé par le scheduler | `rundown_items`, `scheduler/rundown.py` |
| Console | L'application web de l'équipe | `console/` |
| Créneau | Une plage de la grille hebdomadaire, qui porte une horloge | `AutoDJSlot` |
| Décrochage | Partager l'antenne avec une autre radio pendant une plage | voir `docs/exploitation/decrochage.md` |
| Diffusion | Une entrée de l'Agenda : un set ou un direct | `kind` vaut `set` ou `live` |
| Direct | Une prise d'antenne par un encodeur branché sur le harbor | source `stream` |
| Dropbox | Le conteneur qui surveille l'inbox, range les fichiers et met à jour Beets | `radiotomate-dropbox` |
| Émission | Un programme nommé : hebdomadaire, avec un jour, des heures et parfois un animateur ; ou de session, le direct en cours | `emissions` |
| Encodeur | Le logiciel qui envoie le son du direct : BUTT, Mixxx… | — |
| Habillage | Les jingles, virgules et idents qui ponctuent l'antenne | `30-habillage` |
| Harbor | L'entrée du direct dans Liquidsoap, port 6800 | `scheduler/harbor.py` |
| Horloge | Un motif de positions qui se répète, avec ses ancres | `Clock`, `scheduler/clock.py` |
| Inbox | Le dossier où arrivent les fichiers envoyés, avant d'être rangés | `00-inbox` |
| Interface | Le processus web du moteur, port 6811 : pages HTMX de l'amont et API JSON de la console | `interface_app.py` |
| Invité | Une personne sans compte, qui dépose son set par un lien privé | `agenda_guests`, page `/invitation` |
| Jeton d'encodeur | Le mot de passe que l'encodeur envoie au harbor, à la place de celui du compte. Un par compte, montré une seule fois | `users.stream_token_hash`, `services/stream_token.py` |
| Journal d'antenne | Ce qui est vraiment passé, remonté par Liquidsoap, auquel le conducteur se réconcilie | `metadata_log` |
| Migration | Une évolution du schéma de la base | `commands/update/vNN.py` |
| Moteur | Le fork de Radiotomate : playout, scheduler et interface | `engine/` |
| Mount | Un point de diffusion d'Icecast, comme `/radio.mp3` | — |
| nowplaying | Le service qui publie le titre en cours | `services/nowplaying/`, `now.json` |
| Outbox | La file des commandes vers le playout, qui sait réessayer | `playout_commands`, `scheduler/outbox.py` |
| Pad d'ident | Un son d'un bac marqué pour annoncer la station | `ident_pads` |
| Playout | Le processus Liquidsoap qui produit le son | `engine/playout/radiotomate.liq` |
| Position | Un élément d'une horloge : musique, jingle, son ou pub | `musique`, `jingle`, `son`, `pub` |
| Programmateur | Le rôle qui règle la grille, les horloges et les bacs | droits `carts` et `autodj` |
| Pupitre | La partie de la page Antenne où l'animateur prépare et lance ce qui passe | `scheduler/desk.py`, `AntenneDesk` |
| Relais | Le flux d'une autre radio, repris à l'antenne | cart en mode `relay` |
| Rotation | La musique de tous les jours | `10-rotation` |
| Scheduler | Le processus du moteur qui décide quoi jouer, port 6822 | `scheduler_app.py`, `scheduler/` |
| Set | Une émission enregistrée de l'Agenda, souvent déposée par un invité | `kind:"set"` |
| Station | Une radio installée : sa machine, ses données, sa marque | — |
| tus, tusd | Le protocole et le serveur d'envoi reprenable des fichiers | service `tusd` |
| Volume Finder | Le dossier partagé de la banque, ouvert depuis le Finder ou l'Explorateur | service `share` |
