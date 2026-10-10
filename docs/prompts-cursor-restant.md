# Prompts Cursor — ce qui reste vraiment à faire

D'après l'inventaire du code : **les étapes 1 à 10 sont déjà faites.** Rôles, navigation, Programmation, Sons, Automate, dépôt web, Mon compte : en place. Il ne reste que **la refonte de la page Antenne** (pas encore appliquée) et **un petit écart de rôle**. Voici uniquement ces prompts.

> Rappel API (l'inventaire fait foi, pas les noms français du PLAN) : champs `title` / `artist` (pas nom/phrase), identifiant plateau `host_username`, créneau `day_of_week` + `start_minute` + `end_minute`, modes de cart `playlist` / `playlist_loop` / `random` / `relay`, harbor déduit de `source` (`stream`/`harbor`), mutations avec `X-CSRF-Token` (de `GET /csrf.json`), catalogue et dépôt via `ntr-ops` (`/library/search`, `/inbox.json`, `/tus/`). **Ne « corrige » pas le code qui marche pour le faire coller au PLAN** : c'est le PLAN qui est approximatif.

---

## Prompt 1 — Refonte de la page Antenne *(le gros du travail restant)*

```
@ANTENNE.md Applique la refonte complète de la page /antenne. La page actuelle est encore l'ancien pupitre ; ce document est la cible et résout dix frictions précises.
D'abord : lis src/pages/AntennePage.tsx et ses composants (DeskGlance, DeskFile, DeskLibrary, DeskHotStrip, LiveConnectPanel), puis /live.json et /antenne/state.json. Liste les fichiers à toucher et attends ma validation.
Applique, en respectant l'API réelle :
- Pupitre qui tient dans l'écran : replie LiveConnectPanel derrière un lien « Passer en direct ? » (disclosure ou route /antenne/direct). Plus de fiche encodeur dépliée en permanence.
- Renomme le bouton « Passer » en « Suivant » (garde DELETE /live.json, droit live).
- Bandeau d'état unique qui montre la cause : lis playout.silence_s et incidents[] dans /antenne/state.json (« Silence 12 s », « Playout injoignable »). Le harbor se déduit de source (stream/harbor).
- Bibliothèque : toucher un résultat = à la suite (POST /autodj/conducteur/items.json) ; un seul bouton ▶ = jouer maintenant (POST /autodj/conducteur/now.json). Supprime le double bouton.
- Retire la rangée Idents (DeskHotStrip) et les touches 1–6 / Maj+1–6. Garde le drapeau ident_pads dans le modèle de cart et son réglage dans Sons (usage futur), mais plus rien sur Antenne.
- Retire le mot « pupitre » des lignes de file : une poignée de glisser + infobulle « ajouté à la main, déplaçable » (origin: desk).
- Live renommable pendant tout le direct depuis la carte : POST /antenne/emissions.json {scope:"session", title, artist} remplace la session, aucun nouvel endpoint. Garde X-CSRF-Token.
Ne casse aucun endpoint, ne touche pas à la priorité des sources, ne réimplémente pas la coupure du direct. Tiens à 390 px. Coche la checklist « Fini quand » de @ANTENNE.md.
```

---

## Prompt 2 — Écart de rôle : animateur en lecture seule sur le Conducteur

```
Écart relevé à l'inventaire : sur /conducteur, un Animateur peut encore retirer une ligne, alors que le rôle prévoit la lecture seule (retirer/reconstruire = programmateur/admin).
Lis ConducteurPage et src/api/roles.ts, propose le plan, attends validation.
Masque les gestes d'écriture du Conducteur (retirer une ligne, etc.) pour l'Animateur ; garde-les pour Programmateur et Admin. Ne touche pas à la File de la page Antenne, où l'animateur garde ses gestes de pupitre.
Coche : un Animateur ne peut plus modifier le Conducteur ; Programmateur et Admin, si.
```

> Note sur l'autre écart (un admin sans l'interrupteur Stream peut quand même se brancher) : c'est un override admin volontaire côté moteur, et l'interface le dit déjà. **Rien à coder**, sauf si tu veux le supprimer — dans ce cas, dis-le et j'ajoute un prompt.

---

## Optionnel — Vérifier les étapes déjà faites

```
Sans rien coder : passe en revue les étapes 1, 2, 4, 5, 6, 7, 8, 9, 10 de @PLAN.md contre le code actuel, et coche leurs critères d'acceptation un par un. Signale tout critère non tenu, avec le fichier concerné. C'est un audit, pas une modification.
```

---

## Si tu veux remettre le PLAN au propre

Le PLAN.md décrit des noms d'API approximatifs. Le code, lui, est correct. Prompt de mise à jour **de la doc seulement** :

```
Sans toucher au code : corrige @PLAN.md pour qu'il colle à l'API réelle décrite dans l'inventaire — title/artist, host_username, day_of_week/start_minute/end_minute, modes de cart playlist/playlist_loop/random/relay, harbor déduit de source, X-CSRF-Token, /library/search et /inbox.json côté ntr-ops, ident_pads et PUT /account.json déjà présents. Ne change que la documentation.
```
