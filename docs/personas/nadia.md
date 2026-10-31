# Nadia · programmatrice

> « La radio doit sonner comme nous, même à 4 h du matin, quand personne n'est là. »

Persona principal. Dans la console : rôle **Programmateur**.

## Qui elle est

- **45 ans**, programmatrice musicale, salariée à mi-temps de l'association. Disquaire pendant quinze ans.
- **À la radio depuis huit ans.**
- **Son travail** : la grille, la rotation, l'habillage, les invités, les décrochages avec une radio amie.
- **Son matériel** : le PC du bureau, avec deux écrans. Chez elle, son Mac, et le dossier de la station dans le Finder.
- **À l'aise** avec la musique, les tags et les tableurs. **Pas à l'aise** avec les requêtes et les fichiers de configuration.
- **Son temps** : dix-sept heures et demie par semaine, et bien plus quand une saison commence.

Nadia écoute une cinquantaine d'albums par semaine, et en garde une dizaine. Elle pense l'antenne en heures : une heure de jour ne sonne pas comme une heure de nuit. Elle a construit les heures types de la radio, et elle est la seule à toutes les connaître.

## Ce qu'elle veut

- Une antenne qui tient seule, 24 h sur 24, et qui sonne comme la radio.
- Faire tourner les nouveautés sans entendre deux fois le même artiste dans l'heure.
- Déposer des fichiers, et qu'ils soient tagués, rangés et indexés sans elle.
- Ponctuer l'antenne : jingles, idents, pubs, à la bonne minute.
- Accueillir des invités et des relais sans reprendre toute la grille.
- Savoir ce qui manque avant que ça manque à l'antenne.

## Ce qui la freine

- Ne pas savoir, après coup, pourquoi un titre est passé, ou n'est pas passé.
- Les fichiers mal tagués et les formats refusés.
- Trois vues pour une seule grille : les heures types, la semaine, l'Agenda.
- Les mots en double. La console dit bac, heure type, sélection de titres et coupure ; le moteur et la documentation technique disent cart, horloge, catégorie et ancre.
- Les coupures à la minute : puissantes, mais une coupure « Coupe pile » mal placée tranche un titre en plein milieu.
- Les relevés de diffusion à préparer pour la SACEM et la SPRE.

## Son parcours

1. **Déposer.** Dans **Sons → Banque**, elle glisse les nouveautés. L'envoi reprend après une coupure, et la console montre l'avancement, le quota et les fichiers refusés avec leur raison. Chez elle, elle passe par le dossier de la station : [dossier-reseau.md](../exploitation/dossier-reseau.md).
2. **Choisir.** Dans **Programmation → Sélections de titres**, elle décrit ce qui passe : `genre:Jazz`, ou une banque d'archives par son regroupement, `grouping:<dossier>`.
3. **Composer.** Dans **Heures types**, elle enchaîne titres, jingles, programmes et pubs. Ses **Coupures à la minute** coupent pile, ou attendent la fin du titre.
4. **Poser la semaine.** Dans **Semaine**, chaque créneau reçoit son heure type, et chaque émission hebdomadaire ses heures et son animateur, comme Inès, choisi en **Compte du plateau**.
5. **Habiller.** Dans **Sons → Bacs**, elle crée un bac de jingles, un bac de pubs, ou un relais pour un décrochage, avec son adresse et sa durée max : [decrochage.md](../exploitation/decrochage.md).
6. **Inviter.** Dans **Programmation → Agenda**, elle pose le set de Lou. **Copier le message** donne le texte à lui envoyer : [inviter-un-dj.md](../exploitation/inviter-un-dj.md).
7. **Vérifier.** **À préparer** liste ce qui manque pour les sept prochains jours. Le **Conducteur** montre ce qui va passer : elle peut y réparer ou retirer une ligne.

## Le moment qui compte

Vendredi, 18 h. **À préparer** signale que le set de Lou, prévu samedi à 22 h, est déposé mais pas prêt : les droits ne sont pas cochés. Nadia écrit à Lou, qui coche la case dans l'heure.

Sans cela, le set n'aurait pas passé. Un set qui n'est pas prêt à son heure reste hors antenne : la grille joue à sa place, et une alerte part. L'antenne ne se tait pas, mais l'émission annoncée n'a pas lieu.

## Ce que BUTTON fait déjà pour elle

- Des règles de séparation des artistes et des titres, et un volume égalisé (ReplayGain).
- La dropbox range les fichiers, pose les tags d'après le nom du fichier et garde l'original. Un wav ou un aiff devient un flac : [deposer-un-programme.md](../exploitation/deposer-un-programme.md).
- Des bacs en quatre modes : une fois, en boucle, au hasard, ou en relais.
- Un set daté passe à son heure, en entier, sans que les jingles et les pubs de l'heure type s'empilent derrière lui.
- La pré-écoute d'un son, avant de le mettre à l'antenne.
- L'espace disque de la banque, toujours visible dans la navigation.
- Elle nomme elle-même l'animateur d'une émission ou d'un direct daté. La liste ne montre que les comptes qui peuvent passer en direct, sans le reste de leur fiche.

## Ce qui coince encore

- **Pourquoi ce titre ?** L'historique de ce qui est passé, quand et d'où : UX-02.
- **Une seule vue** pour les heures types, les créneaux et l'Agenda : UX-03.
- **Des playlists choisies à la main**, à côté des sélections : UX-04. **Une page par émission** : UX-05.
- **Les relevés SACEM et SPRE**, tirés du journal d'antenne, avec les métadonnées manquantes signalées dès l'import : FON-01, en [P2](../feuille-de-route/P2.md).
- **Les heures types, la semaine, les sélections et l'Agenda attendent leurs parcours dans un navigateur** : TST-04, en P2. Une régression y passe plus facilement qu'au pupitre.

Les fiches UX sont en [P3](../feuille-de-route/P3.md).

## Concevoir pour elle

- La densité est permise : elle travaille longtemps, sur un grand écran.
- Montrer la conséquence avant d'enregistrer, comme le fait l'aperçu d'une série dans l'Agenda.
- Les mots de la console d'abord. Ceux du moteur, seulement en aide.
- Une erreur de programmation ne fait jamais taire l'antenne.
