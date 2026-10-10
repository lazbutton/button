# Sons — UI et fonctionnement actuel

28 septembre 2026. Description de la page telle qu’elle est dans `ntr-console`. Ce n’est pas une maquette cible. C’est le matériau pour une refonte : ce que la page fait, ce qu’elle affiche, ce qu’elle ne doit pas casser.

La page est `/sons`. Le menu ne la montre qu’au programmateur et à l’admin. Un animateur qui force l’adresse voit « Accès réservé » et un retour vers l’antenne. Programmateur et admin voient le même écran.

La page ne décide pas de l’ordre des sources. Elle range les fichiers et les relais. La priorité reste : direct (harbor), puis relais, puis carts, puis jingles, puis rotation. L’onglet Relais le rappelle dans sa phrase d’introduction. Le flux public (`button.mp3`) n’est pas remplacé ici.

## Autour de la page

- Menu : Antenne, Conducteur, Programmation, Sons, Réglages. Sur un écran étroit, le menu devient un bouton « Ouvrir la navigation ».
- La zone de page porte la classe `app-page--carts`. Elle prend toute la largeur de la colonne principale.
- Thème clair ou sombre, lien « Code source », Déconnexion.
- L’écoute de la barre du haut est le flux ou une autre source de monitoring. L’aperçu d’un son, dans le tableau, est une lecture locale du fichier. Ce n’est pas l’antenne.

## Mise en page

Une colonne. Titre de section, puis quatre onglets. L’onglet actif est dans l’adresse.

```
┌ Sons                                                                ┐
│  Carts, habillage, relais et import.                                │
│  [ Carts ]  Habillage   Relais   Importer                           │
├─────────────────────────────────────────────────────────────────────┤
│  (l’onglet, avec un second titre sur les trois premiers)            │
└─────────────────────────────────────────────────────────────────────┘
```

| Onglet | Adresse | Ce qu’il liste |
|---|---|---|
| Carts | `/sons` | Tous les carts dont le mode n’est pas `relay`, y compris l’habillage |
| Habillage | `/sons?onglet=habillage` | Carts dont `bank_folder` commence par `30-habillage` |
| Relais | `/sons?onglet=relais` | Carts dont `mode` est `relay` |
| Importer | `/sons?onglet=importer` | Pas une liste de carts. Dépôt web vers la banque |

L’onglet par défaut n’écrit pas `onglet`. Un `onglet` inconnu retombe sur Carts. Changer d’onglet remplace l’adresse, sans empiler l’historique. L’onglet inactif n’est pas monté : la recherche, la sélection de pistes et un formulaire non enregistré sont perdus.

`?id=` sélectionne un cart s’il appartient à la liste de l’onglet. Les liens depuis Programmation (`/sons?id={id}`) arrivent ainsi. Si l’id n’est pas dans la liste filtrée, le premier cart de l’onglet est montré, et l’adresse peut encore porter l’ancien id tant qu’on n’a pas cliqué une carte.

Un même cart d’habillage apparaît dans Carts et dans Habillage. Un relais n’apparaît que dans Relais, sauf si son dossier banque commence par `30-habillage` : il serait alors aussi dans Habillage.

## Chargement et pannes

| Situation | Ce que la personne voit |
|---|---|
| Session expirée | Écran de connexion |
| Rôle insuffisant | « Accès réservé » |
| `/carts.json` pas encore arrivé (Carts, Habillage, Relais) | « Chargement… » à la place du contenu de l’onglet |
| `/carts.json` injoignable, sans cache | « Radiotomate est indisponible », bouton Réessayer |
| Horloges absentes alors que les carts sont là | L’onglet s’affiche. Sous chaque cart : « pas dans l’Auto-DJ » |
| Importer, catalogue en 401 | « Session expirée — reconnecte-toi. » L’envoi Uppy reste affiché |
| Importer, catalogue muet | « Le dépôt ne répond pas. Réessaie. S’il reste muet, un admin vérifie le catalogue. » |
| Banque injoignable dans le dialogue d’attache | « La banque ne répond pas. Réessaie, ou dépose le fichier dans le cart. » |
| Banque non montée | « La banque n’est pas montée sur cet automate (MEDIA_ROOT). » |

Toasts d’échec :

- Création, enregistrement, suppression, import, attache : message du moteur, ou « Création impossible. », « Enregistrement impossible. », « Suppression impossible. », « Import impossible. », « Attache impossible. »
- Droit manquant sur un cart : « Il faut le rôle Programmateur pour modifier les carts. »
- Droit manquant pour diffuser un son : « Droit Antenne requis. » ou « Droit insuffisant. »
- Diffusion du cart entier : « Diffusion impossible. »
- Fichier refusé à l’import : « Aucun fichier audio. »
- Titre d’un son : « Titre impossible. » Réordre : « Rang impossible. » Case On : « MAJ impossible. » Aperçu : « Lecture impossible. »

