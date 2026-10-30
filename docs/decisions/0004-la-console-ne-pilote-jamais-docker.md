# 0004 · La console ne pilote jamais Docker

Acceptée, octobre 2026.

## Contexte

Certaines actions demandées depuis la console touchent la machine : lancer une mise à jour, par exemple. Le plus court serait de donner le socket Docker à un conteneur. Mais un conteneur exposé à Internet qui a le socket Docker donne la machine entière à qui le compromet.

## Décision

Aucun conteneur n'a accès au socket Docker. Une action sur la machine demandée depuis la console s'écrit dans le moteur, comme une demande. Un minuteur de l'hôte lit les demandes par `docker compose exec`, les exécute, puis écrit le résultat par le même chemin. La console affiche ce résultat.

## Conséquences

- Une action de la console sur la machine prend jusqu'à une minute avant de commencer.
- Le minuteur de l'hôte fait partie de l'installation. Voir MAJ-07.
