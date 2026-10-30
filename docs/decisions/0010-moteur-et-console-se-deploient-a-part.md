# 0010 · Le moteur et la console se déploient à part

Acceptée, octobre 2026.

## Contexte

La console est une image à part, servie par nginx. Pendant une mise à jour, ou après le retour arrière d'une seule image, une station peut avoir une console plus récente que son moteur, ou l'inverse.

## Décision

- L'API JSON du moteur est un contrat. Une route ne change de forme qu'avec la console, dans la même branche, et `docs/api.md` suit.
- On ajoute des champs sans rien casser. On ne retire ni ne renomme un champ sans période de transition. Une route qui change de sens prend un nouveau nom.
- Une console face à un moteur plus ancien survit : une route nouvelle qui répond 404 cache sa fonction, et la console affiche « Mets à jour le moteur », jamais une page blanche.
- Les pages HTMX d'origine, servies par l'interface du moteur, continuent de marcher.

## Conséquences

- Les parcours de bout en bout simulent une route absente. Voir TST-02.
- Une fonction nouvelle demande parfois deux versions : le moteur d'abord, puis la console qui s'en sert.
