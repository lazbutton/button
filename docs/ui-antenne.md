# Antenne — UI et fonctionnement actuel

28 septembre 2026. Description de la page telle qu’elle est dans `ntr-console`, après les étapes 3 (pupitre), 5 (idents par drapeau) et 6 (passer en direct). Ce n’est pas une maquette cible. C’est le matériau pour une refonte : ce que la page fait, ce qu’elle affiche, ce qu’elle ne doit pas casser.

La page est `/` et `/antenne`. Les deux montrent le même écran. Il n’y a pas de titre « Antenne » dans le contenu : le menu dit où l’on est. La racine visuelle est `desk desk--pupitre`.

Même page pour tous les rôles. L’animateur, le programmateur et l’admin voient les mêmes blocs. Le dépannage (vider les files, reconstruire le conducteur, les six pastilles de santé) n’est pas ici. Il est dans Réglages → Automate.

La page ne produit pas le son. Elle lit l’état du moteur et envoie des ordres JSON. La priorité des sources n’est pas réglée ici : direct (harbor), puis relais, puis carts, puis jingles, puis rotation.

## Autour de la page

La coque est hors de la page, mais elle change l’usage :

- Menu : Antenne, Conducteur, et selon le rôle Programmation, Sons, Réglages. Sur un écran étroit, le menu devient un bouton « Ouvrir la navigation ».
- Écoute : un bouton dans la barre choisit ce que *cette personne* entend (flux public, ou une autre source). Ça ne change pas ce que les auditeurs entendent.
- Thème clair ou sombre, lien « Code source », Déconnexion.

## Mise en page

Une colonne, de haut en bas. La zone file + bibliothèque prend la place restante et défile à l’intérieur des cartes. Le panneau « Passer en direct » est long : sur un petit écran, il pousse la carte « maintenant » et les idents plus bas. La page elle-même peut défiler (`overflow: auto` sur `.desk--pupitre`).

