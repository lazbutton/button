# 0001 · Docker Compose, seul format d'installation

Acceptée, octobre 2026.

## Contexte

Une station tient en une dizaine de services : le moteur en trois processus, la console, Icecast, le titre en cours, le catalogue, Meilisearch et tusd. Chaque format d'installation de plus, paquet Debian ou YunoHost, est un chemin de plus à tester et à mettre à jour. AzuraCast, qui fait le même métier, ne propose que Docker.

## Décision

Une station s'installe et se met à jour par Docker Compose, avec les images publiées par la CI. Il n'y a ni paquet Debian ni YunoHost. L'installateur Podman de l'amont reste dans `engine/`, mais ce n'est pas un chemin pris en charge.

## Conséquences

- Un seul chemin à tester, sur une machine jetable.
- Docker contourne le pare-feu ufw : un port publié sur toutes les interfaces reste ouvert. Voir SEC-07.
- Les images ne sont construites que pour `linux/amd64`. Voir ARC-04.
