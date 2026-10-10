# Programmation — UI et fonctionnement actuel

28 septembre 2026. Description de la page telle qu’elle est dans `ntr-console`. Ce n’est pas une maquette cible. C’est le matériau pour une refonte : ce que la page fait, ce qu’elle affiche, ce qu’elle ne doit pas casser.

La page est `/programmation`. Le menu ne la montre qu’au programmateur et à l’admin. Un animateur qui force l’adresse voit « Accès réservé » et un retour vers l’antenne. Il n’y a pas de variante d’écran entre programmateur et admin : les deux voient les mêmes quatre onglets, les mêmes boutons, les mêmes dialogues.

La page ne produit pas le son. Elle écrit la grille que le moteur lira plus tard. La priorité des sources n’est pas réglée ici : direct (harbor), puis relais, puis carts, puis jingles, puis rotation.

## Autour de la page

La coque est hors de la page, mais elle change l’usage :

- Menu : Antenne, Conducteur, Programmation, Sons, Réglages. Sur un écran étroit, le menu devient un bouton « Ouvrir la navigation ».
- La zone de page porte les classes `app-page--horloges` et `app-page--autodj`. Elle n’est pas plafonnée à 86 rem, contrairement aux autres sections : la semaine a besoin de la largeur.
- Thème clair ou sombre, lien « Code source », Déconnexion.
- L’écoute dans la barre du haut ne change rien à cette page.

## Mise en page

Une colonne. En haut, un titre de section, puis quatre onglets. L’onglet actif est dans l’adresse.

```
┌ Programmation                                                       ┐
│  Rotation, horloges, semaine et catégories.                         │
│  [ Rotation ]  Horloges   Semaine   Catégories                      │
├─────────────────────────────────────────────────────────────────────┤
│  (l’onglet choisi, avec souvent un second titre à lui)              │
└─────────────────────────────────────────────────────────────────────┘
```

| Onglet | Adresse | Second titre dans l’onglet |
|---|---|---|
| Rotation | `/programmation` | « Rotation » |
| Horloges | `/programmation?onglet=horloges` | « Atelier Horloges » |
| Semaine | `/programmation?onglet=semaine` | « Semaine », plus une bande « À l’antenne » |
| Catégories | `/programmation?onglet=categories` | « Catégories » |

L’onglet par défaut n’écrit pas `onglet` dans l’adresse. Un `onglet` inconnu retombe sur Rotation. Changer d’onglet remplace l’adresse (`replace`), sans empiler l’historique. L’onglet inactif n’est pas monté : en revenir recharge ses données et oublie ce qui n’a pas été enregistré (recherche de catégorie, case cochée à moitié, inspecteur ouvert).

`?clock=` est lu par l’atelier Horloges pour présélectionner une horloge, si l’identifiant existe.

## Chargement et pannes

Chaque onglet a sa propre porte de session. La section elle-même n’attend pas le moteur.

| Situation | Ce que la personne voit |
|---|---|
| Session expirée | Écran de connexion, à la place de toute la console |
| Rôle insuffisant | « Accès réservé » |
| Horloges pas encore arrivées (Rotation ou Horloges) | « Chargement… » à la place du contenu de l’onglet |
| Horloges injoignables, sans cache | « Radiotomate est indisponible », bouton Réessayer |
| Semaine : départs ou horloges ou émissions en erreur, sans cache | Même écran d’indisponibilité |
| Catégories en erreur | Même écran. Tant que la liste n’est pas arrivée, la porte ne montre pas « Chargement… » : elle attend la réponse ou l’erreur |
| Carts, catégories ou conducteur absents pendant qu’une horloge est déjà là | L’onglet s’affiche. Les listes de carts peuvent être vides. Le badge « À l’antenne » peut manquer |

Les toasts disent l’échec d’une écriture, avec le message du moteur quand il y en a un (« Enregistrement impossible. », « Création impossible. », « Suppression impossible. », « Nettoyage impossible. », « Test impossible. »).

## D’où vient le contenu

