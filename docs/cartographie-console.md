# Cartographie — console BUTTON

27 septembre 2026. État actuel, pas une proposition. Document pour refondre l’app. Le code de l’interface est `ntr-console`. Le moteur est Radiotomate (`radiotomate/`). L’exploitation est `ntr-ops`.

## Trois surfaces

| Surface | Adresse | Compte | Ce que c’est |
| --- | --- | --- | --- |
| Console | `https://gabbler.band`, banc `http://127.0.0.1:5175` | Oui | L’app de ce document |
| Interface HTML Radiotomate | port 6811 : `/live`, `/carts`, `/autodj`, `/account` | Les mêmes | Ancienne admin. La console lui parle en JSON. Elle reste joignable. Ce n’est pas l’app à refondre |
| Écoute | `https://radio.lazbutton.xyz/` et `https://flux.gabbler.band/ntf/` | Non | Bouton lecture. Titre lu dans `now.json` |

La console ne produit pas le son. Elle envoie des ordres à Radiotomate. Le flux public sort d’Icecast sur le VPS. Un direct se branche en dehors de la console : encodeur Icecast vers le harbor de Nasgul, port 6800, mount `/stream`, identifiant d’un compte qui a le droit `stream`.

## Deux personnes dans l’écran, six droits dans le moteur

L’écran ne distingue que `permissions.admin === true`.

**Admin.** Menu Antenne, Conducteur, Carts, Auto-DJ. Engrenage. Six pastilles. Choix du casque. Dépannage. Relancer et réinitialiser le conducteur. Réparer une ligne.

**Animateur.** Tout compte connecté sans `admin`. Menu Antenne et Conducteur. Casque forcé sur l’antenne publique. Une URL `/carts`, `/autodj`, `/parametres`, `/comptes`, `/horloges`, `/categories`, `/semaine` ou `/habillage` le renvoie à `/antenne`, une fois le compte chargé.

Le moteur stocke `admin`, `stream`, `live`, `carts`, `not_audio`, `autodj`. La console ne s’en sert pas pour ouvrir ou fermer une page. Un compte qui a `carts` et `autodj` sans `admin` voit le menu de l’animateur. Le droit `stream` ouvre le harbor, pas un écran. Le droit `live` est exigé par certaines actions du pupitre (« Pas le droit antenne ») même si le menu, lui, ne le vérifie pas. `not_audio` n’apparaît nulle part dans la console.

Il n’y a pas de rôle auditeur. Il n’y a pas de bouton pour se déconnecter. Il n’y a pas, dans l’écran Comptes, de moyen de changer un mot de passe déjà créé.

## Entrée

Chaque URL passe par une sonde de session, puis par `/account.json`.

1. Pas de cookie : **Connexion à Radiotomate**. Identifiant prérempli `lazbutton`. Mot de passe vide. Bouton « Se connecter ». Interrupteur de thème dans le coin. Le texte dit d’utiliser le compte de la marque pour l’administration de l’automate, même si la personne n’est pas admin.
2. Mauvais mot de passe : « Identifiant ou mot de passe incorrect. »
3. Port 6811 fermé : « Interface :6811 injoignable. » ou, si la sonde échoue avant le formulaire, « Radiotomate est indisponible » avec un bouton pour réessayer.
4. Session bonne : chargement, puis la coque. `/` devient `/antenne`.

Pendant le chargement du compte, le menu admin est caché. Un admin qui recharge `/carts` voit « Chargement… » et n’est pas renvoyé vers l’antenne.

## Coque

Présente sur toutes les pages une fois connecté.

**Colonne.** Logo et nom, lien vers `/antenne`. Quatre liens, ou deux. Bouton replier / déplier, mémorisé (`app-nav-collapsed`). Replié, les liens ne montrent que l’icône et une infobulle.

**Barre.**

