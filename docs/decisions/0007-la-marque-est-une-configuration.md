# 0007 · La marque est une configuration

Acceptée, octobre 2026.

## Contexte

Le logiciel est né pour une station. Son nom, ses adresses et ses noms de mount se sont glissés dans le code et dans les fichiers de marque.

## Décision

Le logiciel ne porte aucune station. Le nom, les adresses, le logo et les liens d'une station sont des réglages ou une configuration montée, jamais du code. Le dépôt ne garde qu'une station d'exemple neutre, en `radio.example`.

## Conséquences

- Fiches GEN-01 à GEN-03 de la feuille de route.
- Une fonction qui n'a pas son réglage se cache et dit quoi régler, au lieu de prendre une adresse en repli.
