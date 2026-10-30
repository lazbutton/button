# 0013 · Un échec de connexion bloque l'adresse, jamais le compte

Acceptée, octobre 2026.

## Contexte

Une console exposée à Internet doit freiner qui essaie des mots de passe. Le blocage le plus courant vise le compte : après quelques échecs, l'identifiant est verrouillé. Mais l'identifiant d'un animateur se devine, et son direct a une heure connue. N'importe qui pourrait verrouiller son compte juste avant l'antenne, en tapant de faux mots de passe à son nom.

## Décision

- Les échecs de connexion se comptent par adresse IP. Au-delà du seuil, l'adresse est bloquée pour tous les identifiants.
- Un identifiant n'est jamais bloqué, quel que soit le nombre d'échecs à son nom.
- Derrière un reverse proxy, l'adresse comptée est celle du client, transmise par nginx. Sinon, tous les essais sembleraient venir de la même adresse.

## Conséquences

- Un attaquant qui dispose de nombreuses adresses n'est freiné que par la limite de chacune. La solidité des mots de passe et la double authentification des admins (SEC-08) couvrent ce cas.
- Des personnes derrière la même adresse partagent le compteur : les erreurs répétées de l'une bloquent les autres un moment.
- La fiche SEC-03 suit cette décision.