Succès : « Cart créé », « Cart enregistré », « Cart supprimé », « 1 son importé » ou « N sons importés », « 1 son attaché depuis la banque » ou « N sons attachés depuis la banque », « Cart envoyé à l’antenne ». Diffuser une piste depuis le tableau ne montre pas de toast si ça réussit.

## Les trois onglets de carts

Carts, Habillage et Relais sont le même écran, avec un filtre et des textes différents. Trois colonnes au-dessus de 1260 px :

```
┌ liste des carts     ┬ tableau des sons              ┬ inspecteur ┐
│  recherche, Nouveau │  déposer, ajouter, banque     │  nom, mode │
│  usage Auto-DJ      │  préécoute en bas             │  Maintenant│
└─────────────────────┴───────────────────────────────┴────────────┘
```

Sous 1260 px, l’inspecteur passe sous les deux colonnes, sur toute la largeur, et la page défile. Sous 720 px, liste, tableau et inspecteur s’empilent. La liste est plafonnée à 25 rem.

Sans aucun cart dans le filtre : la liste reste (avec Nouveau), et une carte vide à la place du tableau et de l’inspecteur.

| Onglet | Titre | Phrase | Carte vide |
|---|---|---|---|
| Carts | Carts | « Importe tes fichiers ici. Pour les faire tourner tout seuls : Programmation. » | « Premier cart » — créer, glisser, accrocher dans Programmation |
| Habillage | Habillage | « Carts dont le dossier banque est dans 30-habillage. » | « Aucun habillage » — créer ici, ou choisir un dossier 30-habillage dans l’inspecteur |
| Relais | Relais | Priorité des sources, et « Le flux sortant reste le MP3 public. » | « Aucun relais » — adresse du flux et durée max |

À droite du titre : deux badges, « N carts » et « N sons » (somme des pistes des carts visibles).

### Liste

Titre de colonne = celui de l’onglet. Phrase sous le titre :

- Carts : « Les fichiers. La rotation se règle dans Programmation. »
- Habillage : « Jingles, ids, beds. Coche « Pads d’idents » pour la rangée de l’antenne. »
- Relais : « URL HTTP et durée max, obligatoire. »

Recherche « Rechercher un cart… », sur le titre seulement. Vide avec une recherche : « Aucun résultat » / « Essaie un autre nom. » Vide sans recherche : « Aucun cart » / « Crée un cart, puis importe les fichiers. »

Chaque carte : icône de mode, titre, « N sons », usage dans les horloges, libellé de mode à droite. L’usage vient de `/autodj/clocks.json` : « Dans Auto-DJ · Jingle · Programme · … » ou « pas dans l’Auto-DJ » (en gris plus marqué). Les rôles sont ceux du motif, des ancres, ou « secours ».

Glisser des fichiers audio sur une carte importe dans ce cart. Le survol dit « Relâchez pour importer ici ». Pendant l’import : « Lecture des fichiers… » puis « Import N / M ». Un import en cours bloque un second dépôt.

Cliquer une carte met `id` dans l’adresse.

### Nouveau cart

Dialogue « Nouveau cart ». « Un nom, et comment ça se lit. » Titre, exemple « Jingles ».

| Onglet | Modes proposés | Défaut |
|---|---|---|
| Carts, Habillage | Boucle, Aléatoire | Boucle (`playlist_loop`) |
| Relais | Relais seulement | Relais |

Le mode « Une fois » (`playlist`) n’est pas dans ce dialogue. Il est dans l’inspecteur, sur un cart déjà créé.

Aides de mode :

- Boucle : reprend au début après le dernier son.
- Aléatoire : tire un son au hasard parmi les pistes actives analysées.
- Une fois : joue les sons dans l’ordre, une fois.
- Relais : flux Icecast externe, durée max obligatoire.

En relais, deux champs de plus : « URL du flux » (HTTP ou HTTPS, avec un chemin) et « Durée max (secondes) », défaut 1800. Le bouton « Créer le cart » reste inactif si l’URL n’a pas de chemin, ou si la durée n’est pas un nombre > 0. Exemple d’URL : `https://radio.exemple/flux.mp3`.

Création : `POST /carts.json` avec `title`, `mode`, `schedule_mode: "clock"`. Depuis Habillage, `bank_folder` est forcé à `30-habillage/jingles`. En relais, `url` et `max_duration` sont envoyés. Il n’y a pas d’écran pour les autres `schedule_mode` (`timed`, `jingles`) ni pour une formule cron.

### Tableau des sons

En-tête : nom du cart, nombre de sons. Actions : « Ajouter » (fichiers), icône dossier (« Importer un dossier »), icône disque (« Attacher depuis la banque »).

