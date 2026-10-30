# 0002 · Une station par machine

Acceptée, octobre 2026.

## Contexte

Une installation qui gère plusieurs stations demande un moteur qui sépare les données de chacune, des comptes par station, et une mise à jour qui touche tout le monde à la fois.

## Décision

Par défaut, une machine porte une station : un dossier, une base, un `.env`. Plusieurs stations sur une machine restent possibles à la main, chacune avec son nom de projet Compose (`docker compose -p <station>`) et ses ports. Aucun outil ne gère ce cas.

## Conséquences

- L'installateur, la mise à jour et les sauvegardes ne connaissent qu'une station.
- Le moteur reste mono-station : pas de notion de station dans la base.
