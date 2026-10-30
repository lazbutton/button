# 0006 · Le paquet reste `radiotomate`, une migration publiée ne bouge plus

Acceptée, octobre 2026.

## Contexte

Le moteur est un fork de Radiotomate. Ses migrations s'appliquent à chaque démarrage, sur des bases en service.

## Décision

- Le paquet Python, la commande et les imports gardent le nom `radiotomate`, pour la filiation et pour échanger avec l'amont.
- Une migration publiée ne se modifie jamais, même pour un nom ou un commentaire. Une évolution du schéma est une migration nouvelle, qui sait se défaire.

## Conséquences

- De vieilles migrations gardent des noms d'avant. On les laisse.
- Deux branches qui ajoutent chacune une migration prennent le même numéro. La deuxième à fusionner rebase et renumérote la sienne.
