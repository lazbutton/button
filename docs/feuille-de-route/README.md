# Feuille de route

Ce qui reste à faire, rangé par priorité. Chaque tâche est une **fiche** : assez précise pour qu'un agent la prenne seul, assez petite pour une branche.

| Priorité | Page | Pour |
|---|---|---|
| P1 | [P1-mise-en-prod.md](P1-mise-en-prod.md) | Mettre une station en production sur une machine exposée à Internet, l'installer en une commande, la mettre à jour sans casser l'antenne |
| P2 | [P2.md](P2.md) | Le confort d'exploitation, et ce qui entoure la publication du logiciel |
| P3 | [P3.md](P3.md) | Plus tard : les fonctions, dans l'ordre que les radios demanderont |

## Où on en est

Relevé le 12 novembre 2026, sur `main` après la PR 165. La dernière version publiée est la 0.2.0, du 10 novembre. P1 a 26 fiches faites sur 29, P2 seize sur 64. En cours : SUR-01, en P1, et FON-36 et TST-11, en P2. La personne qui fusionne tient cette partie à jour, comme les tableaux.

**D'abord** :

1. **La version qui suit la 0.2.0 : la 1.0.0.** Plus rien ne la retient : le correctif du tirage des bacs est fusionné (`550e7f1`). Elle porte ce qu'il faut à une station neuve : la banque de sons rendue au moteur, et un conducteur qui ne s'empile plus. Elle rend à l'antenne les lignes mises à la suite au pupitre et les jingles du motif (FON-14, FON-39), qu'il reste à écouter sur une station de test. Elle apporte aussi `station update` (MAJ-04), son retour arrière (MAJ-05) et la sauvegarde hors de la machine (SAV-01), que la 0.2.0 n'a pas : une station d'aujourd'hui prend d'abord la commande de cette version, comme le dit [deploiement.md](../deploiement.md#avec-la-commande-station). Elle demande une action à chaque station, dite dans la « Mise en service » du [CHANGELOG](../../CHANGELOG.md) : régler ses adresses dans Réglages → Station, et poser `ICECAST_MOUNT=button.mp3` dans `.env` pour garder l'adresse de son flux. Une version qui demande une action est une majeure ([developpement.md](../developpement.md#publier-une-version)) : décidé le 11 novembre, elle se publie en 1.0.0.
2. **PUB-03, les réglages du dépôt public.** Ils se posent en quelques minutes, par la personne qui tient le dépôt.
3. **SUR-01**, les alertes sur le téléphone et par e-mail, en cours : SAV-01 est fusionnée, et SUR-01 est la dernière fiche de la file de la commande `station`. Tant qu'elle manque, une alerte reste dans le journal de la machine, où personne ne la lit.

**Ensuite, ce qui reste de P1**, par files : voir [l'ordre](P1-mise-en-prod.md#lordre). SUR-01 finit la file de la commande `station`. INS-04 se mesure sur la version suivante, et DOC-01 vient en dernier.

**À côté, dans P2**, ce qui n'attend rien de P1 :

- l'antenne, une fiche à la fois sur un même fichier : FON-18 sur le pupitre (`desk.py`) ; FON-36, en cours, puis FON-35, FON-37, FON-38 et FON-49 sur `clock.py` ; FON-19 sur `execution.py`. FON-14, FON-39, FON-33 et FON-32 viennent de changer ces fichiers : rejouer chaque défaut avant de coder ;
- les bacs et la banque : FON-21, FON-31, et FON-20 et FON-40, ces deux-là l'une après l'autre, sur le script du pont Dropbox ;
- les fiches de la bibliothèque : ARC-06, puis FON-25, qui attend aussi une clé AcoustID pour BUTTON. FON-26 à FON-30 les suivent ;
- sans ordre, chacune avec ses conflits : FON-47 sur la page Semaine, FON-44 après SUR-01, qui partage `alerts.py`, TST-04, TST-11, en cours, TST-07 et FON-41, qui touchent le même parcours, DEV-05 et TST-12, l'une après l'autre sur `scheduler_api.py`, TST-10 et INS-05 après SUR-01, qui écrit aussi dans `deploy/`, FON-48, FON-46, DEV-01 à DEV-04, PUB-02, LEG-03, GEN-04, SEC-08, SEC-10, ARC-01, et MAJ-08, que MAJ-04 ne retient plus.

Le reste de P2 attend P1 : MAJ-06 et SUR-03 écrivent dans la commande `station`, MAJ-07 suit MAJ-06, SUR-02 suit SUR-01, et SEC-09 relit le tout.

**Ce qui n'est pas du code**, et qu'une personne doit faire ou trancher :

- publier la 1.0.0, et faire dans chaque station l'action qu'elle demande ;
- sur chaque station, régler la sauvegarde hors de la machine (`station config --backup-remote`), chez un autre fournisseur que celui du VPS, et noter le mot de passe du dépôt hors de la machine ;
- essayer FON-14 et FON-39 sur une station de test, fondu allumé : leur banc tournait sans. Pour FON-39, une heure d'antenne ;
- essayer LEG-02 sur une station d'essai en `main` : un animateur y télécharge le code de la version, et sans session la même adresse répond 401 ;
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

Un besoin nouveau, ou un défaut vu en passant : une fiche dans la bonne page, avec le prochain numéro libre de son thème. Chercher d'abord le sujet dans les trois pages et dans les [décisions](../decisions/README.md) : il a peut-être déjà sa fiche, ou sa réponse. Une fiche trop vague reste une question : la poser plutôt que deviner.