| Onglet | Requête | Rythme |
|---|---|---|
| Rotation, Horloges | `GET /autodj/clocks.json` | à l’ouverture, puis après chaque écriture |
| Rotation, Horloges | `GET /carts.json` | à l’ouverture |
| Rotation, Horloges | `GET /autodj/conducteur.json` | 15 s, pour savoir quelle horloge est en onde |
| Horloges | `GET /autodj/categories.json` | à l’ouverture |
| Horloges, Semaine | `GET /autodj/slots.json` | Horloges : à l’ouverture. Semaine : 10 s |
| Semaine | `GET /autodj/clocks.json`, `GET /antenne/emissions.json` | 10 s |
| Semaine, dialogue émission | `GET /users.json` | à l’ouverture du dialogue |
| Catégories | `GET /autodj/categories.json` | à l’ouverture |
| Catégories, « Tester la requête » | `GET /autodj/testquery.json?query=` | au clic |

Le nom d’horloge « à l’antenne » est `clock` dans le conducteur, comparé au nom de l’horloge, pas à son id.

## Écritures

Toutes passent par le moteur, avec le jeton CSRF habituel. Les champs ci-dessous sont les vrais noms JSON.

| Geste | Requête | Corps utile |
|---|---|---|
| Enregistrer une horloge (motif, ancres, nom, secours) | `PUT /autodj/clocks/{id}.json` | `name`, `version`, `fallback_cart`, `fallback_cart_id`, `motif`, `anchors` |
| Créer une horloge | `POST /autodj/clocks.json` | `name`, `fallback_cart`, `motif`, `anchors` |
| Supprimer une horloge | `DELETE /autodj/clocks/{id}.json` | — |
| Créer un départ | `POST /autodj/slots.json` | `title`, `day_of_week`, `minute`, `clock_id`, `color` |
| Changer l’horloge d’une plage | `PUT /autodj/slots/{id}.json` | `title`, `clock_id`, `color` |
| Supprimer un départ | `DELETE /autodj/slots/{id}.json` | — |
| Créer une émission hebdo | `POST /antenne/emissions.json` | `scope: "weekly"`, `title`, `artist`, `day_of_week`, `start_minute`, `end_minute`, `host_username` |
| Modifier une émission | `PUT /antenne/emissions/{id}.json` | les mêmes champs, plus `version` |
| Retirer une émission | `DELETE /antenne/emissions/{id}.json` | — |
| Créer une catégorie | `POST /autodj/categories.json` | `name`, `query`, `empty_query` |
| Modifier une catégorie | `PUT /autodj/categories/{id}.json` | `name`, `query`, `empty_query` |
| Supprimer une catégorie | `DELETE /autodj/categories/{id}.json` | — |

`title` d’une émission est le nom. `artist` est la phrase affichée comme artiste. `host_username` est l’identifiant du plateau, ou une chaîne vide si le créneau n’est pas nominatif. Le jour est `day_of_week` (0 = lundi). Les heures sont des minutes depuis minuit (`start_minute`, `end_minute`), pas des chaînes « début » / « fin ».

`PUT` d’une horloge retire toujours les cases `kind: "musique"` avant l’envoi (`withoutLibrarySteps`). Une sauvegarde ne peut pas poser une catégorie Beets dans le motif.

`color` d’un départ créé depuis cette page est fixé à `#7a9e6a`. Il n’y a pas de sélecteur de couleur.

## Onglet Rotation

Deuxième titre : « Rotation ». Phrase : « Jingles coupe, un programme enchaîne. Les pubs tombent à :20 et :40. La semaine est l’onglet à côté. »

À droite du titre : un badge vert « À l’antenne » si l’horloge éditée porte le même nom que le conducteur. Pendant une écriture, le badge cède la place à un statut (« Enregistrement… », « Nettoyage… », « Ajout… », etc.).

S’il y a plusieurs horloges, un menu « Rotation » permet d’en choisir une. L’horloge en onde est marquée « {nom} · à l’antenne ». S’il n’y en a qu’une, le menu n’est pas là.

S’il n’y a aucune horloge : carte « Pas d’Auto-DJ », texte « Il n’y a pas encore d’horloge. Pose d’abord un départ dans l’onglet Semaine. » Pas de bouton pour en créer une ici. La création est dans Horloges.

Si l’horloge éditée n’est pas celle en onde, un bandeau ambre : « Tu modifies {nom} — en onde : {nom en onde} ».

### Ce qui tourne

Liste ordonnée du motif, après avoir retiré les cases « Bibliothèque » (`kind` musique). Compteur = nombre de cases restantes.

Chaque ligne :

- pastille de type (jingle, programme, pub) ;
- libellé Jingle, Programme ou Pub ;
- « Cart manquant » si le cart cité n’est plus dans `/carts.json` ;
- menu de tous les carts ;
- lien « 1 son » ou « N sons » vers `/sons?id={id}`, ou un tiret si le cart manque ;
- Monter, Descendre, Retirer.

