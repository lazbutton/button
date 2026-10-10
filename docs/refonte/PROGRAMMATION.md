# Refonte de la page Programmation — ntr-console

> Spec de la refonte de `/programmation`. À placer dans le repo (ex. `docs/refonte/PROGRAMMATION.md`). Complète, ne remplace pas, le contrat moteur du PLAN. La page actuelle a déjà les quatre onglets ; cette refonte les simplifie sans rien perdre.

## Principe

1. **Deux gestes, deux onglets.** Construire une heure type (**Horloges**), puis dire quand elle joue (**Semaine**). Fini les quatre onglets et les deux endroits qui réglaient la même horloge.
2. **Des mots simples.** « motif » → « ce qui passe, dans l'ordre » ; « ancre » → « coupure à la minute » ; « départ » → « changement d'horloge ». Le code garde ses noms ; seul l'affichage change.
3. **Une seule façon d'enregistrer.** Chaque changement s'enregistre tout seul, avec un « Enregistré » clair. Plus un onglet qui écrit à chaque geste et un autre qui attend un bouton.
4. **Rien de perdu.** Tout ce que la page sait faire reste possible ; l'avancé (coupures à d'autres minutes que :20/:40, catégories Beets, réglet minute par minute) se replie au lieu de disparaître.

## Le modèle

Une **heure type** (Horloge) est posée dans la **Semaine** (quand elle joue), et l'**Antenne** joue le résultat. Les **catégories** alimentent la musique (avancé). Le **direct** de l'encodeur passe devant tout.

Structure cible : **2 onglets** — Horloges, Semaine — plus **Catégories** en avancé (secondaire). Même écran pour programmateur et admin.

## Onglet Horloges — construire une heure type

Fusion des onglets Rotation et Horloges en **un seul éditeur**. Auto-save.

```
┌ Heures types ──────┐  ┌ Jour habillé                          ✓ Enregistré ┐
│ + Nouveau          │  │ Ce qui passe, dans l'ordre                          │
│ ▸ Jour habillé     │  │   1 · Jingles                              ↑ ↓ ✕    │
│   à l'antenne      │  │   2 · Programme                            ↑ ↓ ✕    │
│   Nuit nappe       │  │   + ajouter une étape                               │
│   Journée pubs     │  │ Coupures pub                                        │
│                    │  │   ☑ :20   ☑ :40  ·  cart : Virgules                 │
│                    │  │   + autre minute (avancé)                           │
│                    │  │ Si un bac est vide                                  │
│                    │  │   jouer : Jingles                                   │
└────────────────────┘  └─────────────────────────────────────────────────────┘
```

- **Gauche** : la liste des heures types ; celle à l'antenne est marquée.
- **Droite** : trois blocs — *ce qui passe, dans l'ordre* (les étapes jingle/programme/pub, ajouter / réordonner / retirer, cart par étape) ; *coupures pub* (cases :20 et :40 + cart, comme l'actuel Rotation) ; *si un bac est vide* (cart de secours).
- **Avancé, replié** : le réglet 0–60, les coupures à d'autres minutes, le choix dur (coupe à l'heure pile) / mou (attend la fin du titre).
- **Auto-save** : chaque geste écrit, un indicateur « Enregistré » le confirme. Plus de bouton Enregistrer séparé, plus de perte en changeant d'onglet.

## Onglet Semaine — placer les heures et les directs

```
┌ ● À l'antenne   Jour habillé · jusqu'à 24:00            ensuite : Nuit nappe ┐

┌ Lundi 28  aujourd'hui ─┐ ┌ Mardi 29 ───────┐ ┌ Mercredi 30 ─────┐
│ + changement + émission│ │ + changement …  │ │ + changement …   │
│ 00:00→07:00 Nuit nappe │ │ 00:00 Nuit nappe│ │ 00:00 Nuit nappe │
│ 07:00→24:00 Jour habillé│ │ 07:00 Jour hab.│ │ 07:00 Jour hab.  │
│   [20:00→22:00 · direct│ │                 │ │                  │
│    Hop Pop Hop]        │ │                 │ │                  │
└────────────────────────┘ └─────────────────┘ └──────────────────┘
```

