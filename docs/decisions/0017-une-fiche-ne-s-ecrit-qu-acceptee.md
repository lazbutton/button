# 0017 · Une fiche se propose, et ne s'écrit qu'acceptée

Acceptée, novembre 2026.

## Contexte

Les fiches de la bibliothèque (FON-22 à FON-30) cherchent en ligne ce qui manque ou ce qui est mal écrit dans les tags d'un titre : titre, artiste, album, année, label, ISRC, une famille de genre, et un verdict « femme ou minorité de genre ». Les sources se trompent souvent. Sur un échantillon de 40 titres d'une radio, l'année des plateformes était celle d'une réédition ou d'une compilation pour un titre sur trois. Sur 77 titres qui avaient déjà un code de genre de la radio, la famille trouvée ne retombait sur ce code qu'une fois sur trois. Un champ faux est pire qu'un champ vide.

Or ces champs servent. L'antenne annonce l'artiste et le titre lus dans Beets : le scheduler les envoie au playout avec le fichier. Une catégorie est une requête Beets, comme `genre:Jazz`. La recherche de la console lit les tags des fichiers. Les relevés SACEM et SPRE les déclareront (FON-01). Une valeur écrite d'office changerait l'antenne sans que personne l'ait vue.

## Décision

- **Une proposition vit dans la base du moteur**, dans des tables à elle : la valeur trouvée, celle qu'elle remplacerait, son niveau (`sûr`, `à revoir`, `rapproché`), pourquoi, d'où elle vient, et ce que l'équipe en a décidé. Jamais dans les tags d'un fichier, ni dans un champ de Beets.
- **Seule une proposition acceptée s'écrit.** Une personne l'accepte dans la page « À relire » de la console, ou l'a déjà acceptée pour le même son, revenu sous un autre chemin.
  - Titre, artiste, album, année, label et ISRC s'écrivent dans Beets et dans les tags du fichier, comme le ferait `beet modify` : la bibliothèque, la recherche de la console et le fichier disent la même chose, et un fichier réindexé garde la correction.
  - La famille de genre et le verdict s'écrivent dans des champs flexibles de Beets, `famille`, `fmg` et `fmg_source`, que Beets ne met jamais dans le fichier.
- **Le champ `genre` ne s'écrit jamais**, même accepté. Les catégories en dépendent, et la boucle d'import le pose elle-même sur les archives. La famille est un champ à part, qu'une catégorie peut lire : `famille:jazz`.
- **Le verdict « femme ou minorité de genre » ne se calcule que si la station l'a allumé** (`features.fiches_fmg`, éteint par défaut). Il ne vient que de ce que MusicBrainz et Wikidata déclarent, jamais d'un prénom, d'une voix ou d'une photo. BUTTON ne garde que le verdict et sa source, pas le genre de chaque personne.
- **Une seule tâche de fond cherche**, dans le scheduler, comme l'analyse ReplayGain : un titre à la fois, sous les limites de chaque service. Rien ne se cherche pendant l'import. `features.fiches`, éteint par défaut, coupe toute la fonction ([ADR 0009](0009-interrupteurs.md)).
- **Les règles sont celles qui ont été mesurées** sur un catalogue réel, par l'outil de catalogue de Hopper, un projet à part. BUTTON les réécrit en Python avec leurs cas de test, et ne dépend pas de Hopper.

## Conséquences

- Une migration ajoute les tables des fiches, sauvegardées avec la base du moteur. Les champs flexibles sont dans la bibliothèque de Beets, que `backup-radiotomate.sh` copie déjà.
- Accepter réécrit les tags d'un fichier. Jamais pendant qu'il est à l'antenne ou en file : l'écriture attend. Un fichier que le moteur ne peut pas écrire est signalé dans la page, et une valeur écrite peut revenir à celle d'avant.
- Une valeur changée ailleurs depuis la proposition la rend périmée : elle ne s'accepte plus, et le titre est recherché de nouveau.
- Un fichier déplacé revient dans Beets sous un nouvel identifiant. Ses propositions se refont d'après ce qui a déjà été trouvé, sans réseau, et les décisions déjà prises pour ce son s'y appliquent de nouveau, sans redemander.
- Une station peut écrire une catégorie sur `famille:` ou sur `fmg:oui`. Effacer les verdicts vide une telle catégorie : la console le dit avant.
- Le moteur parle à MusicBrainz, AcoustID, Deezer et Wikidata, sous le nom de BUTTON, jamais sous celui de la station. Une station qui ne le veut pas laisse `features.fiches` éteint.
- Les fiches de la feuille de route : FON-22 à FON-30, dans [P2](../feuille-de-route/P2.md). À partir de FON-25, elles attendent la montée de Beets en 2.14 (ARC-06).
