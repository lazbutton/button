# 0008 · Deux conventions d'heure en base

Acceptée, octobre 2026.

## Contexte

Les tables de l'amont, et celles qui les suivent (journal d'antenne, conducteur, alertes), stockent l'heure locale naïve du conteneur. L'Agenda, lui, a besoin d'instants sûrs à travers les changements d'heure : une diffusion datée ne doit ni sauter ni doubler en mars et en octobre.

## Décision

- Les tables historiques gardent l'heure locale naïve, réglée par `TZ`.
- L'Agenda et les tables nouvelles stockent de l'UTC naïf.
- L'API de l'Agenda rend l'heure de Paris avec son décalage, par exemple `2026-11-07T22:00+01:00`.
- Les conversions passent par les fonctions de `engine/radiotomate/domain/agenda.py`.

## Conséquences

- On ne compare jamais deux heures de conventions différentes.
- Les tests tournent avec `TZ=Europe/Paris`, comme la CI.
