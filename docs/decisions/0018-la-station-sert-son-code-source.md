# 0018 · La station sert le code source de sa version

Acceptée, novembre 2026.

## Contexte

L'AGPL demande de proposer le code source de la version en service à chaque personne qui se sert de la console à distance, animateurs compris (fiche LEG-02). Le lien « Code source » du menu du compte menait à la racine du dépôt, pas au code de cette version.

Trois voies se présentaient :

- un lien vers le tag de la version sur GitHub, dont la page joint déjà une archive du code ;
- une archive jointe à chaque version, et un lien vers elle sur GitHub ;
- la même archive, servie par la station elle-même.

Les deux premières ne tiennent que tant que le dépôt reste public et que GitHub répond. Or une station peut tourner des années sur sa version, et l'obligation pèse sur elle, pas sur le dépôt.

## Décision

- **L'archive.** `scripts/version.py source` fait l'archive du code du commit, `button-X.Y.Z-source.tar.gz`, par `git archive`, et `source.json`, qui la nomme. Pour un même commit, avec les mêmes outils, les mêmes octets d'une fois à l'autre.
- **La version.** `version.yml` joint l'archive à la page de chaque version publiée, avec les fichiers d'une station.
- **L'image de la console.** `console.yml` passe les deux fichiers au build de l'image, comme contexte `source`. Ils remplacent une étape vide du Dockerfile : une image construite sans eux, par `docker compose build` par exemple, n'en a pas. Le Dockerfile donne aussi à l'archive un nom qui ne change pas d'une version à l'autre, `source.tar.gz`.
- **nginx** les sert sous `/code-source/`, hors de la racine du site, à une session seulement (`auth_request`), comme le catalogue.
- **La console** lit `source.json` une fois connectée, puis à chaque ouverture du menu du compte : une mise à jour change l'archive sous une page restée ouverte. Le lien télécharge `source.tar.gz`, sous le nom de l'archive de la version ; sans archive, il mène au dépôt. Le réglage `source_url` de la station, dans Réglages → Station, passe devant les deux : une station qui sert une version modifiée y donne l'adresse de son code.

## Conséquences

- **Le code reste joignable** même si le dépôt devient privé, ou si GitHub ne répond pas : la station le sert à chaque compte, sans compte GitHub.
- **L'image de la console grossit** de l'archive, 4 Mo environ.
- **Sur `main`, l'archive suit la console.** L'image de la console ne se reconstruit que quand `console/` change : sur une station d'essai qui suit `main`, l'archive peut être celle d'un commit plus ancien que le moteur. Une version publiée reconstruit toutes ses images depuis son tag : son archive est exacte.
- **Une version modifiée** construite par les mêmes workflows porte son propre code. Construite autrement, elle règle `source_url`.
- **La page d'un invité de l'Agenda** n'a pas de lien « Code source », et l'archive demande une session : l'invité n'y accède pas encore. C'est une fiche à ouvrir dans la feuille de route.