Monter et Descendre sont des boutons icône. Le premier ne monte pas, le dernier ne descend pas. Retirer ouvre « Retirer {type} ? » et nomme le cart. Confirmation « Retirer ».

Sous la liste, trois boutons : « Ajouter un jingle », « Ajouter un programme », « Ajouter des pubs ». L’ajout devine un cart : titre qui contient « jingle », cart pubs (`pickPubCart`), sinon cart programme (`pickProgCart`). Toast « {titre} ajouté » ou « Case ajoutée ».

Liste vide : « Rien ne tourne encore », « Un jingle coupe le titre. Un programme enchaîne les morceaux. », bouton « Mettre Jingles et Prog ». Si Jingles et Prog n’existent pas dans Sons, le toast dit « Crée d’abord Jingles et Prog dans Sons. » et rien n’est écrit.

Note sous les boutons : « Un jingle coupe le titre en cours. Un programme enchaîne les morceaux. »

À l’ouverture, si le motif contient encore une case Bibliothèque, la page l’enregistre sans cette case. Toast « Cases bibliothèque retirées ». Ce n’est pas un bouton. Ouvrir l’onglet suffit.

### Pubs à :20 et :40

Carte sous la liste. Titre « Pubs à :20 et :40 ». Phrase : « À cette minute pile, le programme s’interrompt pour les pubs. »

Deux cases : « :20 » et « :40 ». Un menu « Cart ». Cocher crée une ancre `kind: "pub"`, `sync: "dure"`, à la minute 20 ou 40. Décocher retire cette ancre. Changer le cart met à jour les deux ancres si au moins une existe. Le menu préfère les carts dont le titre contient « pub » ou « spot » ; sinon tous les carts sauf ceux dont le titre contient « prog ».

Les cases sont désactivées tant qu’aucun cart n’est choisi, ou pendant une écriture.

## Onglet Horloges

C’est l’atelier. Sourcil « Programmation Auto-DJ », titre « Atelier Horloges », phrase « Le motif enchaîne tes carts : Jingles, puis Prog, puis ce que tu accroches. »

Même badge « À l’antenne » ou statut d’écriture que Rotation. À droite, un bouton « Semaine » qui va à `?onglet=semaine`.

Trois colonnes quand la fenêtre fait plus de 1220 px :

```
┌ Horloges          ┬ Heure type + motif + carts     ┬ Inspecteur ┐
│  liste            │  réglet 0–60                   │  formulaire│
│  sparkline        │  « Ce qui tourne »             │            │
│  usage semaine    │  carts accrochés               │            │
└───────────────────┴────────────────────────────────┴────────────┘
```

Sous 1220 px, l’inspecteur quitte la colonne et s’ouvre en feuille (dialogue). Un bouton « Inspecteur » apparaît sur « Heure type ». Choisir une case ou une ancre ouvre la feuille. Sous 860 px, la liste d’horloges passe au-dessus de l’atelier, limitée en hauteur. Sous 620 px, la page défile au lieu de tenir dans l’écran.

Sans horloge : la liste reste, avec le bouton Nouveau, et une carte « Aucune horloge » / « Créez une horloge pour composer son motif et placer ses ancres dans l’heure. »

### Liste des horloges

Titre « Horloges », « Recettes réutilisables », compteur.

Bouton « Nouveau » : dialogue nom (exemple « Journée pubs ») et « Cart de secours » (Aucun, ou un titre de cart). Phrase : le motif et les ancres se règlent dans l’atelier. Création : motif par défaut Jingles puis Prog si ces carts existent, ancres vides. Toast « Horloge créée ».

Chaque carte : nom, sparkline de l’heure, « N positions », ancres « :20 / :40 » ou « sans ancre ». L’horloge dont le nom est celui du conducteur porte un badge « Antenne » et une icône radio, seulement sur la carte sélectionnée.

Pied de liste : « Cette horloge est à l’antenne. », ou « Chargement des dayparts… », ou « Utilisée : Lun 00:00, … » (huit créneaux max, puis « … ») avec un lien Semaine, ou « Aucun daypart » et le même lien.

