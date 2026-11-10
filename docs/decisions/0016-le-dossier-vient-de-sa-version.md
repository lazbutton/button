# 0016 · Le dossier d'une station vient des fichiers joints à sa version

Acceptée, novembre 2026.

## Contexte

`station install` installe une station sur un VPS neuf, sans clone du dépôt (fiche INS-02). Le dossier de la station doit pourtant suivre la version de ses images, pour deux raisons :

- `compose.yml` monte des scripts du dossier dans les conteneurs, comme `init-radiotomate.sh` ;
- il garde des sections `build:` qui visent les sources.

Trois voies se présentaient :

- joindre des fichiers à chaque version publiée, comme le prévoyaient la décision [0003](0003-mettre-a-jour-par-des-versions.md) et la fiche MAJ-04 ;
- prendre l'archive des sources que GitHub sert pour chaque tag, et en extraire `deploy/` ;
- mettre les scripts dans les images, et ne garder à part que `compose.yml`.

## Décision

- **Les fichiers joints.** Chaque version publiée joint trois fichiers à sa page :
  - `station`, le script d'exploitation ;
  - `station.tar.gz`, le dossier d'une station à cette version : `compose.yml` sans ses sections `build:`, le `Caddyfile`, `.env.example`, les scripts de `deploy/scripts/`, `station` et `VERSION` ;
  - `SHA256SUMS`, les sommes des deux.
- **Leur fabrication.** `scripts/version.py station` les fabrique. `version.yml` les joint pendant que la page est encore un brouillon, avant que `X.Y` et `stable` bougent.
- **`stable`.** Pour `station install`, c'est la version marquée « Latest » sur GitHub : `version.yml` ne donne cette marque qu'à la version qui prend `stable`.
- **L'installation.** `install` vérifie la somme, pose les fichiers, puis épingle la version dans `.env`. Une relance reprend la version de `.env`, jamais une autre.
- **Les images ne changent pas.** Le dépôt garde ses sections `build:`, pour le développement.

## Conséquences

- **Aucun jeton pour les fichiers.** Le dépôt est public. Le jeton GHCR ne sert qu'aux images encore privées.
- **La 0.1.0 ne s'installe pas ainsi.** Elle est publiée avant cette décision, sans ces fichiers. La première version installable par `station install` est la suivante. D'ici là, `releases/latest/download/station` ne trouve rien.
- **Un essai de `main`.** Hors d'une version publiée, l'archive se fabrique depuis un clone, par `python3 scripts/version.py station main <dossier>`. `station install --from` la prend ensuite.
- **Les commandes suivantes.** `update` (MAJ-04) et `rollback` (MAJ-05) prendront les fichiers de la même façon. Revenir à une version, c'est reprendre son archive.
- **Plus de build sur une station.** Une station n'a pas les sources : une image qui manque fait échouer `docker compose`, au lieu de lancer un build impossible.
- **Un fichier monté doit être dans l'archive.** Tout fichier que `compose.yml` monte depuis le dossier doit être dans `station.tar.gz` : sinon, `scripts/version.py station` refuse.
- **Les scripts restent dans le dossier**, pas dans les images. Un correctif d'image marche toujours avec le dossier de la version d'avant : voir les pièges de [deploy/AGENTS.md](../../deploy/AGENTS.md#pièges).
