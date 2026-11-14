# 0020 · La banque se range par ses fiches

Acceptée, novembre 2026.

## Contexte

La banque se range aujourd'hui par ses dossiers : la rotation, les collections, l'habillage. La console montre une collection à la fois, lue sur le disque, et n'y sait que retirer ou déplacer un fichier. Rien ne corrige le titre ou l'artiste d'un fichier, rien ne renomme un fichier. Un fichier déplacé revient dans la bibliothèque de Beets comme un titre nouveau : il perd son identifiant, son volume analysé et ses champs flexibles, et une diffusion de l'Agenda qui le jouait ne le trouve plus. La boucle d'import écrit `genre=Archive` dans chaque titre d'une collection, à la place du genre du fichier : ranger une collection par genre n'a pas de sens.

Le 14 novembre 2026, l'utilisateur a demandé de pouvoir trier et ranger la banque et les bacs par genre et par artiste, renommer leurs fichiers, et vraiment se servir de ce que Hopper apporte. Il a tranché 31 choix dans une page faite pour cela : les parcours, les fonctions, les règles et la livraison. Les fiches qui en découlent sont dans la section « Ranger la banque » de [P2](../feuille-de-route/P2.md).

## Décision

- **Ranger, c'est regarder.** Le tableau de la banque se range par collection, artiste, famille ou album, et se filtre par ses colonnes et par les étiquettes de la station. Un fichier ne bouge que par un geste nommé : le déplacer vers une collection, le renommer. Un sous-dossier par artiste n'est qu'une option du renommage, pour qui passe par le dossier de la station.
- **Deux gestes.** Corriger la fiche d'un titre change ce que l'antenne annonce : ses tags, dans le fichier et dans la bibliothèque. Renommer le fichier change ce que montre le dossier de la station. Le nom suit la fiche d'un clic, jamais de lui-même.
- **Un titre garde son identité.** Renommé ou déplacé par BUTTON, un titre garde son identifiant dans Beets, son volume analysé, ses champs flexibles, et sa place dans les bacs et dans l'Agenda.
- **Le genre.** La famille, l'une des quatorze de `engine/radiotomate/fiches/rules.py`, range la banque. Le genre écrit dans le fichier se montre en colonne. Une personne peut le corriger ; une proposition, jamais : l'[ADR 0017](0017-une-fiche-ne-s-ecrit-qu-acceptee.md) tient. Avant d'écrire un genre, la console nomme les sélections de titres qui gagnent ou perdent ces titres. La boucle d'import n'écrit plus `genre=Archive`.
- **Toujours une personne.** Rien ne s'écrit d'office, même une proposition sûre : les sûres s'acceptent par lot, comme le dit l'ADR 0017.
- **Un journal.** Chaque geste sur la banque et les bacs se note : qui, quand, quoi, et la valeur d'avant. Il s'annule pendant 30 jours.
- **Les droits.** Le Programmateur corrige, renomme et range, un titre ou un lot. Créer, renommer et supprimer une collection restent à l'Admin, comme aujourd'hui.
- **Hopper.** La recherche des fiches reste dans BUTTON, comme décidé le 10 novembre 2026 : une station cherche sans dépendre d'un autre service. Hopper ne sert qu'aux liens d'écoute du titre en cours, « Retrouver ce titre », qu'une station allume si elle le veut.

## Conséquences

- La bibliothèque de Beets devient la source du tableau : elle a l'album, le genre, l'année et les champs flexibles, que l'index de Meilisearch n'a pas. Meilisearch reste la recherche de la page Antenne.
- Déplacer et renommer passent par le moteur, qui tient Beets et la base. Il réécrit les chemins qu'il garde, comme `sounds.path`, `agenda_files.path` et les lignes prévues du conducteur, sans réimport.
- Une écriture dans un fichier attend que le titre ne soit ni à l'antenne ni en file. Chaque geste qui écrit dans un fichier passe d'abord sur un banc fait d'une copie de vraie banque.
- Une sélection de titres qui lit `genre:Archive` ne prend plus les titres arrivés après le changement : elle se réécrit en `grouping:<dossier>`.
- La console gagne des vues dans Sons → Banque (Arrivées, À relire, Santé) et un onglet Journal dans Sons.
- Les fiches : TST-16, ARC-09 et FON-64 à FON-85, dans [P2](../feuille-de-route/P2.md). ARC-06, ARC-08, FON-26, FON-27, FON-28 et SEC-10 changent, comme UX-02 et UX-04 en [P3](../feuille-de-route/P3.md).
