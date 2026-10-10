# Prompts Cursor — jeu complet pour mettre en place les projets

## Avant de commencer

**Fichiers à poser dans le repo** (Cursor les référence avec `@`) :
- `docs/refonte/PLAN.md` — le brief d'implémentation (contexte, API moteur, 10 étapes).
- `docs/refonte/ANTENNE.md` — la refonte complète de la page Antenne (source de l'étape 3).
- `.cursor/rules/refonte.mdc` — les règles d'or, toujours actives.

**Méthode** (vaut pour toutes les étapes) :
- **Une étape = une branche git = une session de chat neuve** (Composer/Agent), avec le modèle le plus costaud.
- Chaque prompt suit la boucle : *l'agent lit → propose un plan → tu valides → il code → il coche les critères*.
- Tu relis les diffs fichier par fichier, tu testes sur `:5175`, tu commits par étape.
- Étape 1 (rôles) d'abord, toujours. L'ordre des étapes est celui du PLAN.

---

## Prompt d'amorçage (une seule fois, sans coder)

```
Lis @PLAN.md et @ANTENNE.md en entier, puis explore ntr-console, radiotomate et ntr-ops.
Ne code rien. Réponds-moi :
1) l'arborescence de ntr-console (routes, composants, où se lit /account.json, où se décide l'accès aux pages) ;
2) les endpoints JSON réellement exposés par radiotomate et leurs formes exactes (requête/réponse) ;
3) les écarts entre le code actuel et : le modèle de rôles du PLAN, et la refonte de @ANTENNE.md.
Si l'API réelle diffère du PLAN, dis-le : on corrigera le PLAN avant de coder.
```

---

## Étape 1 — Rôles et accès *(fondement)*

```
@PLAN.md Étape 1 (Rôles et accès). À faire en premier.
Lis comment l'accès aux pages est décidé aujourd'hui dans ntr-console, et la forme de /account.json. Liste les fichiers à toucher et attends ma validation avant de coder.
Implémente le modèle 3 rôles (Animateur/Programmateur/Admin) + interrupteur « Peut passer en direct », avec la traduction rôle→drapeaux et la lecture inverse du PLAN. Créer/éditer un compte se fait par rôle, jamais par les six cases brutes. `not_audio` n'apparaît nulle part.
Reste dans le périmètre. Coche les critères d'acceptation de l'étape 1 et dis comment les vérifier.
```

## Étape 2 — Coque, navigation, déconnexion

```
@PLAN.md Étape 2 (Coque, navigation, déconnexion). L'étape 1 est fusionnée.
Lis la coque et le routing actuels, propose le plan des fichiers, attends validation.
Implémente les cinq sections (Antenne, Conducteur, Programmation, Sons, Réglages), une route par écran, supprime les routes qui redirigent, ajoute une Déconnexion visible partout (mobile compris) et un login par compte personnel (retire le préremplissage du compte de la marque). Le menu n'affiche que les sections permises par le rôle.
Reste dans le périmètre. Coche les critères de l'étape 2.
```

## Étape 3 — Refonte complète de la page Antenne

```
@ANTENNE.md Refonte complète de la page /antenne. Suis ce document de bout en bout ; il résout dix frictions précises.
Lis d'abord la page /antenne actuelle et le contrat moteur du PLAN, propose le plan des fichiers, attends validation.
Applique la refonte : pupitre qui tient dans l'écran (fiche encodeur repliée derrière le lien « Passer en direct ? ») ; bouton de saut renommé « Suivant » ; bandeau d'état unique qui montre la cause (silence N s, playout injoignable) ; bibliothèque où toucher = à la suite et ▶ = jouer maintenant ; retrait des idents et du mot « pupitre » (poignée + infobulle) ; live renommable pendant le direct.
Respecte le contrat moteur de @ANTENNE.md : mêmes endpoints, champs `title`/`artist`, priorité des sources inchangée, la console ne coupe pas le direct. Tiens sur mobile (≥ 390 px). Coche la checklist « Fini quand » de @ANTENNE.md.
```

## Étape 4 — Programmation unifiée

```
@PLAN.md Étape 4 (Programmation unifiée).
Lis Auto-DJ actuel + le code mort Atelier Horloges et Catégories, propose le plan, attends validation.
Crée /programmation à quatre onglets : Rotation, Horloges (ressuscite l'atelier), Semaine (remonte la grille hebdo au premier plan), Catégories (ressuscite la table). Chaque onglet fonctionne bout à bout contre le moteur (départs, émissions, catégories).
Aucun code d'écran sans route. Reste dans le périmètre. Coche les critères de l'étape 4.
```

## Étape 5 — Sons + relais éditable *(décrochages)*

```
@PLAN.md Étape 5 (Sons + relais éditable, décrochages).
Lis la page Carts actuelle et le modèle de cart du moteur (dont les champs relay : URL + durée max), propose le plan, attends validation.
Crée /sons à onglets : Carts, Habillage, Relais (édite enfin les carts relay : URL HTTP + durée max obligatoire), Importer (préparé ici, rempli à l'étape 7). Garde le drapeau « pads d'idents » dans le modèle de cart, mais NE l'affiche PAS sur la page Antenne (les idents sont retirés du pupitre P0, cf. @ANTENNE.md) : l'écran de réglage des pads reste dans Sons, pour un usage futur.
Reste dans le périmètre. Coche les critères de l'étape 5.
```

## Étape 6 — Passer en direct (fiche + état)

```
@PLAN.md Étape 6 (Passer en direct). Le branchement reste externe (encodeur) ; la console guide et reflète l'état.
Lis /live.json et /antenne/state.json, propose le plan, attends validation.
Implémente la fiche « Passer en direct » ouverte depuis le lien du bandeau Antenne (cf. @ANTENNE.md) : état du harbor (branché/en attente/absent), règle du créneau, et la fiche encodeur (Icecast, adresse Nasgul, port 6800, mount /stream, compte avec droit Stream, MP3 128–192). Ne crée pas de bouton « passer en direct » et ne réimplémente pas la coupure (comportement moteur).
Coche les critères de l'étape 6.
```

## Étape 7 — Dépôt de musique par le navigateur

```
@PLAN.md Étape 7 (Dépôt web, Uppy + tusd). Étape avec du backend.
Lis la chaîne dropbox/Beets et l'arbo des inbox (00-inbox/rotation, 00-inbox/archives/ntf1..ntf3), propose le plan (front ntr-console + tusd dans ntr-ops + un endpoint file d'attente/rejets), attends validation.
Implémente : Uppy dans Sons → Importer (upload reprenable tus), tusd qui range selon l'onglet (rotation/archives), avancement, rejets avec motif, quota. Refuse les formats inconnus. Ne réimplémente pas l'indexation (c'est Beets). Toute modif moteur/ops : minimale et rétro-compatible.
Coche les critères de l'étape 7.
```

## Étape 8 — Mon compte

```
@PLAN.md Étape 8 (Mon compte).
Lis la gestion des comptes actuelle, propose le plan, attends validation.
Ajoute Réglages → Mon compte : changer son mot de passe, voir son rôle et ses créneaux, se déconnecter. Côté Comptes (admin) : réinitialiser un mot de passe, éditer les notes, voir les créneaux d'un compte sur sa fiche.
Reste dans le périmètre. Coche les critères de l'étape 8.
```

## Étape 9 — Dépannage et Automate

```
@PLAN.md Étape 9 (Dépannage et Automate).
Lis le dépannage actuel (pupitre) et Relancer/Réinitialiser (conducteur), propose le plan, attends validation.
Crée Réglages → Automate (admin) : santé complète (les six pastilles + popovers, déplacées depuis Antenne — cf. @ANTENNE.md qui les retire du pupitre), dépannage unifié (Recharger l'état, Vider les files, Reconstruire le conducteur — fusionne les gestes aujourd'hui doublés), page de statut lisible.
Plus aucun geste de réparation ailleurs. Coche les critères de l'étape 9.
```

## Étape 10 — Polissage

```
@PLAN.md Étape 10 (Polissage).
Passe l'app en revue : nommage unique (plus de pastilles renommées selon le rôle), messages d'erreur qui disent quoi faire, mobile vérifié écran par écran, accessibilité (focus, clavier, contrastes). Retire le code mort et les routes fantômes restantes.
Propose la liste de ce que tu comptes changer, attends validation, applique par petits diffs. Coche les critères de l'étape 10 et la définition de « fini » globale du PLAN.
```

---

## Rappel

- Si l'amorçage révèle que l'API réelle diffère du PLAN, **fais corriger `PLAN.md` d'abord**, puis enchaîne les étapes.
- Ne laisse pas l'agent sortir du périmètre d'une étape ni « améliorer » ailleurs.
- Garde l'ancien écran derrière la route tant que le nouveau ne passe pas ses critères.