```
┌ bandeau d’état          En onde | Silence | Direct | Problème    heure ┐
┌ Passer en direct                                                    ┐
│  état du harbor : Branché | En attente | Absent                     │
│  règle du créneau, droit du compte                                  │
│  fiche encodeur (Icecast, adresse, port, mount, format)             │
└─────────────────────────────────────────────────────────────────────┘
┌ maintenant                                                          ┐
│  restant    artiste — titre                         [ Passer ]      │
│             barre de lecture                                        │
│             source · fin hh:mm                                      │
│             « Direct — l’horloge est en pause » (si harbor)         │
│             rappel clavier                                          │
│             formulaire « Nommer ce live » (si harbor et pas de nom) │
└─────────────────────────────────────────────────────────────────────┘
┌ File (un peu plus large)          ┬ Bibliothèque                    ┐
└───────────────────────────────────┴─────────────────────────────────┘
┌ Idents   [ Régler ]                                                 ┐
│  1  2  3  4  5  6                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

Sous 1100 px, file et bibliothèque passent l’une sous l’autre. Les six idents restent sur une seule ligne. Sous 640 px, la fiche encodeur passe en une colonne (le libellé au-dessus de la valeur).

## Chargement et pannes

| Situation | Ce que la personne voit |
|---|---|
| `/live.json` pas encore arrivé | « Chargement… » à la place de la page |
| `/live.json` ou le conducteur injoignable, sans donnée en cache | « Radiotomate est indisponible », texte qui dit de réessayer, bouton Réessayer |
| Session expirée | Écran de connexion |
| Émissions, carts ou `/antenne/state.json` absents | La page s’affiche quand même. La carte « maintenant » peut montrer un tiret. Le bandeau se rabat sur ce que `/live.json` sait. |

Les toasts (coin de page) disent l’échec d’une action et, quand c’est possible, quoi faire : se reconnecter, réessayer, demander le droit antenne à un admin.

## D’où vient le contenu

| Bloc | Requête | Rythme |
|---|---|---|
| Bandeau, carte maintenant, Passer | `GET /live.json` | 1 s |
| File | `GET /autodj/conducteur.json?horizon=360` | 3 s |
| Nom du live, règle de créneau | `GET /antenne/emissions.json` | 3 s |
| Idents | `GET /carts.json` | 8 s |
| Bandeau Silence / Problème, état harbor « en attente » | `GET /antenne/state.json` | 5 s |
| Bibliothèque | `GET /library/search` (catalogue, pas le moteur) | à la frappe, après 80 ms |

Écritures :

| Geste | Requête |
|---|---|
| Passer | `DELETE /live.json` |
| Jouer maintenant | `POST /autodj/conducteur/now.json` |
| À la suite | `POST /autodj/conducteur/items.json` |
| Retirer un item posé au pupitre | `DELETE /autodj/conducteur/items/{id}.json` |
| Retirer un item d’horloge | `POST /autodj/conducteur/items.json` avec `suppress_at` |
| Réordonner les items « pupitre » | `PUT /autodj/conducteur/items/ranks.json` `{ids}` |
| Nommer ce live | `POST /antenne/emissions.json` `{scope:"session", title, artist}` |
| Lancer un ident | `POST /carts/{id}/sounds/{id}/now.json` |
| Ranger un ident (mode Régler) | `PUT` du rang des sons du cart marqué pads d’idents |

Les champs réels sont `title` et `artist`, pas « nom » et « phrase ». `title` est le nom de l’émission. `artist` est la phrase affichée comme artiste.

## Bandeau d’état

Une ligne, `role="status"`. Un point, un libellé, l’heure de Paris `hh:mm`. Même histoire pour tous les rôles.

| Libellé | Quand |
|---|---|
| Direct | Le harbor est la source. S’il y a un nom d’émission : « Direct : {titre} ». |
| Problème | Hors direct, et le live est offline, le playout est injoignable, ou un incident `playout_down`, `heartbeat` ou `icecast_down` est ouvert. |
| Silence | Hors des cas ci-dessus, silence d’au moins 3 s, ou incident `silence`. À partir de 20 s le bandeau passe en `is-hot`. |
| En onde | Le reste du temps, s’il y a du son. |

`live_absent` (créneau ouvert, encodeur pas là) ne force pas « Problème » si le son de l’horloge est là. Ce cas est dit dans le panneau « Passer en direct » (« En attente »), pas dans ce bandeau.

Le direct gagne sur le silence et sur un playout annoncé en panne : si le harbor est branché, le bandeau dit Direct.

## Passer en direct

Carte toujours ouverte, sous le bandeau. Ce n’est pas un bouton pour lancer le direct. Le son entre par un encodeur externe (BUTT ou Mixxx). La carte dit où en est le harbor et comment se brancher.

États, lus dans `/live.json` et `/antenne/state.json` :

| État | Sens |
|---|---|
| Branché | La source est le harbor (`stream` ou `harbor`), et le live n’est pas offline. |
| En attente | Pas branché, mais un créneau est ouvert (`emission.state` vaut `waiting`), le prochain créneau est `active`, ou l’incident `live_absent` est ouvert. L’horloge tient l’antenne. |
| Absent | Pas d’encodeur, pas de créneau qui l’attend. La rotation continue. |

Si le live est offline et que le harbor n’est pas branché, le détail devient « L’antenne ne répond pas. »

Textes associés :

- Branché : l’encodeur est à l’antenne. Couper BUTT ou Mixxx rend la grille. Le moteur vide les files. La page ne refait pas cette coupure.
- En attente : un créneau est ouvert, l’encodeur n’est pas là.
- Absent : pas d’encodeur, la rotation continue.

Règle de créneau : si l’émission en cours est hebdomadaire et nomme un compte (`host_username`), le texte dit que seul ce compte, ou un admin, peut se brancher. Sinon, la règle générale : un créneau nominatif réserve le harbor à ce compte ou à un admin ; sans nom, tout compte avec le droit Stream peut se brancher.

Ligne de compte :

- Admin : « Un admin peut se brancher même hors créneau. »
- Droit Stream : « Ton identifiant encodeur : {username}. »
- Sans ce droit : « Ce compte n’a pas le droit Stream : l’encodeur sera refusé. »

Fiche, toujours visible :

| | |
|---|---|
| Type | Icecast, BUTT ou Mixxx |
| Adresse | `192.168.1.100` sur place (ou l’hôte SMB de la marque), nom Tailscale hors studio |
| Port | 6800 |
| Mount | `/stream` |
| Compte | Identifiant du compte, droit Stream, mot de passe du compte |
| Format | MP3, 128 à 192 kbps |

## Carte maintenant

Gros restant `mm:ss` à gauche. Au centre, « artiste — titre », un point de couleur selon le genre (musique, jingle, son, pub), une barre de progression, un badge de source, et « fin hh:mm » si on connaît une fin.

Le titre vient d’abord de l’item du conducteur qui couvre « maintenant », sinon du live. En harbor, le temps écoulé et le restant viennent du live, pas de l’horloge.

Badge de source :

| | |
|---|---|
| Arrêt | live offline |
| Direct | harbor |
| Sinon | le libellé du moteur (Auto-DJ, Cart, Jingle, Relais…) |

Si le restant est entre 1 et 15 secondes, la carte prend la classe `is-ending`.

Vide : « Cherche un titre et mets-le à la suite ». Pas de barre utile.

**Passer.** Bouton rouge, icône skip. Coupe le titre en cours (`DELETE /live.json`). Désactivé si offline ou si le harbor est à l’antenne. Ce n’est pas « passer en direct ». En direct, le bouton ne fait rien, y compris via la barre d’espace.

Sous le titre, si harbor : « Direct — l’horloge est en pause ».

Rappel clavier, toujours : « Espace passer · 1–6 idents · / chercher · Entrée à la suite ».

**Nommer ce live.** Visible seulement si le harbor est branché et qu’aucune émission courante n’est posée (ni dans le live, ni dans `/antenne/emissions.json`). Deux champs : « Nom de l’émission », « Phrase artiste ». Bouton Enregistrer, désactivé tant que l’un des deux est vide. Succès : toast « Live nommé. », champs vidés. Le bandeau peut alors devenir « Direct : {titre} ».

## File

Titre « File », et le nom de l’horloge en cours s’il y en a une.

Liste des **10** prochains items. S’il y en a plus : « encore N dans le conducteur ». Le passé n’est pas montré.

Chaque ligne : rang (« N » pour le premier, sinon 1, 2, 3… — le premier prochain est marqué `is-next`), temps avant l’antenne, point de genre, puis un badge :

- ancre d’horloge : heure `:mm` en rouge, ou « Ancre » ;
- item posé depuis cette page : « pupitre » ;
- sinon rien (c’est le motif).

Puis artiste / titre, durée.

Retirer : croix, libellé « Retirer {titre} ». Un item verrouillé montre un cadenas « Verrouillé » à la place. Après un retrait, toast « Retiré de la file. » pendant 8 secondes, avec Annuler si on sait reconstruire la ligne.

Réordonner : glisser seulement les lignes « pupitre » qui ne sont pas verrouillées. Les items d’horloge ne se réordonnent pas ici.

Vide : « Cherche un titre et mets-le à la suite. »

Le clic sur une ligne ne sélectionne plus rien pour une action « Remplacer ». `selectedId` est toujours nul.

## Bibliothèque

Titre « Bibliothèque ». À droite : « Entrée met à la suite. »

Champ « Titre, artiste… ». La touche `/` le focus, hors d’un champ déjà en cours d’édition. Échap, si le focus est dans le champ, vide la recherche et sort du champ.

Onglets : Tous, Musique, Jingles, Archives. Pubs, Habillage et Émissions existent dans le catalogue mais ne sont pas sur cette page.

- Tous : pas de filtre.
- Musique : `grouping=rotation`.
- Jingles : `kind=jingle`.
- Archives : `grouping=ntf1,ntf2,ntf3` (le catalogue traite ça comme une seule égalité ; une liste à virgules peut ne pas faire un OU).

Sans texte, s’il y a un historique local : bloc « Récents » (mémoire du navigateur, pas du moteur).

Chaque résultat : point de genre, titre, artiste, durée, deux boutons.

| Bouton | Effet |
|---|---|
| Jouer maintenant | Coupe et envoie le titre (`now.json`). Désactivé en direct, titre « Direct à l’antenne ». Double-clic sur la ligne fait la même chose. |
| À la suite | Ajoute dans la file, sans couper. Entrée fait ça sur la ligne active. |

Flèches haut / bas changent la ligne active **seulement** quand le focus est dans la recherche.

Toast succès : « Mis à la suite. » ou « À l’antenne — coupe. » En démo sans Liquidsoap : « Envoyé (démo horloge — pas de Liquidsoap). » Si on insiste en direct : « Direct à l’antenne. »

Vide ou filtre sans hit : « Aucun titre. » Sinon « N résultat(s) ». Erreur réseau : le message du catalogue, en rouge (« Catalogue injoignable. » si le fetch échoue).

On peut glisser un résultat. Le dépôt utile est un ident en mode Régler. Le dépôt sur la file ne remplace pas une ligne : le drop bibliothèque sur la file est ignoré.

## Idents

Titre « Idents ». Bouton « Régler » (`aria-pressed`). Une seule rangée de 6 cases.

Le cart lu est celui dont le drapeau `ident_pads` est vrai. S’il n’y en a aucun, repli sur un cart encore nommé « Jingles ». Un seul cart peut porter le drapeau (posé dans Sons). Les cases vides affichent « — », ou « Vide » + « drop » en mode Régler.

Clic ou touches 1 à 6 : joue ce son tout de suite. En direct, les boutons sont désactivés, le titre dit « Direct à l’antenne », et 1–6 ne font rien. Maj+1 à Maj+6 ne font rien non plus.

La case du son réellement à l’antenne prend `is-onair`. Juste après un clic, `is-fired` le temps du retour.

Mode Régler :

- on peut glisser un titre de la bibliothèque sur une case ;
- on peut échanger deux cases, ou déplacer un son vers une case vide ;
- une croix retire le son de la case. Le fichier reste dans le cart. Toast : « Pad vidé — le son reste dans le cart. »
- s’il n’y a pas de cart d’idents : « Coche « Pads d’idents » sur un cart, dans Sons. »

Hors Régler, une case vide est inactive (« Slot vide »).

## Clavier

Ignoré si Ctrl, Cmd ou Alt sont tenus, ou si le focus est dans un champ (sauf `/` et Entrée dans la recherche, décrits plus haut).

| Touche | Effet |
|---|---|
| Espace | Passer, sauf offline ou direct |
| 1 à 6 | Ident de cette case, sauf en direct |
| / | Focus recherche |
| Entrée | Met la ligne active à la suite |
| Échap dans la recherche | Vide et sort |
| Flèches dans la recherche | Ligne active |

Il n’y a pas de raccourci pour « Jouer maintenant », ni pour nommer le live, ni pour Régler.

## Ce que la page ne fait pas

- Pas de bouton « passer en direct ». Le direct vient de l’encodeur.
- Pas de coupure spéciale au retour d’antenne. Couper l’encodeur est le geste. Le moteur vide les files et saute le titre d’auto-DJ. La carte le dit, elle ne le déclenche pas.
- Pas de dépannage, pas de pastilles de santé, pas de bandeau d’incident séparé, pas de journal « passé », pas de « Remplacer ».
- Pas de rangée Pubs.
- Le choix d’écoute de la barre ne pilote pas le flux public.

## Rôles

Tout le monde qui a la session voit cette page. Le menu cache Programmation et Sons à l’animateur, et Comptes / Automate aux non-admins, mais Antenne ne change pas.

En direct, Jouer maintenant, Passer et les idents sont coupés pour tout le monde, y compris l’admin. Réparer l’antenne se fait dans Réglages → Automate.

## Thème, mobile, clavier, focus

Thème clair et sombre, hérités de la coque.

Cibles tactiles des actions de bibliothèque et du bouton Passer : au moins 40 px de haut. Les cases d’idents sont plus basses que ça : six colonnes sur une ligne, y compris à 390 px.

Focus visible sur les liens et boutons de la coque, et sur les cases d’idents. La page est utilisable sans souris pour chercher, mettre à la suite, passer et lancer un ident. Régler les pads, nommer le live et lire la fiche encodeur demandent la souris ou le toucher.

## Tensions utiles pour une refonte

Ce ne sont pas des décisions. Ce sont les frottements de l’écran actuel.

1. **Deux « direct ».** Le bandeau dit Direct quand le harbor est à l’antenne. Le panneau dit Branché / En attente / Absent. Le bouton Passer veut dire « couper ce titre ». Trois mots proches, trois gestes différents.
2. **Le panneau encodeur est toujours déplié.** Il prend plus de place que la carte maintenant. Sur téléphone, les idents et la file passent sous une fiche qu’on ne relit pas à chaque titre.
3. **La carte maintenant et le bandeau racontent presque la même chose** (ce qui joue, et si on est en direct), puis la file recommence avec le prochain.
4. **« Pupitre »** sur une ligne de file est un mot interne. La page s’appelle Antenne. Le badge veut dire « ajouté à la main, donc déplaçable ».
5. **Les idents dépendent d’un drapeau** posé dans Sons, avec un repli sur le titre Jingles. Si personne n’a coché le drapeau et que le cart a été renommé, la rangée est vide sans explication sur la page.
6. **Jouer maintenant et À la suite sont sur chaque ligne.** Sur 390 px, la grille titre + deux boutons est serrée. Le double-clic « jouer maintenant » n’a pas d’équivalent tactile évident à part le bouton.
7. **Entrée met à la suite, pas à l’antenne.** C’est voulu. Ce n’est pas dit ailleurs que dans le petit hint.
8. **Le silence et le problème sont un seul mot dans le bandeau**, sans la cause. La cause détaillée est dans Automate, pas sous les yeux de la personne qui est à l’antenne.
9. **Nommer ce live n’apparaît qu’une fois branché**, et disparaît dès qu’une émission courante existe. On ne corrige pas le nom depuis cette carte.
10. **La page défile**, alors que le pupitre était pensé pour tenir dans l’écran. Le panneau direct est la cause principale.