- Pastille, rafraîchie toutes les 2 s depuis `/live.json` : Arrêt (gris), Direct (rouge), Jingles, Carts, Relais ou Auto-DJ (vert).
- Forme d’onde du casque. Bouton « Activer le son » tant que le navigateur n’a pas eu de geste.
- Source d’écoute, admin seulement. Dialogue **Source d’écoute**. Le texte dit que le casque change, pas l’antenne des auditeurs. Quatre cartes :
  - Nasgul · Tailscale — « Régie via Tailscale. Casque WAV Icecast, live edge. »
  - Nasgul · LAN — « Chez toi, 192.168.1.100 — casque WAV, le plus proche du zéro. »
  - Antenne publique — « Ce que l’auditeur entend (VPS). »
  - Conducteur (fichiers) — « MP3 du conducteur, collés à l’horloge. Ancre dure = coupe. Live plateau → Icecast. » Ce mode ne lit pas le burst Icecast : il joue les fichiers du conducteur.
- Thème clair ou sombre.
- Engrenage vers `/parametres`, admin seulement.

Le choix de source admin est mémorisé. Il revient si on repasse admin. L’animateur n’a pas le bouton. Sa source est `public`.

**Mobile.** Le menu est un panneau. Thème et, pour l’admin, un lien Paramètres en bas du panneau.

## Chemins

| Chemin | Ce qui s’ouvre | Qui |
| --- | --- | --- |
| `/` | `/antenne` | tout le monde |
| `/antenne` | Pupitre | tout le monde |
| `/conducteur` | Prévision | tout le monde |
| `/carts`, `/carts?id=12` | Carts, cart 12 sélectionné | admin |
| `/autodj` | Rotation, pubs, semaine repliée | admin |
| `/parametres` | Comptes | admin |
| `/comptes` | `/parametres` | admin |
| `/horloges` | `/autodj` | admin |
| `/categories` | `/autodj` | admin |
| `/semaine` | `/autodj` | admin |
| `/habillage` | `/carts` | admin |

Aucune autre route. Un non-admin sur une route admin arrive sur `/antenne`.

`HorlogesPage` (« Atelier Horloges ») et `CategoriesPage` sont dans le code et ne sont branchées à aucune route. Leurs anciennes adresses tombent sur Auto-DJ. Leur contenu est décrit plus bas, parce qu’il a existé comme écrans.

## Rythme

| Donnée | Où | Période |
| --- | --- | --- |
| `/live.json` | pastille, pupitre, conducteur | 2 s |
| `/antenne/state.json` | pastilles, bandeau, journal passé | 3 s sur le pupitre |
| `/antenne/emissions.json` | puce émission, conducteur | quelques secondes |
| `/autodj/conducteur.json` | file du pupitre et page Conducteur | poll continu |
| `/carts.json` | pads, page Carts | au chargement, puis après chaque geste |
| `/library/search` | colonne recherche | à la frappe, pas en poll |

Les toasts durent le temps d’un message (« Ajouté en suivant », « Session expirée — reconnecte-toi », « Automate injoignable »).

## Page Antenne — `/antenne`

Une page, quatre bandes. Même page pour l’admin et l’animateur. L’admin a en plus le dépannage et trois pastilles.

### Bandeau

S’affiche s’il y a un incident et qu’on n’est pas en direct. Titre de l’incident, ton, « depuis … ». Un toast dit « Incident antenne : … » à l’ouverture et « Antenne rétablie. » à la fermeture.

Incidents vus par l’animateur : silence, encodeur absent (`live_absent`). L’admin voit aussi le reste (moteur, public, local, alertes).

### Carte maintenant

Titre, artiste, barre de temps, écoulé, restant, heure de fin. Source affichée : Arrêt, Direct, « Direct · nom », « nom en attente », « Démo / casque public », ou le libellé de la file.

Cinq puces :

| Puce | Contenu |
| --- | --- |
| Horloge | Nom d’horloge ou plage, sinon — |
| Ancre | `:MM −mm:ss`, sinon — |
| Suivant | Titre de la prochaine ligne de la file |
| Jingle | Prochain jingle annoncé par le direct |
| Émission | Titre en cours, ou le prochain créneau. Rouge si à l’antenne |

Bouton passer. Raccourci espace. Envoie `DELETE /live.json`. Inactif si arrêt ou si un harbor est connecté. En direct, un bandeau : « Direct — l’horloge est en pause ».

Si le harbor est là et qu’aucune émission n’est nommée, la puce Émission ouvre un formulaire dans la carte : « Nommer ce live », champ nom, champ phrase artiste, Enregistrer. Les deux champs sont obligatoires. Cela poste une émission `scope: session`. Ce n’est pas le créneau de la semaine. Toast « Live nommé. »

