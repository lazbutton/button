# Prompts Cursor — un par étape

Mode d'emploi : **une étape = une branche git = une session de chat neuve** (Composer/Agent). Colle le prompt, laisse-le lire et proposer un plan, valide, puis laisse-le coder. Relis les diffs, teste, commit. Les règles d'or sont dans `.cursor/rules/refonte.mdc` (toujours actives) et le détail dans `@PLAN.md`.

---

## Prompt d'amorçage (une seule fois, sans coder)

```
Lis @PLAN.md en entier, puis explore ntr-console, radiotomate et ntr-ops.
Ne code rien. Réponds-moi :
1) l'arborescence de ntr-console (routes, composants principaux, où se lit /account.json et où se décide l'accès aux pages) ;
2) les endpoints JSON réellement exposés par radiotomate et leurs formes exactes (requête/réponse) ;
3) les écarts que tu vois entre le code actuel et le modèle de rôles du plan.
C'est un état des lieux pour préparer les étapes suivantes.
```

---

## Étape 1 — Rôles et accès

```
@PLAN.md Étape 1 (Rôles et accès). C'est le fondement, à faire en premier.
D'abord : lis dans ntr-console comment l'accès aux pages est décidé aujourd'hui, et dans radiotomate la forme de /account.json. Liste les fichiers à toucher et attends ma validation avant de coder.
Puis implémente le modèle 3 rôles (Animateur/Programmateur/Admin) + interrupteur « Peut passer en direct », avec la traduction rôle→drapeaux et la lecture inverse décrites dans le plan. La création/édition d'un compte se fait par rôle, jamais par les six cases.
Reste strictement dans le périmètre de l'étape. À la fin, coche les critères d'acceptation de l'étape 1 et dis comment les vérifier.
```

---

## Étape 2 — Coque, navigation, déconnexion

```
@PLAN.md Étape 2 (Coque, navigation, déconnexion). L'étape 1 est faite et fusionnée.
Lis la coque et le routing actuels, propose le plan des fichiers, attends validation.
Implémente les cinq sections (Antenne, Conducteur, Programmation, Sons, Réglages) avec une route par écran, supprime les routes qui redirigent, ajoute un bouton Déconnexion visible partout (mobile compris) et un login par compte personnel (retire le préremplissage du compte de la marque). Le menu n'affiche que les sections permises par le rôle.
Reste dans le périmètre. Coche les critères d'acceptation de l'étape 2.
```

---

## Étape 3 — Page Antenne P0

```
@PLAN.md Étape 3 (Page Antenne P0). Suis la maquette du plan.
Lis la page /antenne actuelle, propose le plan, attends validation.
Retire : les 5 puces, les 6 pastilles + le dépannage (ils iront dans Automate, étape 9), la rangée de pads Pubs, le bloc Passé, les onglets Pubs/Habillage/Émissions, le geste Remplacer.
Garde et clarifie : bandeau d'état unique (En onde/Silence/Direct/Problème + heure), carte maintenant + Passer, File | Bibliothèque avec deux actions « Jouer maintenant » et « À la suite », une rangée d'idents, le passage en direct avec « Nommer ce live ». Clavier réduit : Espace, 1–6, /, Entrée.
Même page pour tous les rôles. Tiens sur mobile. Coche les critères d'acceptation de l'étape 3.
```

---

## Étape 4 — Programmation unifiée

```
@PLAN.md Étape 4 (Programmation unifiée).
Lis Auto-DJ actuel + le code mort Atelier Horloges et Catégories, propose le plan, attends validation.
Crée la section /programmation à quatre onglets : Rotation, Horloges (ressuscite l'atelier), Semaine (remonte la grille hebdo au premier plan), Catégories (ressuscite la table). Chaque onglet doit fonctionner bout à bout contre le moteur (départs, émissions, catégories).
Ne laisse aucun code d'écran sans route. Reste dans le périmètre. Coche les critères de l'étape 4.
```