« Supprimer » en bas, sur l’horloge sélectionnée. Confirmation « Supprimer « {nom} » ? ». Le texte dit que les dayparts qui l’utilisent devront être reconfigurés. Toast « Horloge supprimée ». Changer d’horloge ferme l’inspecteur et la feuille.

### Heure type

Réglet de 0 à 60 minutes, gradué :00 :10 :20 :30 :40 :50 :60. Légende « Poser une ancre ». Au survol, la minute s’affiche. Clic sur une minute libre prépare une ancre (pas encore enregistrée). Clic sur une minute déjà prise ouvre cette ancre. Flèches gauche et droite déplacent la minute au clavier, Entrée ou Espace la choisit.

Sous le réglet, les plages entre ancres sont des boutons « Remplissage ». Ils montrent la chaîne des cases (« Cart Jingles → Cart Prog ») et les bornes. Cliquer une plage sélectionne une case du motif (la dernière consultée, sinon la première).

Les ancres déjà posées sont des repères sur le réglet.

### Motif dans l’atelier

Le même composant que « Ce qui tourne » sur Rotation, avec trois différences :

- les cases Bibliothèque ne sont pas retirées à l’affichage, mais toute sauvegarde les enlève quand même ;
- retirer une case remet l’inspecteur au repos ;
- réordonner resélectionne la case déplacée.

Toasts : « Cart changé », « Position retirée », « Motif réordonné », « {titre} ajouté », « Jingles et Prog ».

### Carts de cette horloge

Titre « Carts de cette horloge ». Phrase : « Ce que l’Auto-DJ joue vraiment : Jingles et Prog, plus ce que tu accroches. »

Liste des carts déjà cités par le motif ou les ancres. Chaque ligne est un lien vers Sons, avec le rôle et « (défaut) » pour le programme par défaut, plus un badge du nombre de titres.

Bouton « Accrocher un cart » : dialogue pour poser un cart dans cette horloge (horloge fixée à celle de l’atelier). Le bouton est inactif s’il n’y a aucun cart.

Sous la liste, les carts qui ne sont pas dans l’heure : « Pas encore dans l’heure : {titres}. » Lien « Nouveau cart » vers `/sons`.

État vide : « Aucun cart accroché. Ajoute Jingles puis Prog. »

Le dialogue « réparer un cart manquant » est dans le code de la page. Aucun bouton ne l’ouvre. Un cart disparu se voit seulement par « Cart manquant » dans la liste du motif.

### Inspecteur

Au repos (rien de sélectionné) : nom de l’horloge, cart de secours, bouton « Enregistrer » actif seulement si le nom a changé. Note : « Cliquez une position du motif ou une ancre de la timeline pour l’inspecter. » Le nom modifié ici est celui que la Semaine affiche.

Case du motif sélectionnée : sourcil « Motif séquentiel », titre « Motif N ». Champs :

- Type : Jingle, Programme, Pub. L’aide change avec le type (jingle coupe souvent le titre, programme est le cart de titres, pub est souvent calé à une minute).
- Cart, ou « Catégorie Beets » si le type interne est encore Bibliothèque. L’aide dit que la musique BUTTON tourne depuis un cart Programme. Le menu des types ne propose pas Bibliothèque.
- Secours de la position, ou « Secours d’horloge » pour hériter.
- Note : après la dernière position, la lecture reprend à la première.

Ancre existante : sourcil « Position ancrée », titre « Ancre :MM ». Mêmes champs, plus un interrupteur Dure / Molle.

- Dure : le programme en cours est coupé pour partir à la minute.
- Molle : le titre se termine ; l’ancre est sautée si une ancre dure suivante arrive.

Bouton « Retirer » avec confirmation. La zone redevient du remplissage.

Ancre seulement préparée (clic sur une minute vide) : badge « À créer ». Le bouton dit « Créer l’ancre ». Tant qu’on n’enregistre pas, rien n’est en base. Une nouvelle ancre de type pub préremplit un cart dont le titre contient « pub », s’il y en a un.

Badge « Modifié » tant que le formulaire diffère de ce qui est enregistré. L’enregistrement n’est pas automatique, contrairement à Rotation où chaque geste écrit tout de suite.

## Onglet Semaine

Titre « Semaine ». Phrase : « Un départ charge une horloge jusqu’au suivant. Les émissions live se superposent : l’horloge continue tant que le harbor n’est pas là. Dès que le harbor est connecté, tout le reste cède. »