Sous la carte, les pastilles. L’animateur en voit trois, renommées : Silence (à la place d’Antenne), Auditeurs (à la place de Public), Direct. L’admin en voit six : Antenne, Public, Local, Direct, Moteur, Alertes. Une pastille peut être ok, warn, alert ou off. Si l’état a plus de 30 s ou si la requête a échoué, la bande est marquée périmée et montre l’heure du dernier état.

**Dépannage**, bouton clé à molette, admin seulement.

- Recharger l’état. Pas de confirmation.
- Vider les files Liquidsoap… Confirmation : les titres déjà envoyés à Liquidsoap partent, l’horloge repousse au tick suivant, le titre en cours finit. Toast « Files vidées — l’horloge repousse la suite. »
- Reconstruire le conducteur… Confirmation : les items planifiés sont jetés et reprévus depuis maintenant, les files sont vidées, le titre en cours finit. Toast « Conducteur reconstruit. » Refus possible : « Pas le droit Auto-DJ. »

### File

Titre « File », badge du nom d’horloge. Liste des prochains passages, tronquée (le trop-plein n’est pas montré, un compte le dit).

Chaque ligne : pastille de type (musique, jingle, son, pub), titre, artiste, durée, temps avant l’antenne. La ligne à l’antenne n’est pas dans cette liste : elle est dans la carte.

Une ligne « pin » du pupitre se sélectionne, se retire, se réordonne au glisser, se remplace. Une ligne verrouillée (ancre, ou titre en cours) ne se retire pas et ne se réordonne pas. Glisser un résultat de recherche sur une ligne la remplace.

Sous la liste, **Passé**, replié. Fermé, on voit l’heure et le titre du dernier passage. Ouvert : heure, source (auto-DJ, jingle, cart, direct…), artiste, titre. Si le chemin est connu, bouton pour remettre « en suivant ». Inactif pendant un direct. Toast « Remis en suivant. »

### Bibliothèque

Titre « Bibliothèque ». Champ « Titre, artiste… ». Raccourci `/` pose le curseur dedans. La recherche part vers `/library/search` avec `q`, `limit=40`, et le filtre de l’onglet.

Onglets : Tous, Musique (`grouping=rotation`), Jingles (`kind=jingle`), Pubs (`kind=pub`), Habillage (dossiers beds, stings, sfx), Archives (`grouping` ntf1, ntf2, ntf3), Émissions (`kind=emission`).

Champ vide : bloc Récents, mémorisés dans le navigateur. Sinon la liste, le nombre de résultats, ou « Aucun titre. » Erreur en rouge : « Catalogue injoignable. » ou « Recherche catalogue impossible. »

Chaque ligne est glissable. Double-clic = Maintenant. Boutons :

- Ensuite — insère après la ligne sélectionnée si c’est un pin, sinon en suivant. Toast « Ajouté en suivant. »
- Remplacer — seulement si une ligne de la file est sélectionnée.
- Maintenant — coupe et envoie à l’antenne. Toast « À l’antenne — coupe. » En démo sans Liquidsoap : « Envoyé (démo horloge — pas de Liquidsoap). » Inactif en direct, titre « Direct à l’antenne ».

### Pads

Titre « Pads », bouton **Régler**. Deux rangées de 6 : Jingles, Pubs. Les sons viennent des carts dont le titre est exactement `Jingles` et `Pubs`, dans l’ordre de leur rang. Un autre cart n’apparaît pas ici. Case vide : on peut y déposer un titre seulement en mode Régler.

Hors réglage : clic ou touche lance le son. 1–6 jinglés, majuscule 1–6 pubs. Le pad à l’antenne est marqué. Un pad vient d’être tiré : il clignote. En direct, le tir est bloqué.

En réglage : déposer un résultat de recherche sur une case, échanger deux pads, retirer (croix). Cela réécrit le rang des sons du cart.

### Clavier et APC Mini

Ignoré si le curseur est dans un champ.