---

## Étape 5 — Sons + relais éditable

```
@PLAN.md Étape 5 (Sons + relais éditable, décrochages).
Lis la page Carts actuelle et le modèle de cart du moteur (dont les champs relay : URL + durée max), propose le plan, attends validation.
Crée la section /sons à onglets : Carts, Habillage, Relais (édite enfin les carts relay : URL HTTP + durée max obligatoire), Importer (préparé ici, rempli à l'étape 7). Remplace les pads « par titre exact Jingles/Pubs » par un drapeau explicite sur le cart, et branche-le à la rangée d'idents de l'étape 3.
Reste dans le périmètre. Coche les critères de l'étape 5.
```

---

## Étape 6 — Passer en direct (panneau + fiche)

```
@PLAN.md Étape 6 (Passer en direct). Le branchement reste externe (encodeur) ; la console guide et reflète l'état.
Lis /live.json et /antenne/state.json (état du harbor), propose le plan, attends validation.
Ajoute dans Antenne un panneau « Passer en direct » : état du harbor (branché/absent/en attente) + fiche mode d'emploi d'une page (Icecast, adresse Nasgul, port 6800, mount /stream, compte avec droit Stream, MP3 128–192). Rappelle la règle des créneaux (émission nominative → seul ce compte ou un admin).
Ne crée pas de bouton « passer en direct » et ne réimplémente pas la coupure (comportement moteur existant). Coche les critères de l'étape 6.
```

---

## Étape 7 — Dépôt de musique par le navigateur

```
@PLAN.md Étape 7 (Dépôt web, Uppy + tusd). Étape avec du backend.
Lis la chaîne dropbox/Beets et l'arbo des inbox (00-inbox/rotation, 00-inbox/archives/ntf1..ntf3), propose le plan (front ntr-console + tusd dans ntr-ops + un endpoint de file d'attente/rejets), attends validation.
Implémente : Uppy dans l'onglet Sons → Importer (upload reprenable tus), tusd qui range selon l'onglet (rotation/archives), affichage de l'avancement, des rejets avec motif, et d'un quota. Refuse les formats inconnus.
Ne réimplémente pas l'indexation (c'est Beets). Toute modif moteur/ops : minimale et rétro-compatible. Coche les critères de l'étape 7.
```

---

## Étape 8 — Mon compte

```
@PLAN.md Étape 8 (Mon compte).
Lis la gestion des comptes actuelle, propose le plan, attends validation.
Ajoute Réglages → Mon compte : changer son mot de passe, voir son rôle et ses créneaux, se déconnecter. Côté Comptes (admin) : réinitialiser un mot de passe, éditer les notes, voir les créneaux d'un compte sur sa fiche.
Reste dans le périmètre. Coche les critères de l'étape 8.
```

---

## Étape 9 — Dépannage et Automate

```
@PLAN.md Étape 9 (Dépannage et Automate).
Lis le dépannage actuel (pupitre) et Relancer/Réinitialiser (conducteur), propose le plan, attends validation.
Crée Réglages → Automate (admin) : la santé complète (les six pastilles + popovers, déplacées depuis Antenne), un dépannage unifié (Recharger l'état, Vider les files, Reconstruire le conducteur — fusionne ici les gestes aujourd'hui doublés), et une page de statut lisible.
Il ne doit plus rester aucun geste de réparation ailleurs. Coche les critères de l'étape 9.
```

---

## Étape 10 — Polissage

```
@PLAN.md Étape 10 (Polissage).
Passe toute l'app en revue : nommage unique (plus de pastilles renommées selon le rôle), messages d'erreur qui disent quoi faire, mobile vérifié écran par écran, accessibilité (focus, clavier, contrastes). Retire le code mort et les routes fantômes restantes.
Propose la liste de ce que tu comptes changer, attends validation, puis applique par petits diffs. Coche les critères de l'étape 10 et la définition de « fini » globale du plan.
```