Sous l’en-tête : le mode, puis la durée totale (`hh:mm:ss` si elle est connue), la moyenne (« moy. mm:ss »), et `schedule_summary` s’il est rempli. Avec un filtre de titres, ces durées cèdent la place à « N résultats ».

Ligne « Suivant » si `next_sound_id` pointe un son : titre et artiste lus dans la chaîne du titre (coupure sur ` - `).

Filtre « Filtrer les titres… ». À côté, « Déposez les fichiers ici », ou l’état d’import. Déposer sur le tableau ouvre le même import, avec un voile « Importer dans « {titre} » ».

Sélection : case à cocher, Maj+clic pour une plage, case d’en-tête pour tout le filtre. Barre « N pistes sélectionnées », « Effacer », « Supprimer ». Confirmation : les fichiers quittent le cart, sans annulation. L’envoi est `POST /carts/{id}/sounds/delete.json` avec `{ids}`.

Colonnes : case, rang (sauf en mode Aléatoire), aperçu, titre, durée, On, actions.

- Le rang est une poignée. Glisser réordonne. `PUT /carts/{id}/sounds/ranks.json` avec `{ranks: [ids]}`. En Aléatoire il n’y a pas de rang : l’ordre ne se règle pas.
- L’aperçu joue le fichier dans le navigateur (`GET` binaire `/carts/{id}/sounds/{id}`). Recliquer arrête. La fin de piste enchaîne le suivant de la liste visible, ou de tout le cart si le filtre est vide. La barre du bas reprend lecture, titre, temps, et un clic pour chercher dans le fichier. Ce son ne part pas à l’antenne.
- Le titre affiché sépare artiste et morceau sur ` - `. Cliquer le titre édite la chaîne brute. Entrée enregistre, Échap annule. `PUT /carts/{id}/sounds/{id}.json` avec `{title}`.
- Badges sur la ligne : « Aperçu », « Suivant », « Analyse » tant que `gain` est vide, « Inactif » si `available` est faux (fichier absent), une fois l’analyse finie. Une piste `active` fausse ou indisponible est grisée.
- Colonne On : `active`, écrit tout de suite avec le même `PUT`. Ce n’est pas le badge Inactif. On retire la piste du tirage sans effacer le fichier.
- Tour radio : `POST /carts/{id}/sounds/{id}/now.json`. Coupe et envoie ce son. Pas de toast de succès.
- Corbeille : confirmation, puis `DELETE /carts/{id}/sounds/{id}.json`.

Cart vide : « Ce cart est vide », « Déposez ici des fichiers ou un dossier audio, ou ouvrez le sélecteur de fichiers. », bouton « Ajouter des sons ».

Filtre sans résultat : « Aucun titre trouvé », « Effacer le filtre ».

Note sous le tableau : « Cliquez un titre pour le renommer · glissez le numéro pour réordonner · la préécoute enchaîne les pistes. » La mention du glisser disparaît en mode Aléatoire.

Formats acceptés par le sélecteur et le dépôt : audio, et les extensions mp3, wav, flac, ogg, opus, m4a, aac, aiff. L’envoi vers le moteur est `POST /carts/{id}/sounds.json?delta=1`, par paquets, trois en parallèle.

### Attacher depuis la banque

Dialogue « Attacher depuis la banque ». Phrase : « Habillage et émissions seulement. Les fichiers restent sur Nasgul. La rotation Auto-DJ, c’est le cart Prog accroché à l’horloge. »

Liste `GET /media/bank.json`. Filtre « Filtrer un dossier… jingles, pubs, hph… ». Chaque dossier affiche son chemin et « N sons ». Plusieurs dossiers. « Attacher N sons » envoie `POST /carts/{id}/sounds.json?delta=1` avec `{folders}`. Les fichiers ne sont pas copiés dans le navigateur.

### Inspecteur

Titre = nom du cart. Phrase : « Fichiers et lecture. Pour le mettre dans la rotation : Programmation. » Bouton « Maintenant » : `POST /carts/{id}/now.json`, toast « Cart envoyé à l’antenne ». C’est le cart entier, pas la piste surlignée.

Champs, enregistrés ensemble au bouton « Enregistrer » (`PUT /carts/{id}.json`) :

| Champ | JSON |
|---|---|
| Nom | `title` |
| Notes | `notes` |
| Dossier banque | `bank_folder` (chaîne vide = « Auto — dossier du cart ») |
| Lecture | `mode` : `playlist_loop`, `random`, `playlist`, `relay` |
| URL du flux | `url`, seulement en relais |
| Durée max (secondes) | `max_duration`, seulement en relais |
| Pads d’idents | `ident_pads`. Forcé à faux si le mode devient relais |