| Geste | Effet |
| --- | --- |
| Espace | Passer |
| 1–6 | Pad jingle |
| Majuscule 1–6 | Pad pub |
| `/` | Focus recherche |
| Flèches haut / bas | Ligne suivante ou précédente de la file |
| Retour arrière ou Suppr | Retire la ligne sélectionnée si elle n’est pas verrouillée |

Un APC Mini mk2, s’il est branché et autorisé, reprend les pads, le passage, et une touche de chaîne. Les voyants suivent le pad en cours, la fin proche, et le nombre de sons. Ce n’est pas un écran : rien dans le menu n’en parle. États possibles du branchement : navigateur sans MIDI, geste requis, refus, recherche, débranché, connecté.

## Page Conducteur — `/conducteur`

Prévision, pas le pupitre. Pas de pads, pas de recherche.

En-tête « Conducteur ». Pastille : en onde (vert), démo (ambre), arrêt (gris).

Admin seulement :

- **Relancer.** Reposte le conducteur sans `reset`. Toast « Conducteur relancé ».
- **Réinitialiser.** Dialogue : « Le motif repart du début. Les files jingles, auto-DJ et carts sont vidées, sauf le titre à l’antenne. La prévision et les insertions pupitre prévues sont effacées, puis le conducteur est reconstruit. » Toast « Conducteur réinitialisé ».

Bandeau « À l’antenne » : titre, temps restant en gros, puis faits : Horloge (nom et plage), Ancre (`:MM`, dure ou molle, compte à rebours), File (source brute), Émission (pastille du titre en cours ou du prochain), Horizon (heure du dernier item et durée de fenêtre, souvent 30 min).

Tableau. Colonnes : Heure, Type, Cart, Ressource, Quand, Statut, durée. La liste se cale sur la ligne en cours. Le passé est grisé. La suivante a une icône d’avance. Les heures pleines ont un séparateur « 14 h ». La suite charge par paquets de 36 en scrollant.

Une ligne montre : heure `hh:mm:ss`, restant si c’est la ligne en cours, type (musique, jingle, son, pub), nom du cart, ressource, méta (catégorie, « secours » si le repli a servi, « glissement », file Auto-DJ / Jingles / Carts), quand (« séquentiel », « en direct », ou `:20 dure` / `:00 molle`), statut, durée.

**Réparer** n’apparaît que si le cart d’horloge manque, et seulement pour l’admin. Le dialogue propose un cart existant, ou crée un cart du nom manquant (mode une fois) et ouvre `/carts?id=`. On peut aussi écrire le cart dans la case de l’horloge.

**Retirer** (croix) : ligne qui a un id, qui n’est pas à l’antenne, qui n’est pas ancrée. Animateur compris. Toast « Retiré du conducteur ». Pas de confirmation.

Vide : « Aucun item prévu (pas d’horloge sur le daypart, ou bibliothèque vide). »

Refus des gestes d’écriture : « Droit Auto-DJ requis. »

## Page Carts — `/carts`

Admin. Texte : « Importe tes fichiers ici. Pour les faire tourner tout seuls : Auto-DJ → Ajouter. » Compteurs de carts et de sons.

Trois colonnes.

### Liste

Recherche « Rechercher un cart… ». Bouton **Nouveau**.

Dialogue **Nouveau cart**. Titre (exemple « Jingles »). Mode :

| Mode | Aide affichée |
| --- | --- |
| Boucle | Reprend au début après le dernier son |
| Aléatoire | Tire un son au hasard parmi les pistes actives analysées |
| Une fois | Joue les sons dans l’ordre, une fois |

Le mode relais n’est pas dans cette liste. À la création, `schedule_mode` est `clock`. Toast « Cart créé ». L’URL gagne `?id=`.

Chaque cart de la liste montre son nom et, s’il est posé dans une horloge, la ligne d’usage.

### Sons

En-tête du cart. **Importer dans « … »** : fichiers, ou un dossier. Barre de progression (lecture, puis envoi, nom du fichier). Toast « 1 son importé » ou « N sons importés ». « Aucun fichier audio. » si le choix est vide.

**Attacher depuis la banque.** Dialogue, dossiers cochés, compte de sons. Toast « N sons attachés depuis la banque ». Si la banque n’est pas montée : « La banque n’est pas montée sur cet automate (MEDIA_ROOT). »