À droite, si des départs consécutifs répètent la même horloge : bouton « Nettoyer N départs ». Confirmation qui cite le nombre et un exemple de journée (00h–10h, 10h–18h, 18h–24h). Le nettoyage supprime ces départs internes un par un. Toast « Départ inutile retiré » ou « N départs inutiles retirés ».

Sinon, un badge gris « 7 jours · N plages / jour type » (N = plages du jour courant, pas une moyenne).

### Bande « À l’antenne »

Heure de Paris `hh:mm`. Bloc courant : nom de l’horloge, « hh:mm → hh:mm · encore N h M min », ou « Aucune horloge » / « Hors grille ». Bloc « Ensuite » : jour, heure, nom. Bloc « Émission » si `next` est présent dans `/antenne/emissions.json` : titre, jour, heure de début.

Le mot « Direct » sur une plage du jour veut dire que l’horloge de cette plage couvre l’heure de Paris. Ce n’est pas le harbor. Le harbor est décrit dans la phrase du titre, pas par ce badge.

### Sept colonnes

Lundi à dimanche, date du jour dans la semaine civile de Paris, pastille « aujourd’hui » sur le jour courant. Chaque colonne a deux boutons icône : « Ajouter un départ le {jour} » et « Ajouter une émission le {jour} ».

Les plages empilées prennent une hauteur proportionnelle à leur durée (au moins l’équivalent d’une heure). Une plage affiche l’intervalle, le nom d’horloge (ou « Sans horloge »), la durée, et « · N départs identiques » si plusieurs départs de la même horloge ont été fusionnés à l’affichage. La plage en cours a une barre de progression et le badge « Direct ». Cliquer ouvre le dialogue de la plage.

Les émissions hebdo (`scope` différent de `session`) sont des boutons par-dessus la journée, calés sur `start_minute` / `end_minute`. Hauteur minimale visuelle de 30 minutes. Texte : « Émission », titre, fenêtre, phrase artiste, identifiant du plateau. Cliquer ouvre le dialogue de l’émission. Une émission de session (le live nommé depuis l’antenne) n’apparaît pas dans la grille.

Sans aucun départ : « Aucune plage programmée », « Il faut un départ à minuit chaque jour, puis éventuellement 10h et 18h. », bouton « Ouvrir la rotation » qui revient à `/programmation`.

Sous 1180 px, les sept colonnes défilent horizontalement (chaque colonne garde environ 12,5 rem). Sous 720 px, les jours s’empilent, le jour courant passe en premier, et chaque journée fait au moins 16 rem de haut. La bande « À l’antenne » passe sur deux lignes.

### Dialogue d’une plage

Titre « {Jour} · hh:mm → hh:mm ». La phrase dit que la plage joue telle horloge sans interruption, et mentionne les départs internes s’il y en a.

S’il reste des départs de la même horloge à l’intérieur : avertissement avec leurs heures, bouton « Fusionner en une seule plage ».

Champ « Horloge jusqu’au prochain changement ». L’aide dit que seul le départ de début de plage est modifié. Enregistrer envoie le nom de l’horloge comme `title` du slot, et `clock_id`. Toast « Horloge de la plage enregistrée ».

Champ « Ajouter un départ à », heures pleines strictement à l’intérieur de la plage. Bouton « Départ hh:00 » qui crée un slot à `minute = heure × 60`. Inactif tant qu’aucune heure n’est choisie.

Le départ de minuit (`minute` 0) ne se supprime pas. Le bouton est remplacé par « Départ de minuit obligatoire ». Les autres ont « Supprimer hh:mm ». Confirmation : la plage précédente se prolonge jusqu’à la fin de celle-ci.

### Nouveau départ

Titre « Nouveau départ · {jour} ». Heures pleines de 01:00 à 23:00 qui ne sont pas déjà un début de plage. Défaut 10:00 si cette heure est libre. Menu des horloges. Toast « Départ ajouté {jour} hh:00 ». Minuit ne se crée pas ici : il est déjà le départ obligatoire.

### Émission

Titre « Nouvelle émission · {jour} » ou « Émission · {jour} ». Phrase : l’horloge continue tant que personne n’est connecté ; dès que le harbor est là, le titre devient le nom et l’artiste la phrase.

| Champ à l’écran | JSON |
|---|---|
| Nom de l’émission | `title` |
| Identifiant du plateau | `host_username` |
| Phrase artiste | `artist` |
| Début | `start_minute` |
| Fin | `end_minute` |