Le dossier banque liste d’abord des chemins fixes (`30-habillage/jingles`, `ids`, `pubs`, `beds`, `stings`, `sfx`), puis ceux renvoyés par `/media/bank.json` si la banque répond. Le chemin déjà enregistré reste dans la liste même s’il n’est plus proposé.

Bloc Finder, au-dessus du dossier : une adresse `smb://` Tailscale (`Carts/{id}-{slug}` dans le partage de la marque) et, si elle diffère, l’adresse du studio (`192.168.1.100` par défaut). « Ouvrir dans le Finder » ouvre l’adresse Tailscale. « Copier » met cette adresse dans le presse-papiers et le bouton dit « Copié » une seconde et demie. L’aide : glisser un fichier dans ce dossier le fait arriver dans le cart ; compte SMB `laz` ; hors studio, l’adresse Tailscale. Ce bloc n’écrit rien au moteur. Le chemin est calculé dans la page.

« Pads d’idents » n’est pas affiché en mode relais. Le texte : « La rangée Idents de l’antenne lit ce cart. Un seul cart à la fois. » La page envoie le drapeau du cart enregistré. Elle ne décoche pas les autres carts elle-même. Tant qu’aucun cart n’a le drapeau, l’antenne retombe sur un cart encore nommé Jingles.

Statut « Non enregistré » ou « À jour ». « Annuler » revient au cart chargé, seulement s’il y a des changements. « Enregistrer » est inactif sans changement, sans nom, ou si le relais n’a pas une URL avec chemin et une durée > 0. « Supprimer » confirme « Le cart et son contenu seront supprimés. » puis `DELETE /carts/{id}.json`.

## Onglet Importer

Pas de second titre, pas de liste de carts. C’est le dépôt web, à part des imports « Ajouter » des autres onglets.

Ceux-là posent des fichiers dans un cart déjà créé. Celui-ci envoie des fichiers dans la banque, pour que Beets les indexe. La rotation et les archives n’en font pas tout de suite des sons de cart.

Champ « Destination » :

| Valeur | Libellé |
|---|---|
| `rotation` | Rotation |
| `ntf1` | Archive NTF 1 |
| `ntf2` | Archive NTF 2 |
| `ntf3` | Archive NTF 3 |

Aide : « MP3, FLAC, OGG, Opus, M4A, WAV ou AIFF. Un envoi coupé reprend. Beets indexe ensuite. » Le tableau de bord Uppy (français, hauteur 320 px, thème clair ou sombre) dit « Glisse les fichiers. L’envoi reprend tout seul. » Pas de mention « Powered by Uppy ».

L’envoi est tus vers `/tus/`, morceaux de 8 Mo, reprises à 0 s, 1 s, 3 s, 5 s, 10 s. Le meta `destination` suit le menu. Changer de destination pendant qu’un fichier est déjà dans Uppy met à jour ce meta.

Jauge « Quota de la station », lue dans `GET /library/inbox.json` toutes les 5 s : « N utilisés sur M », ou « Quota… » tant que la première réponse n’est pas là. La jauge est un `meter`.

Trois listes, avec un compteur :

- En cours. Vide : « Aucun envoi en cours. » Une ligne peut montrer le pourcentage (`offset` / `bytes`).
- File d’attente. Vide : « Rien en attente de promotion. »
- Rejets. Vide : « Aucun rejet. » La raison est en gras sous le nom.

Chaque ligne : nom, destination (Rotation, NTF 1, NTF 2, NTF 3, ou la valeur brute), taille si elle est connue.

`/library/inbox.json` et `/tus/` sont le catalogue (`ntr-ops`), pas les routes `/carts.json` du moteur.

## Ce que la refonte doit pouvoir encore faire

- Lister, créer, renommer, supprimer un cart, avec `mode` parmi `playlist`, `playlist_loop`, `random`, `relay`.
- Importer des fichiers ou un dossier dans un cart, réordonner les pistes (sauf aléatoire), activer ou désactiver une piste, la renommer, la supprimer, l’écouter en local.
- Envoyer un son maintenant (`…/sounds/{id}/now.json`) ou le cart entier (`…/now.json`).
- Attacher des dossiers de la banque sans les recopier (`/media/bank.json`, `{folders}`).
- Régler un relais : URL HTTP avec un chemin, durée max obligatoire. Ne pas remplacer le mount public.
- Marquer un seul cart comme pads d’idents (`ident_pads`), et laisser le repli sur le cart nommé Jingles tant qu’aucun drapeau n’est posé.
- Voir si un cart est dans une horloge, et ouvrir ce cart depuis Programmation via `?id=`.
- Déposer vers la banque (rotation ou archives NTF 1 à 3) en envoi reprenable, avec quota, file, et rejets motivés.
- Rester réservé au programmateur et à l’admin.