Filtre « Filtrer les titres ». Case tout sélectionner.

Chaque son : poignée de rang, aperçu (lecture, barre de position), case actif / inactif, bouton diffuser ce son maintenant, supprimer. L’aperçu est local au navigateur, pas l’antenne.

### Inspecteur

Titre, notes, mode (boucle, aléatoire, une fois). Un cart déjà en relais est réaffiché comme une boucle : l’URL et la durée max du relais ne sont pas des champs ici, alors que le moteur les connaît (`relay`, URL HTTP, durée max obligatoire).

Dossier de banque, parmi `30-habillage/jingles`, `ids`, `pubs`, `beds`, `stings`, `sfx`, ou aucun. Enregistrer. Supprimer, avec confirmation. Diffuser le cart entier. Lien SMB vers `Carts/{id}-{slug}` sur le partage de la marque.

## Page Auto-DJ — `/autodj`

Admin. Tout est sur une seule page qui défile.

S’il y a plusieurs horloges, menu **Rotation** en haut à droite. L’horloge en onde est suffixée « · à l’antenne ». Badge vert « À l’antenne » si on édite celle qui joue. Bandeau ambre sinon : « Tu modifies {nom} — en onde : {autre} ».

Vide total : « Pas d’Auto-DJ. Il n’y a pas encore de rotation. »

### Ce qui tourne

« Dans l’ordre, puis ça recommence. » Compteur de cases. Les cases `musique` sont retirées de l’affichage : la musique de fond n’est pas une ligne ici.

Chaque ligne : rôle (Jingle, Programme, Pubs), liste de tous les carts, lien « N sons » vers `/carts?id=`, monter, descendre, retirer (confirmation « sort de la rotation »). Cart introuvable : « Cart manquant » et la ligne est marquée.

Sans aucune case : « Rien ne tourne encore. Un jingle coupe le titre. Un programme enchaîne les morceaux. » Bouton « Mettre Jingles et Prog ». S’il n’y a pas de carts dont le nom évoque jingles et programme : toast « Crée d’abord Jingles et Prog dans Carts. »

Sous la liste : **Ajouter un jingle**, **Ajouter un programme**, **Ajouter des pubs**. Le cart est deviné par le nom (jingle, pub/spot, sinon un programme). Phrase rappel : un jingle coupe, un programme enchaîne.

### Pubs à :20 et :40

« À cette minute pile, le programme s’interrompt pour les pubs. » Cases `:20` et `:40`. Liste de carts : ceux dont le titre contient pub ou spot, sinon tous les carts sauf ceux dont le titre contient prog. Le choix écrit l’ancre de l’horloge.

### Grille de la semaine

Une ligne de résumé, puis un bloc replié **Grille de la semaine**. L’ouvrir fait défiler la page jusqu’au bloc. Dedans, sept colonnes Lun–Dim. La colonne du jour porte « aujourd’hui ». En tête de colonne : deux boutons, ajouter un départ (plus) et ajouter une émission (micro).

Les blocs déjà posés sont des horloges (plage, nom) et des émissions (nom, horaire, phrase, identifiant s’il y en a un). Cliquer ouvre le dialogue. Une émission dont l’heure contient maintenant est marquée en direct.

**Nouveau départ.** Heure, de 01:00 à 23:00, les heures déjà prises sont absentes. Défaut 10:00 si libre. Horloge, liste des horloges. Texte : elle joue de cette heure jusqu’au départ suivant. Pas de minute libre : c’est l’heure pile. Couleur enregistrée en dur `#7a9e6a`.

**Départ existant.** Jour, début, fin. On peut changer l’horloge. S’il reste des départs internes de la même horloge, un avertissement le dit et un bouton les fusionne. Supprimer. Le départ de minuit ne se supprime pas.

