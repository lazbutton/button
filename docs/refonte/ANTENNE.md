# Refonte de la page Antenne — ntr-console

> Spec de la refonte complète de la page `/antenne`. Sert de source à l'étape 3 du plan. À placer dans le repo (ex. `docs/refonte/ANTENNE.md`). Complète, ne remplace pas, le contrat moteur du PLAN.

## Principe

1. **Le pupitre tient dans l'écran.** Plus de défilement : l'état, le titre en cours, la file et la bibliothèque se lisent d'un coup d'œil. Ce qui ne se lit qu'une fois (la fiche encodeur) se replie.
2. **Un mot par état, un geste par intention.** Fini les trois « direct » qui se ressemblent : le bandeau dit l'état, un lien mène au passage en direct, et le bouton de saut s'appelle **Suivant**.
3. **Le bandeau montre la cause.** Un silence ou un problème s'accompagne de sa raison courte, sous les yeux de la personne à l'antenne — pas seulement dans Automate.
4. **Le vocabulaire est celui de l'antenne.** « pupitre » disparaît de l'écran ; une poignée de glisser + une infobulle disent « ajouté à la main, déplaçable ».

## Maquette cible

```
┌ ● En onde · 14:32                              Passer en direct ? ┐   (bandeau : état + cause + heure ; lien à droite)

┌ maintenant                                                        ┐
│ 2:14      Artiste — Titre                          [ Suivant → ]  │
│ restant   ▓▓▓▓▓▓▓▓▓░░░░░░                                         │
│           Auto-DJ · fin 14:35                                      │
│           (si direct) Direct — l'horloge est en pause · Renommer   │
└───────────────────────────────────────────────────────────────────┘

┌ File ─────────────────────┐   ┌ Bibliothèque ────────────────────┐
│ N  Artiste — Titre   2:58  │   │ [ Titre, artiste…              ] │
│ 2  Titre             3:10  │   │ toucher = à la suite · ▶ = maintenant │
│ + 6 dans le conducteur     │   │ Titre A                     [▶]  │
│                            │   │ Titre B                     [▶]  │
└────────────────────────────┘   └───────────────────────────────────┘
```

- Le pupitre tient sans défiler. Pas de rangée d'idents. Pas de fiche encodeur dépliée : le lien « Passer en direct ? » ouvre la fiche à la demande (disclosure ou route `/antenne/direct`).
- Sous 1100 px, File et Bibliothèque s'empilent. Cibles tactiles ≥ 40 px.

## Décisions, friction par friction (les 10 tensions résolues)

| # | Friction | Décision |
|---|---|---|
| 1 | Trois « direct » (bandeau / panneau / bouton Passer) | « Passer » devient **Suivant** (couper le titre) ; l'état direct vit dans le bandeau ; « Passer en direct ? » n'est qu'un lien |
| 2 | Panneau encodeur toujours déplié, plus gros que la carte | Replié derrière le lien « Passer en direct ? » ; le pupitre reprend le haut de l'écran |
| 3 | Bandeau, carte et file se répètent | Le bandeau porte l'état (+ la cause), la carte le titre, la file la suite ; aucun ne redit l'autre |
| 4 | « pupitre », mot interne | Une poignée de glisser + infobulle « ajouté à la main, déplaçable » ; le mot disparaît |
| 5 | Idents : drapeau fragile, rangée vide sans explication | **Retirés de la page P0** (utilité étroite, coupés en direct de toute façon) ; réactivables si un présentateur anime depuis la console |
| 6 | Deux boutons serrés par résultat sur mobile | Toucher un titre = à la suite ; un bouton ▶ = jouer maintenant ; lisible à 390 px |
| 7 | Entrée = à la suite, pas à l'antenne | Gardé, et dit clairement sous la recherche |
| 8 | Silence / Problème sans cause | Le bandeau montre la cause courte (« Silence 12 s », « Playout injoignable ») ; le détail reste dans Automate |
| 9 | Nommer le live une seule fois, sans correction | On peut **renommer** le live tant qu'il dure, depuis la carte |
| 10 | La page défile | Panneau replié et idents retirés : le pupitre tient dans l'écran |

## Fonctionnalités

