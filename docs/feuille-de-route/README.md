# Feuille de route

Ce qui reste à faire, rangé par priorité. Chaque tâche est une **fiche** : assez précise pour qu'un agent la prenne seul, assez petite pour une branche.

| Priorité | Page | Pour |
|---|---|---|
| P1 | [P1-mise-en-prod.md](P1-mise-en-prod.md) | Mettre une station en production sur une machine exposée à Internet, l'installer en une commande, la mettre à jour sans casser l'antenne |
| P2 | [P2.md](P2.md) | Le confort d'exploitation, et ce qu'il faut avant de publier le logiciel |
| P3 | [P3.md](P3.md) | Plus tard : les fonctions, dans l'ordre que les radios demanderont |

## Les fiches

**L'identifiant** est un préfixe de thème et un numéro, comme SEC-01. Il ne change jamais et ne sert jamais deux fois, même si la fiche change de priorité ou disparaît.

| Préfixe | Thème |
|---|---|
| SEC | sécurité |
| GEN | une station générique, sans rien d'une station dans le code |
| TST | tests de bout en bout |
| MAJ | mettre à jour |
| INS | installer |
| SAV | sauvegarder |
| SUR | surveiller |
| DOC | documenter |
| LEG | licences |
| DEV | confort de développement |
| ARC | architecture |
| PUB | publier le logiciel |
| FON | fonctions nouvelles |
| UX | simplifier l'interface |

**La taille** : S, une demi-journée au plus ; M, un à deux jours ; L, trois à cinq jours. Une fiche plus grosse se coupe en deux.

**Une fiche est prête** quand ses dépendances sont faites, ses questions tranchées, et son « Accepté quand » vérifiable. Une fiche qui touche une station en service dit comment revenir en arrière.

**Les conflits** d'une fiche sont les fichiers qu'elle va sans doute toucher. Deux fiches dont les conflits se recoupent ne tournent pas en même temps.

## Le gabarit

```markdown
#### XXX-NN · Titre

Taille · dépend de … · conflits : fichiers

- **Pourquoi** : le besoin, en une phrase.
- **Aujourd'hui** : l'état du code, avec les fichiers.
- **À trancher avant de coder** : les questions de produit, avec une proposition. Facultatif.
- **À faire** : les changements, numérotés.
- **Mise en service** : ce qu'une station existante doit faire avant ou après. Facultatif.
- **Tests** : ce qui prouve que ça marche.
- **Accepté quand** : un critère qu'on peut vérifier.
```

## Prendre une fiche

1. Choisir une fiche prête dont les conflits ne recoupent pas ceux d'une fiche en cours.
2. Créer sa branche dans un worktree à part : `fiche/<ID>-<mot>`, par exemple `fiche/SEC-01-catalogue`. Une fiche est **en cours** tant que sa branche existe : `git branch -a --list 'fiche/*'`.
3. Suivre le [AGENTS.md](../../AGENTS.md) de la racine, puis celui du dossier touché.
4. Un commit par fiche, sauf si la fiche en prévoit plusieurs. Le message suit la règle `Zone : résumé`, et cite l'identifiant de la fiche dans son corps.
5. À la fusion, la personne qui fusionne passe la fiche à « fait » dans le tableau, avec le commit, puis supprime la branche.

Les agents ne modifient pas les tableaux pendant leur travail. Sinon chaque branche touche les mêmes lignes, et chaque fusion se bat avec la précédente.

## Ajouter une fiche

Un besoin nouveau, ou un défaut vu en passant : une fiche dans la bonne page, avec le prochain numéro libre de son thème. Une fiche trop vague reste une question : la poser plutôt que deviner.