**Nouvelle émission / Émission.** Nom (exemple « Hop Pop Hop »). Identifiant du plateau : « Pas encore nominatif », ou un compte `stream` ou `admin`. Aide : tant qu’aucune émission ne nomme quelqu’un, tout compte stream peut se brancher ; dès qu’une émission a un identifiant, chacun ne passe que sur son créneau ; un admin passe toujours. Phrase artiste (exemple « avec Marie et Jean »). Début et fin, champs heure, 24:00 accepté pour minuit (le champ HTML montre 23:59 et le modèle garde 24:00). Défaut 20:00–22:00. Texte : l’horloge continue tant que personne n’est connecté ; dès que le harbor est là, le titre devient le nom et l’artiste la phrase. Retirer : « L’horloge de la plage n’est pas modifiée. » Les deux textes sont obligatoires pour enregistrer. Un chevauchement est refusé par le moteur (« Ce créneau chevauche une autre émission. »).

Il n’y a pas d’autre page Semaine. Le bouton micro n’existe que dans ce bloc.

## Page Paramètres — `/parametres`

Admin. « Comptes et accès à la console. » Un seul onglet, Comptes. L’ancienne page Comptes redirige ici.

Recherche. Filtre : Tous les comptes, ou Droit Admin, Auto-DJ, Carts, Antenne, Stream. Compteur d’admins.

**Nouveau compte.** Identifiant, mot de passe. Texte : « Les droits Auto-DJ et Carts seront activés par défaut. » Pas de cases dans le dialogue. Le compte naît donc avec `autodj` et `carts`, sans `admin`, sans `stream`, sans `live`. Comme il n’est pas admin, ce compte voit le menu animateur. Il ne peut pas ouvrir Carts ni Auto-DJ. Il ne peut pas entrer au harbor tant qu’on ne lui coche pas Stream ensuite. Toast « Compte créé ».

Tableau. Colonne Compte : identifiant, notes si le moteur en a. Colonne Permissions : cinq cases, chacune enregistrée tout de suite. Libellés et infobulles :

| Case | Clé | Infobulle | Effet réel dans cette console |
| --- | --- | --- | --- |
| Admin | `admin` | Administration des comptes | Ouvre tout le menu |
| Auto-DJ | `autodj` | Programmation automatique | N’ouvre pas Auto-DJ. Le moteur s’en sert pour écrire horloge et conducteur |
| Carts | `carts` | Gestion des carts | N’ouvre pas Carts |
| Antenne | `live` | Contrôle de l’antenne | N’ouvre pas le pupitre (déjà ouvert). Le moteur peut refuser un geste sans ce droit |
| Stream | `stream` | Gestion du flux | Harbor. Apparaît dans la liste « identifiant du plateau » |

Menu de ligne : **Supprimer le compte** seulement. Confirmation : le compte perd immédiatement tous ses accès. Pas de changement de mot de passe. Pas d’édition des notes.

`not_audio` ne figure pas dans le tableau.

## Écrans qui ne s’ouvrent plus

### Atelier Horloges

Était la page Horloges. Toujours compilé, plus de route. C’était un atelier en plusieurs panneaux : liste des horloges, bandeau d’heure type, motif (le même composant que « Ce qui tourne »), inspecteur de case, panneau des carts de l’horloge, dialogue pour poser un cart dans une horloge, réparation d’un cart manquant. Sur un écran étroit, l’inspecteur devenait un tiroir. L’adresse pouvait porter `?clock=`. Aujourd’hui `/horloges` ouvre Auto-DJ, qui n’a pas cet atelier.

### Catégories

Était une table des catégories musicales : nom, requête, requête de repli, nombre de titres. Recherche, filtre toutes / avec titres / sans titre. Créer, modifier, supprimer, essayer la requête, poser la catégorie dans une horloge. Aujourd’hui `/categories` ouvre Auto-DJ. Les catégories existent encore dans le moteur et apparaissent en méta sur une ligne de conducteur. On ne les édite plus dans la console.

## Hors de la console, mais sur le chemin des gens

**Déposer un fichier.** Pas de page. `00-inbox/rotation` pour la rotation, `00-inbox/archives/ntf1` à `ntf3` pour les archives, via le partage SMB ou le Nextcloud déjà branché sur la même banque. Le conteneur dropbox promeut puis Beets indexe. La recherche de la console ne voit le titre qu’après l’index. La console ne montre pas la file d’attente ni les fichiers ignorés.

