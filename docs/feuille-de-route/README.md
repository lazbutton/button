# Feuille de route

Ce qui reste à faire, rangé par priorité. Chaque tâche est une **fiche** : assez précise pour qu'un agent la prenne seul, assez petite pour une branche.

| Priorité | Page | Pour |
|---|---|---|
| P1 | [P1-mise-en-prod.md](P1-mise-en-prod.md) | Mettre une station en production sur une machine exposée à Internet, l'installer en une commande, la mettre à jour sans casser l'antenne |
| P2 | [P2.md](P2.md) | Le confort d'exploitation, et ce qui entoure la publication du logiciel |
| P3 | [P3.md](P3.md) | Plus tard : les fonctions, dans l'ordre que les radios demanderont |

## Où on en est

Relevé le 15 novembre 2026, sur `main` après la PR 251. La dernière version publiée est la 2.0.0, du 15 novembre : le rangement de la banque, en entier. P1 a 28 fiches faites sur 30, P2 soixante sur 113. Aucune fiche n'a de pull request ouverte. La personne qui fusionne tient cette partie à jour, comme les tableaux.

**D'abord** :

1. **PUB-03, les réglages du dépôt public.** Les sept images sont publiques, mais le signalement privé des failles reste éteint, alors que `SECURITY.md` y envoie, et `main` n'est pas protégée : relevé le 15 novembre 2026. Ils se posent en quelques minutes, par la personne qui tient le dépôt.
2. **FON-89, puis FON-90**, sur `clock.py`. Leurs défauts, autour d'une coupure « Coupe pile », font rougir le banc du conducteur : cinq passages sur trente le 14 novembre 2026, sur des branches qui ne touchent pas à l'antenne.

**Ensuite, ce qui reste de P1**, par files : voir [l'ordre](P1-mise-en-prod.md#lordre). INS-04 se mesure maintenant, sur la 2.0.0, et DOC-01 vient en dernier.

**À côté, dans P2**, ce qui n'attend rien de P1 :

- l'antenne, une fiche à la fois sur un même fichier : FON-50 sur le pupitre (`desk.py`) ; après FON-89 et FON-90, FON-35, FON-37, FON-38, FON-51 et FON-56 sur `clock.py` ; FON-55 et FON-57 sur `live.py` ; FON-19 et FON-62 sur `execution.py`, que FON-90 touche aussi. FON-53, FON-58 à FON-61 et FON-63 viennent de changer ces fichiers : rejouer chaque défaut avant de coder ;
- les bacs et la banque : FON-21, FON-31, FON-52 sur `promote-inbox.sh`, et FON-20 et FON-40, ces deux-là l'une après l'autre, sur le script du pont Dropbox ;
- la suite du rangement de la banque, fait dans la 2.0.0 : ARC-08, le nouveau rangement sur le disque, qui touche aussi les scripts de l'hôte et la commande `station`, et passe donc seule dans ces fichiers ; FON-91, sur le plugin Beets du moteur ; FON-29, qui attend le nom des fichiers de l'export de Rivendell ; le banc de TST-16, passé sur 29 vrais titres, qui attend une copie de quelques centaines ;
- sans ordre, chacune avec ses conflits : FON-47 sur la page Semaine, FON-44, sur `alerts.py`, TST-04, TST-13, TST-07 et FON-41, qui touchent le même parcours, DEV-05 et TST-12, l'une après l'autre sur `scheduler_api.py`, INS-05, FON-46, DEV-01 à DEV-04, PUB-02, LEG-03, GEN-04, SEC-08, SEC-10, SEC-11 sur nowplaying, SEC-12 et FON-54 sur le script du playout, ARC-01, et MAJ-08, que MAJ-04 ne retient plus.

Dans la commande `station`, une fiche à la fois : MAJ-06, les mises à jour de la nuit, MAJ-09, TST-10, SUR-03 et ARC-08. SUR-02 peut passer. SEC-09 relit le tout à la fin.

**Ce qui n'est pas du code**, et qu'une personne doit faire ou trancher :

- faire dans chaque station l'action que demande la 2.0.0, dite dans la « Mise en service » du [CHANGELOG](../../CHANGELOG.md) : `station update --major`, puis réécrire en `grouping:` les sélections de titres qui lisent `genre:Archive`. Le rangement écrit dans les fichiers : prévenir l'équipe, ou le couper le temps de le faire ;
- essayer sur une station ce que les bancs de la 2.0.0 n'ont pas vu, dit dans ses notes : un bac de titres de la banque joué, un son copié dans deux bacs, une fiche acceptée entendue à son passage suivant, une sélection `famille:jazz` qui puise à l'antenne, une nuit de recherche sur 7 000 titres ;
- sur chaque station, régler la sauvegarde hors de la machine (`station config --backup-remote`), chez un autre fournisseur que celui du VPS, et noter le mot de passe du dépôt hors de la machine ;
- essayer FON-14 et FON-39 sur une station de test, fondu allumé : leur banc tournait sans. Pour FON-39, une heure d'antenne ;
- essayer LEG-02 sur une station d'essai en `main` : un animateur y télécharge le code de la version, et sans session la même adresse répond 401 ;
- les réglages du dépôt (PUB-03) ;
- une copie de quelques centaines de fichiers de la banque d'une station, de formats variés, sur la machine de développement, hors du dépôt, pour TST-16 : celle d'aujourd'hui compte 29 MP3 ;
- les droits et les conditions d'usage des pochettes des plateformes, avant d'allumer celles de FON-83 ;
- l'adresse du service de liens d'écoute et sa clé partenaire, avant d'allumer FON-84 ;
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
