# 0014 · Avant le moteur, l'interrupteur est dans `.env`

Acceptée, octobre 2026. Complète 0009.

## Contexte

La décision [0009](0009-interrupteurs.md) coupe une fonction risquée par une clé `features.*` de la table `settings`, qu'un admin change dans la console. Le contrôle des secrets de `radiotomate-init` (SEC-06) tourne avant le moteur et avant les migrations. Quand il bloque, la console est éteinte. À la première installation, la base n'existe même pas. Une clé de la base ne peut donc pas le couper.

## Décision

- Un contrôle qui tourne avant le moteur se coupe par une variable de `deploy/.env`, que `compose.yml` transmet. Seule la valeur `1` le coupe.
- Un contrôle de sécurité refuse par défaut : sans la variable, la station ne démarre pas. Un défaut qui laisse passer ce que le contrôle doit arrêter ne protégerait personne.
- Couper un contrôle l'adoucit sans l'effacer : il avertit dans le journal à chaque démarrage. Ce qui ne doit jamais passer, comme `change-me`, reste refusé.
- Le premier interrupteur qui suit cette décision est `RT_ALLOW_SHORT_SECRETS` : un secret de machine de moins de 24 caractères avertit au lieu de bloquer.

## Conséquences

- Contrairement à 0009, l'absence de la variable peut arrêter une station en service qui passe à une version nouvelle. La ligne du CHANGELOG dit alors quoi vérifier avant la mise à jour.
- Couper le contrôle demande un accès à la machine, pas un compte admin.
- Chaque interrupteur a un test contrôle coupé et un test contrôle actif, comme le veut 0009.
- `SMB_ALLOW_PUBLIC=1`, plus ancien, lève déjà un refus du dossier partagé par une variable de `.env`, mais sans le rappeler dans le journal à chaque démarrage.
