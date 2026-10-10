# Prompts Cursor (Grok 4.7) — refonte de la page Programmation

**Fichier à poser dans le repo** : `docs/refonte/PROGRAMMATION.md` (les prompts le référencent avec `@PROGRAMMATION.md`).

**Méthode** : modèle Grok 4.7 en mode Agent. **Un lot = une branche git = une session neuve.** Chaque prompt suit la boucle *lis → propose un plan → j'valide → code → coche*. Relis les diffs, teste sur `:5175`, commit par lot. La page Programmation existe déjà (quatre onglets) : **garde-la fonctionnelle pendant la refonte, ne perds aucune capacité** de la checklist « Tout ce que la page doit encore savoir faire ».

> Rappel API réelle (l'inventaire fait foi) : `day_of_week` 0 = lundi ; heures en minutes depuis minuit (`start_minute`, `end_minute`, `minute`) ; émission `title` / `artist` / `host_username` / `scope` ; un `PUT` d'horloge retire les étapes `kind: musique` (`withoutLibrarySteps`) ; mutations avec `X-CSRF-Token`. **Ne « corrige » pas le code qui marche pour coller au vocabulaire du plan** : le vocabulaire est un affichage, pas un renommage d'API.

---

## Prompt d'amorçage (sans coder)

```
Lis @PROGRAMMATION.md en entier, puis explore la page /programmation dans ntr-console : ProgrammationPage et ses onglets (Rotation, Horloges/Atelier, Semaine, Catégories), et les endpoints /autodj/clocks, /autodj/slots, /autodj/categories, /antenne/emissions.
Ne code rien. Réponds : 1) les composants et fichiers de chaque onglet ; 2) où sont écrites les chaînes de texte (pour le vocabulaire) ; 3) les écarts entre le code actuel et la cible de @PROGRAMMATION.md (fusion Rotation+Horloges, auto-save, Semaine simplifiée, catégories en avancé). Signale tout endpoint dont la forme diffère.
```

---

## P1 — Vocabulaire et voix *(sûr, à faire en premier)*

```
@PROGRAMMATION.md P1 : le vocabulaire et la voix. Uniquement de l'affichage, aucune logique ni endpoint touché.
Lis où sont les chaînes de la page, propose la liste des libellés à changer, attends validation.
Applique la table de vocabulaire : motif → « ce qui passe, dans l'ordre », position → « étape », ancre → « coupure à la minute », dure/molle → « coupe à l'heure pile » / « attend la fin du titre », départ → « changement d'horloge », cart de secours → « si un bac est vide, jouer… », catégorie Beets → « sélection de titres ». Passe tout l'onglet Catégories au tutoiement, comme le reste.
Ne renomme rien côté API (les clés JSON ne bougent pas). Coche : plus aucun de ces mots internes à l'écran, une seule voix.
```

## P2 — Éditeur d'heure type *(fusion Rotation + Horloges, le gros du lot)*

```
@PROGRAMMATION.md P2 : fusionne les onglets Rotation et Horloges en un seul éditeur (voir la maquette).
Lis les deux onglets et leur écriture (PUT /autodj/clocks/{id}.json), propose le plan des fichiers, attends validation.
Construis l'éditeur : à gauche la liste des heures types (celle à l'antenne marquée, + Nouveau) ; à droite trois blocs — « ce qui passe, dans l'ordre » (étapes, ajouter/réordonner/retirer, cart par étape), « coupures pub » (cases :20 et :40 + cart, comme l'actuel Rotation), « si un bac est vide » (cart de secours). Mets le réglet 0–60, les autres minutes et le choix dur/mou dans un repli « avancé ».
Passe tout en auto-save avec un indicateur « Enregistré » ; supprime le bouton Enregistrer séparé et la perte de saisie au changement d'onglet. Retire l'onglet Rotation (son adresse redirige vers Horloges le temps de la bascule, puis disparaît).
Ne casse pas le PUT ni withoutLibrarySteps. Garde toutes les capacités de la checklist. Coche les critères.
```

## P3 — Semaine simplifiée

```
@PROGRAMMATION.md P3 : simplifie l'onglet Semaine (« à telle heure, telle horloge »).
Lis l'onglet Semaine et l'API des slots (/autodj/slots) et des émissions, propose le plan, attends validation.
Rends le modèle lisible : la journée commence toujours avec une horloge ; deux plages identiques consécutives fusionnent automatiquement (retire le bouton « Nettoyer N départs » et la fusion à la main). Deux boutons par jour : « + changement d'horloge » (heure pleine, horloge) et « + émission en direct » (title, artist, host_username, day_of_week, start_minute, end_minute). Garde l'interdiction d'effacer le changement de minuit, et affiche le refus du moteur si deux émissions se chevauchent.
Ne change pas les endpoints slots/emissions ni les champs (minutes depuis minuit, day_of_week 0 = lundi). Coche les critères.
```

## P4 — Catégories en avancé + réparer un cart manquant

```
@PROGRAMMATION.md P4 : mets les Catégories en secondaire et branche la réparation d'un cart manquant.
Lis l'onglet Catégories et le dialogue « réparer un cart manquant » (présent dans le code, sans bouton). Propose le plan, attends validation.
Place Catégories en onglet avancé (secondaire), garde son CRUD et le test de requête (/autodj/testquery.json). Ajoute un vrai bouton « Réparer » là où un cart manquant apparaît (dans l'éditeur d'heure type), qui ouvre le dialogue existant.
Coche : les catégories restent complètes mais discrètes ; un cart manquant se répare en un clic.
```

---

## Optionnel — recette

```
Sans coder : passe la page /programmation refondue contre la checklist « Tout ce que la page doit encore savoir faire » de @PROGRAMMATION.md, et coche chaque ligne avec le fichier/écran concerné. Signale toute capacité perdue. C'est un audit.
```

## Rappels

- Un lot après l'autre : P1 (sûr), puis P2 (le gros), puis P3, puis P4.
- Garde l'ancien onglet derrière sa route tant que le nouveau ne passe pas ses critères — pas de page cassée en prod.
- Le vocabulaire est de l'affichage : ne touche jamais aux clés JSON ni aux endpoints.