Défaut à la création : 20:00–22:00, exemple de nom « Hop Pop Hop », exemple de phrase « avec Marie et Jean ». Les deux textes sont obligatoires. Le début et la fin sont des champs heure. 24:00 est accepté pour minuit ; le champ HTML affiche 23:59 et le modèle garde 24:00.

L’identifiant du plateau liste les comptes qui ont le droit Stream ou qui sont admin (`listedAsHost`), plus « Pas encore nominatif ». L’aide : tant qu’aucune émission ne nomme quelqu’un, tout compte stream peut se brancher ; dès qu’une émission a un identifiant, chacun ne passe que sur son créneau ; un admin passe toujours.

« Retirer » sur une émission existante. Confirmation : « L’horloge de la plage n’est pas modifiée. »

Un chevauchement est refusé par le moteur. La page affiche le message reçu, sans texte local dédié.

## Onglet Catégories

Sourcil « Programmation », titre « Catégories ». Phrase : « Une requête Beets choisit les titres. Le repli sert quand la requête ne ramène rien. » Bouton « Nouvelle catégorie ».

Cet onglet vouvoie (« Créez », « Définissez », « sera supprimée »). Les trois autres tutoient.

Barre : recherche « Nom ou requête Beets… », filtre « Toutes les catégories » / « Avec des titres » / « Sans titre », compte « N au total » ou « N sur M ».

Tableau : Nom, Requête Beets, Titres (badge vert si le compte est > 0, gris sinon), Repli si vide (« Non défini » si vide), menu d’actions.

Menu de ligne :

- Tester la requête : appelle `testquery` avec la requête principale, pas le repli. Le nombre de titres s’écrit sous le nom (« N titres »). L’échantillon renvoyé n’est pas affiché.
- Modifier.
- Supprimer, après confirmation « définitivement ».

Recherche sans résultat : « Aucun résultat » et « Réinitialiser les filtres ». Liste vide : « Aucune catégorie » et « Créer une catégorie ».

Dialogue créer / modifier : Nom, Requête Beets, Repli si vide. Aides : « Rotation 24/24 : path:/media/10-rotation. Thème : grouping:jazz. » et « Optionnel. Cette requête est utilisée lorsque la sélection principale ne retourne rien. » Nom et requête sont obligatoires. Le repli peut rester vide.

Sous 760 px le tableau se replie en fiches (le libellé de colonne passe au-dessus de la cellule, via `data-label`).

## Deux endroits pour la même horloge

Rotation et Horloges écrivent le même `PUT /autodj/clocks/{id}.json`.

| | Rotation | Horloges |
|---|---|---|
| Ce qu’on voit du motif | Cases jingle, programme, pub | Les mêmes, plus l’heure entière |
| Écriture | À chaque geste | Au bouton Enregistrer de l’inspecteur ; le motif, lui, écrit à chaque geste |
| Ancres :20 et :40 | Deux cases à cocher et un cart | Le réglet et l’inspecteur, n’importe quelle minute, dure ou molle |
| Cases Bibliothèque | Retirées dès l’ouverture de l’onglet | Retirées à la prochaine sauvegarde |
| Créer ou supprimer une horloge | Non | Oui |
| Voir où l’horloge est posée dans la semaine | Non | Pied de la liste, lien vers Semaine |

La Semaine ne modifie pas le motif. Elle choisit quelle horloge joue à partir d’une heure. Une émission ne remplace pas l’horloge : elle se pose par-dessus, et le harbor, quand il est branché, passe devant.

## Ce que la refonte doit pouvoir encore faire

- Choisir l’horloge qui tourne, en voir le motif, le réordonner, changer le cart d’une case, en ajouter, en retirer.
- Poser et retirer les pubs à la minute, au minimum :20 et :40 en coupure dure.
- Créer, renommer, supprimer une horloge, et savoir lesquelles sont à l’antenne ou utilisées dans la semaine.
- Poser un départ (heure pleine, jour, horloge), le changer, le couper, et ne pas pouvoir effacer le départ de minuit.
- Poser une émission hebdo avec `title`, `artist`, `host_username`, jour et minutes, et montrer le refus du moteur si deux émissions se chevauchent.
- Créer, modifier, supprimer, tester une catégorie Beets (`query`, `empty_query`, `count`).
- Revenir vers Sons sur un cart précis (`/sons?id=`).
- Rester réservé au programmateur et à l’admin, avec le même écran pour les deux.
