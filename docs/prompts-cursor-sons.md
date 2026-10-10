# Prompts Cursor (Grok 4.7) — refonte de la page Sons

**Fichier à poser dans le repo** : `docs/refonte/SONS.md` (les prompts le référencent avec `@SONS.md`).

**Méthode** : Grok 4.7 en mode Agent. **Un lot = une branche git = une session neuve.** Boucle *lis → propose un plan → j'valide → code → coche*. Relis les diffs, teste sur `:5175`, commit par lot. La page existe déjà (quatre onglets) : **garde-la fonctionnelle** et ne perds aucune capacité de la checklist « Tout ce que la page doit encore savoir faire ».

> Rappel API réelle : modes `playlist` / `playlist_loop` / `random` / `relay` ; création `POST /carts.json` (`title`, `mode`, `schedule_mode:"clock"`, `bank_folder`, `url`, `max_duration`) ; sons via `POST /carts/{id}/sounds.json?delta=1`, `PUT .../ranks.json {ranks}`, `PUT .../sounds/{id}.json {title|active}`, `POST .../sounds/delete.json {ids}`, `.../now.json` ; banque `/library/inbox.json` + `/tus/` = **ntr-ops**, pas le moteur ; un seul `ident_pads` ; mutations avec `X-CSRF-Token`. **Ne « corrige » pas le code qui marche pour coller au vocabulaire** : le vocabulaire est un affichage.

---

## Prompt d'amorçage (sans coder)

```
Lis @SONS.md en entier, puis explore /sons dans ntr-console : les onglets Carts, Habillage, Relais, Importer (liste des carts, tableau des sons, inspecteur, dépôt Uppy/tus). Repère les endpoints /carts, /media/bank.json, /library/inbox.json, /tus/.
Ne code rien. Réponds : 1) composants et fichiers de la page ; 2) où sont les chaînes de texte (pour le vocabulaire) ; 3) les écarts avec la cible de @SONS.md (fusion des trois onglets en Bacs, trois imports clarifiés, inspecteur allégé, Importer → Banque). Signale tout endpoint dont la forme diffère.
```

---

## P1 — Vocabulaire *(sûr, à faire en premier)*

```
@SONS.md P1 : le vocabulaire de la page Sons. Uniquement de l'affichage, aucune logique ni endpoint touché.
Lis où sont les chaînes, propose la liste des libellés, attends validation.
Applique la table : cart → « bac » (bac de sons), Importer → « Banque », bank_folder → « dossier de la banque », « attacher depuis la banque » → « lier un dossier (sans copie) », modes → Boucle / Aléatoire / Une fois / Relais, ident_pads → « Pads d'idents (avancé) ».
Ne renomme aucune clé JSON. Note : le renommage cart → bac devrait être appliqué à toute l'app (Antenne, Programmation) dans une passe séparée pour rester cohérent — signale-le, ne le fais pas ici. Coche : plus de « cart » ni « Importer » à l'écran, sur cette page.
```

## P2 — Onglet Bacs *(fusion des trois onglets, le gros du lot)*

```
@SONS.md P2 : fusionne Carts, Habillage et Relais en un seul onglet « Bacs » (voir la maquette).
Lis les trois onglets (même écran filtré) et le modèle de cart, propose le plan des fichiers, attends validation.
Construis : à gauche une seule liste de tous les bacs + un filtre par type (Tous / Fichiers / Habillage / Relais) — Habillage devient un filtre (bacs dont bank_folder commence par 30-habillage), plus un onglet ; un bac n'apparaît qu'une fois. À droite, un éditeur qui s'adapte : bac de fichiers → tableau des sons (rang sauf aléatoire, aperçu local, titre éditable, actif/inactif, envoyer maintenant, supprimer) ; relais → URL du flux + durée max.
Garde tous les endpoints sons et le now.json. Ne casse pas l'ouverture par ?id= depuis Programmation. Coche les critères.
```

## P3 — Les trois imports et l'inspecteur allégé

```
@SONS.md P3 : clarifie les trois ajouts et allège les réglages.
Lis les gestes d'import actuels (Ajouter, dossier, Attacher depuis la banque) et l'inspecteur, propose le plan, attends validation.
Rends explicites, dans l'éditeur d'un bac : « Ajouter des fichiers » (copie) et « Attacher un dossier (sans copie) ». Mets en avancé (replié) : dossier banque, bloc Finder/SMB, pads d'idents (avec une aide neutre, sans promettre la rangée Antenne retirée en P0). Rends le mode « Une fois » (playlist) choisissable comme les autres, pas seulement dans l'inspecteur.
Ne touche pas aux endpoints (delta=1, {folders}, ranks). Coche les critères.
```

## P4 — Onglet Banque (ex-Importer)

```
@SONS.md P4 : renomme et finis l'onglet Banque.
Lis l'onglet Importer actuel (Uppy/tus, quota, listes), propose le plan, attends validation.
Renomme « Importer » → « Banque ». Garde le dépôt reprenable (tus vers /tus/), la destination (Rotation, NTF 1–3), la jauge de quota (/library/inbox.json), et les trois listes (en cours, file d'attente, rejets avec raison). Rappelle en une ligne la différence avec « Ajouter » dans un bac.
/library/inbox.json et /tus/ sont ntr-ops : ne les confonds pas avec /carts.json. Coche les critères.
```

---

## Optionnel — recette

```
Sans coder : passe /sons refondue contre la checklist « Tout ce que la page doit encore savoir faire » de @SONS.md, coche chaque ligne avec le fichier/écran concerné, signale toute capacité perdue. Audit seulement.
```

## Rappels

- Ordre : P1 (sûr), puis P2 (le gros), puis P3, puis P4.
- Garde l'ancien onglet derrière sa route tant que le nouveau ne passe pas ses critères.
- Le vocabulaire est de l'affichage : jamais de renommage de clés JSON ni d'endpoints. `cart → bac` se décide pour toute l'app, pas page par page.