| Fonction | Décision | Détail |
|---|---|---|
| Bandeau d'état | Gardé, enrichi | Ajoute la cause (silence N s, playout injoignable) sous les yeux |
| Carte maintenant | Gardée | Titre, restant, barre, source, fin |
| Bouton de saut | Retravaillé | « Passer » → **Suivant** (coupe le titre en cours) |
| Passer en direct | Retravaillé | Panneau replié en lien ; fiche encodeur à la demande |
| Nommer le live | Retravaillé | **Renommable** pendant tout le direct, depuis la carte |
| File | Gardée | 10 items, retrait avec Annuler, réordonner à la main |
| Bibliothèque | Retravaillée | Toucher = à la suite, ▶ = maintenant ; onglets Tous / Musique / Jingles / Archives |
| Idents (pads) | **Retiré** | Utilité étroite en P0, coupés en direct ; réactivables plus tard |
| Régler les idents | **Retiré** | Part avec les idents |
| Rappel clavier | Gardé, simplifié | Espace, /, Entrée |
| Dépannage, pastilles de santé | Ailleurs | Déjà dans Réglages → Automate, pas sur cette page |

## Interactions

**Clavier.** `Espace` = Suivant (sauf à l'arrêt ou en direct) ; `/` = focus recherche ; `Entrée` = met la ligne active à la suite ; `Échap` = vide la recherche. Retirés : `1–6` et `Maj+1–6` (partis avec les idents).

**Tactile et souris.** Toucher un résultat le met à la suite ; le bouton ▶ le joue maintenant ; on glisse une ligne « ajoutée à la main » pour la réordonner (les items d'horloge ne bougent pas).

**Direct.** À la connexion de l'encodeur : bandeau « Direct : {titre} », carte « l'horloge est en pause » + bouton **Renommer**. Suivant et les gestes d'antenne sont coupés pour tout le monde, admin compris. À la coupure, le moteur reprend seul (vide les files, saute le titre auto-DJ) ; la page ne déclenche rien.

## Contrat moteur (ne pas casser)

Refonte **purement côté console**. Mêmes endpoints, mêmes formes.

- **Lectures** : `GET /live.json` (1 s), `/autodj/conducteur.json?horizon=360`, `/antenne/emissions.json`, `/antenne/state.json`, `/carts.json`, `/library/search`.
- **Écritures** : `DELETE /live.json` (Suivant) · `POST /autodj/conducteur/now.json` (jouer maintenant) · `POST /autodj/conducteur/items.json` (à la suite) · `DELETE /autodj/conducteur/items/{id}.json` (retirer) · `POST .../items.json {suppress_at}` (retirer un item d'horloge) · `PUT .../items/ranks.json {ids}` (réordonner) · `POST /antenne/emissions.json {scope:"session", title, artist}` (nommer / renommer).
- Champs réels : **`title`** (nom de l'émission) et **`artist`** (phrase artiste), pas « nom »/« phrase ».
- Priorité des sources (au moteur) : direct > relais > carts > jingles > rotation.
- La console ne produit pas le son, ne règle pas la priorité, ne coupe pas le direct ; la coupure au retour d'antenne reste au moteur.
- **Aucun nouvel endpoint pour renommer** : `POST /antenne/emissions.json {scope:"session", title, artist}` efface déjà la session en cours et en recrée une, tant que le harbor est branché. Le renommage réutilise ça tel quel.
- Le harbor n'est pas un booléen : on le déduit de `source` (qui vaut `stream` ou `harbor`) dans `/live.json`. Les mutations portent l'en-tête `X-CSRF-Token` (lu dans `GET /csrf.json`) — à conserver.

## Fini quand

- [x] Le pupitre tient dans l'écran, sans défilement, sur ordinateur et mobile.
- [x] Un seul « direct » clair : bandeau (état), lien (se brancher), Suivant (couper le titre).
- [x] Le bandeau montre la cause d'un silence ou d'un problème.
- [x] Bibliothèque : toucher = à la suite, ▶ = maintenant, lisible à 390 px.
- [x] Plus d'idents ni de mot « pupitre » ; le live se renomme pendant le direct.
- [x] Aucun endpoint moteur cassé ; `title`/`artist` respectés.
- [ ] Un bénévole tient une heure d'antenne sans qu'on lui explique l'écran.
