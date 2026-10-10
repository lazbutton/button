# Passer en direct

Une page pour un animateur. Le plateau entre par le harbor, la grille reprend toute seule.

## Avant

1. Un admin crée le compte dans Paramètres, avec la permission **Stream**.
2. Dans Auto-DJ, sur la semaine, l’émission porte le **nom exact** de ce compte dans « Identifiant du plateau ».
3. Tant qu’aucune émission ne nomme personne, tout compte Stream peut se brancher. Dès qu’une émission a un identifiant, chacun ne passe que pendant son créneau. Un admin passe toujours.

## Brancher BUTT

- Serveur : l’adresse de Nasgul sur le réseau de la radio, ou son adresse Tailscale.
- Port **6800**, type Icecast, mount `/stream`.
- Utilisateur et mot de passe du compte.
- MP3, 128 ou 192 kbit/s, 48 kHz.

Le titre à l’antenne devient le nom de l’émission, l’artiste la phrase.

## Sortir

Couper l’encodeur. Les files jingles et auto-DJ sont vidées, et le titre auto-DJ en cours est sauté : la grille reprend sur un morceau entier.

Si personne ne se branche, l’horloge continue. Au bout d’environ 90 secondes, la console signale l’encodeur absent. Il n’y a pas de silence à la place du créneau.

## Ce qui n’est pas encore fait

BUTT et Mixxx n’ont pas été tenus une heure sur l’antenne. Une coupure réseau de 30 secondes pendant un direct n’a pas été jouée. Nasgul tire encore l’ancien dépôt : ce comportement est dans le code et les tests, pas encore sur le flux public.