**Entrer en direct.** Pas de page. BUTT ou Mixxx vers le harbor. Le pupitre, lui, voit la source passer à Direct, bloque pads et passage, et propose de nommer le live. À la coupure, le moteur vide jingles et auto-DJ et saute le titre auto-DJ en cours. Si un créneau hebdo est là et que personne ne se branche, au bout d’environ 90 s la pastille Direct et le bandeau disent que l’encodeur manque. L’horloge continue.

**Écouter le festival.** `https://flux.gabbler.band/ntf/`. Un bouton, pas de lecture automatique. Le son est `https://radio.lazbutton.xyz/button.mp3`. Le titre vient de `https://radio.lazbutton.xyz/now.json` (`artist`, `title`), relu toutes les 15 s. Un fragment HTML est prévu pour une iframe. Aucun lien vers `gabbler.band`.

**Relais.** Pas de page. Ordre du moteur : harbor, relais, carts, jingles, auto-DJ. Un cart `relay` porte une URL. L’écran Carts ne sait pas l’éditer.

## Parcours, geste par geste

### Animateur, une heure d’antenne

1. Ouvre `gabbler.band`. Se connecte. Atterrit sur `/antenne`.
2. Lit la carte et les trois pastilles. Active le son du casque public.
3. Passe un titre (espace) ou laisse l’horloge.
4. `/`, cherche, Ensuite ou Maintenant. Ou tape 1–6.
5. Le harbor se connecte. La pastille du haut devient Direct. Espace et pads meurent. S’il n’y a pas de nom, il remplit la puce Émission.
6. Il ouvre Conducteur, lit l’ancre et l’horizon, retire une ligne non ancrée, revient.
7. Il ne peut pas ouvrir Carts, Auto-DJ, Paramètres, ni changer de casque. Il ne peut pas se déconnecter depuis l’écran.

### Admin, poser la grille

1. Carts. Nouveau, titre Jingles, mode aléatoire. Importe trois fichiers. Même chose pour un cart programme et, si les pads de pub doivent vivre, un cart titré exactement Pubs.
2. Auto-DJ. S’il n’y a rien, « Mettre Jingles et Prog ». Sinon il ajoute, réordonne, ouvre le lien « N sons » qui ramène à Carts.
3. Coche `:20` et `:40`, choisit le cart de pubs.
4. Ouvre Grille de la semaine. Pour chaque jour, départ 00:00 déjà là ou départ à l’heure, horloge de nuit ou de jour. Les heures déjà prises n’apparaissent pas.
5. Micro sur le jour du plateau. Nom, identifiant, phrase, 20:00–22:00. Enregistre.
6. Le compte nommé doit avoir Stream, coché après coup dans Paramètres. Sans ça, il n’est même pas dans la liste.

### Admin, donner un compte

1. Paramètres, créer. Le compte naît Auto-DJ + Carts, et malgré ça il ne voit pas ces pages.
2. Cocher Stream pour le harbor. Cocher Antenne si le moteur doit accepter les gestes du pupitre. Ne pas cocher Admin si la personne ne doit pas voir le reste.
3. Pour le créneau, retour à Auto-DJ, pas un lien depuis la ligne du compte. Rien ne dit sur la fiche du compte quels créneaux il a.

### Admin, réparer

Deux endroits, presque le même geste. Pupitre → Dépannage → vider les files, ou reconstruire. Conducteur → Relancer (sans vider la prévision de la même façon) ou Réinitialiser (vide les files, garde le titre, reconstruit). Une ligne au cart manquant : Réparer, qui crée ou rattache un cart puis peut emmener vers Carts.

## Ce qui ne se voit pas dans le menu

- Le pupitre de l’animateur a les mêmes gestes que celui de l’admin, moins le dépannage et moins trois pastilles.
- Les droits cochés dans Paramètres ne correspondent pas aux pages que la personne peut ouvrir.
- Un compte neuf est créé avec des droits qui ne lui donnent aucune page de plus.
- Jingles et Pubs des pads sont des carts trouvés par leur titre exact, pas par un type.
- La semaine, qui décide qui peut entrer en direct, est un bloc replié en bas d’Auto-DJ.
- Les catégories et l’atelier horloges sont du code sans adresse.
- Le relais, le dépôt, l’écoute publique, les alertes envoyées et la sauvegarde n’ont pas de page.
- On ne sort pas, et on ne change pas un mot de passe.
