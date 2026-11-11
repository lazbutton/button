# Feuille de route

Ce qui reste à faire, rangé par priorité. Chaque tâche est une **fiche** : assez précise pour qu'un agent la prenne seul, assez petite pour une branche.

| Priorité | Page | Pour |
|---|---|---|
| P1 | [P1-mise-en-prod.md](P1-mise-en-prod.md) | Mettre une station en production sur une machine exposée à Internet, l'installer en une commande, la mettre à jour sans casser l'antenne |
| P2 | [P2.md](P2.md) | Le confort d'exploitation, et ce qui entoure la publication du logiciel |
| P3 | [P3.md](P3.md) | Plus tard : les fonctions, dans l'ordre que les radios demanderont |

## Où on en est

Relevé le 11 novembre 2026, sur `main` après la PR 130. La dernière version publiée est la 0.2.0, du 10 novembre. P1 a 19 fiches faites sur 28, P2 une sur 46. La personne qui fusionne tient cette partie à jour, comme les tableaux.

**D'abord**, parce que le dépôt est public, et qu'une station a été installée sur un VPS en 0.2.0 :

1. **Le correctif du tirage des bacs, puis la version suivante.** Depuis les PR 115 et 121, `main` a quatre défauts du tirage, relevés à leur relecture du 11 novembre : « Diffuser maintenant » qui rejoue le son entendu à l'instant, ou toujours le même après un direct qui a retenu une coupure, un bac bloqué sur un son que l'antenne ne dit jamais, et des sons sautés en Boucle. La 0.2.0 n'a pas ce tirage, donc pas ces défauts. La version suivante attend leur correctif, qui touche `clock.py`, `execution.py`, `rundown.py` et `cart_draw.py` : dans les tableaux, c'est « le correctif du tirage des bacs ». Elle porte aussi ce qu'il faut à une station neuve : la banque de sons rendue au moteur, et un conducteur qui ne s'empile plus.
2. **PUB-03, les réglages du dépôt public, et PUB-01, les secrets dans l'historique.** Les réglages se posent en quelques minutes, par la personne qui tient le dépôt.
3. **GEN-02**, qui retire du code les données de la station d'origine.
4. **TST-06** : depuis le 10 novembre, un passage des parcours sur trois rougit sans défaut.

**Ensuite, ce qui reste de P1**, par files : voir [l'ordre](P1-mise-en-prod.md#lordre). GEN-02 ouvre la file de la commande `station` : MAJ-04, prête, la suit, puis MAJ-05, SAV-01 et SUR-01. LEG-02 passe après GEN-02, FON-14 après le correctif du tirage, INS-04 sur la version suivante, et DOC-01 en dernier.

**À côté, dans P2**, ce qui n'attend rien de P1 :

- l'antenne, une fiche à la fois sur un même fichier. FON-17 puis FON-18, sur le pupitre (`desk.py`), n'attendent rien, mais pas en même temps que FON-14. FON-33 et FON-35 à FON-38 attendent le correctif du tirage, comme FON-14 : elles touchent `clock.py`. FON-19 et FON-32 touchent `execution.py`, que le correctif touche aussi : elles partent après lui, ou se rebasent ;
- les bacs et la banque : FON-16 puis FON-21, qui touchent le même inspecteur, FON-20 et FON-31 ;
- les fiches de la bibliothèque : FON-22, FON-23 et FON-24, l'une après l'autre, et ARC-06 à côté. FON-25 à FON-30 les suivent ;
- sans ordre, chacune avec ses conflits : FON-34, qui partage `alerts.py` avec SUR-01, TST-04, TST-05, DEV-01 à DEV-04, PUB-02, GEN-04, SEC-08, SEC-10 et ARC-01.

Le reste de P2 attend P1 : MAJ-06 et SUR-03 écrivent dans la commande `station`, MAJ-07 suit MAJ-06, MAJ-08 se mesure pendant une mise à jour, SUR-02 suit SUR-01, et SEC-09 relit le tout.

**Ce qui n'est pas du code**, et qu'une personne doit faire ou trancher :

- les réglages du dépôt, et le sort des cinq images encore privées (PUB-03) ;
- une clé d'application AcoustID pour BUTTON, avant FON-25 ;
- le nom des fichiers de l'export audio de Rivendell, avant FON-29 ;
- le format des relevés, confirmé par écrit par la SACEM et la SPRE, avant FON-01 ;
- avant le 29 janvier 2027, relire les onze failles acceptées de `.trivyignore.yaml` : passé cette date, le contrôle des failles échoue de nouveau.

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