- Par jour, une suite lisible : **à telle heure, telle horloge**. La journée commence toujours avec une horloge.
- Le « départ de minuit obligatoire » et le « Nettoyer N départs » disparaissent : deux plages identiques qui se suivent **fusionnent toutes seules**.
- Deux boutons par jour : **+ changement d'horloge** (heure, horloge) et **+ émission en direct** (`title`, `artist`, `host_username`, jour, minutes). Le moteur refuse un chevauchement ; la page affiche le refus.
- Bande « À l'antenne » : ce qui joue et ce qui suit. Le direct de l'encodeur passe devant, comme au modèle.

## Vocabulaire (interne → écran)

| Mot interne | Mot à l'écran |
|---|---|
| Horloge | Heure type |
| Motif | Ce qui passe, dans l'ordre |
| Position | Étape |
| Ancre | Coupure à la minute |
| Ancre dure | Coupe à l'heure pile |
| Ancre molle | Attend la fin du titre |
| Départ / daypart | Changement d'horloge |
| Cart de secours (fallback) | Si un bac est vide, jouer… |
| Catégorie Beets | Sélection de titres (avancé) |
| Émission (scope weekly) | Émission en direct |

Voix unique : on **tutoie** partout (l'onglet Catégories, qui vouvoyait, s'aligne).

## Décisions

| Aujourd'hui | Refonte | Type |
|---|---|---|
| Rotation et Horloges éditent la même horloge à deux endroits | Un seul éditeur d'heure type | Fusionné |
| Deux modèles d'écriture (Rotation à chaque geste, Horloges au bouton) | Auto-save partout, indicateur « Enregistré » | Simplifié |
| Départ de minuit obligatoire, « Nettoyer N départs », fusion à la main | Journée qui commence toujours avec une horloge, fusion automatique | Simplifié |
| Vocabulaire d'ingénieur (motif, ancre, départ) | Mots simples (table ci-dessus) | Simplifié |
| Réglet 0–60 et dure/molle au premier plan | :20/:40 en un clic, le reste en avancé | Simplifié |
| Catégories mêlées aux onglets, en vouvoiement | Onglet avancé, tutoiement | Déplacé |
| « Réparer un cart manquant » sans bouton | Bouton « Réparer » sur un cart manquant | Ajouté |
| Changer d'onglet oublie ce qu'on n'a pas enregistré | Auto-save : rien à perdre | Corrigé |

## Contrat moteur (ne pas casser)

Refonte **côté console**. Mêmes endpoints, mêmes champs. La page écrit la grille que le moteur lira.

- **Lectures** : `/autodj/clocks.json`, `/carts.json`, `/autodj/conducteur.json` (horloge à l'antenne), `/autodj/slots.json`, `/autodj/categories.json`, `/antenne/emissions.json`, `/users.json`, `/autodj/testquery.json`.
- **Écritures** (`X-CSRF-Token`) : `POST/PUT/DELETE /autodj/clocks[/{id}].json` · `POST/PUT/DELETE /autodj/slots[/{id}].json` · `POST/PUT/DELETE /antenne/emissions[/{id}].json` · `POST/PUT/DELETE /autodj/categories[/{id}].json`.
- **Champs** : émission `title`, `artist`, `host_username`, `day_of_week` (0 = lundi), `start_minute`, `end_minute`, `scope` ; départ `title`, `day_of_week`, `minute`, `clock_id`, `color` ; horloge `name`, `version`, `fallback_cart`, `motif`, `anchors` ; catégorie `name`, `query`, `empty_query`.
- Un `PUT` d'horloge retire les étapes `kind: musique` (`withoutLibrarySteps`) : pas de catégorie Beets posée dans le motif par ce chemin.
- Priorité des sources (au moteur) : direct > relais > carts > jingles > rotation.

**Tout ce que la page doit encore savoir faire**

- [ ] Choisir l'horloge éditée, voir ses étapes, réordonner, changer le cart d'une étape, ajouter, retirer.
- [ ] Poser et retirer les coupures pub, au minimum :20 et :40 en coupe dure.
- [ ] Créer, renommer, supprimer une horloge ; savoir laquelle est à l'antenne et où elle sert dans la semaine.
- [ ] Poser un changement d'horloge (heure, jour, horloge), le changer, le retirer, sans effacer celui de minuit.
- [ ] Poser une émission hebdo et montrer le refus du moteur en cas de chevauchement.
- [ ] Créer, modifier, supprimer, tester une catégorie Beets.
- [ ] Revenir vers Sons sur un cart précis (`/sons?id=`).
- [ ] Rester réservé au programmateur et à l'admin, même écran pour les deux.
