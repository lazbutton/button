# 0005 · Le fuseau de la station est celui des conteneurs

Acceptée, octobre 2026.

## Contexte

Le moteur de l'amont prend l'heure locale du processus, et l'antenne vit à l'heure murale : une émission de 20 h passe à 20 h, l'hiver comme l'été.

## Décision

Le fuseau d'une station est la variable `TZ` de ses conteneurs, choisie à l'installation, `Europe/Paris` par défaut. La console l'affiche en lecture seule ; elle ne le règle pas.

## Conséquences

- Changer de fuseau après coup demanderait de convertir les heures locales stockées : ce n'est pas prévu.
- Une partie du code, l'Agenda en tête, écrit encore l'heure de Paris en dur. Une station hors de ce fuseau attend ARC-02.
