# 0003 · Mettre à jour par des versions publiées

Acceptée, octobre 2026.

## Contexte

Les stations suivent l'image `main`. Un commit qui passe la CI, mais qui se comporte mal à l'antenne, part donc partout. Un outil générique de mise à jour des conteneurs ne sait rien de la base, des directs prévus ni du retour arrière. Watchtower, le plus connu, est archivé depuis décembre 2025.

## Décision

Les stations installent des versions publiées, numérotées selon le versionnage sémantique, depuis un canal `stable`. Une commande à nous fait la mise à jour : elle attend une fenêtre sans direct, sauvegarde, met à jour, contrôle, et revient en arrière si le contrôle échoue, base comprise.

## Conséquences

- Fiches MAJ-01 à MAJ-05 de la feuille de route.
- Publier une version devient un geste : un tag, des notes, des fichiers joints.
- `main` sert au développement et aux essais, plus aux stations.
