# Décisions

Chaque fichier garde une décision d'architecture : ce qui a été choisi, pourquoi, et ce que ça coûte. Avant de revenir sur une de ces décisions, lire sa page. Pour en changer, écrire une décision nouvelle qui remplace l'ancienne : on ne réécrit pas l'histoire.

Une décision s'écrit quand un choix coûte cher à défaire, ou quand quelqu'un le remettra en question sans en connaître la raison.

| N° | Décision |
|---|---|
| [0001](0001-docker-compose-seul-format.md) | Docker Compose, seul format d'installation |
| [0002](0002-une-station-par-machine.md) | Une station par machine |
| [0003](0003-mettre-a-jour-par-des-versions.md) | Mettre à jour par des versions publiées |
| [0004](0004-la-console-ne-pilote-jamais-docker.md) | La console ne pilote jamais Docker |
| [0005](0005-le-fuseau-est-celui-des-conteneurs.md) | Le fuseau de la station est celui des conteneurs |
| [0006](0006-le-paquet-reste-radiotomate.md) | Le paquet reste `radiotomate`, une migration publiée ne bouge plus |
| [0007](0007-la-marque-est-une-configuration.md) | La marque est une configuration |
| [0008](0008-deux-conventions-d-heure.md) | Deux conventions d'heure en base |
| [0009](0009-interrupteurs.md) | Une fonction risquée a un interrupteur |
| [0010](0010-moteur-et-console-se-deploient-a-part.md) | Le moteur et la console se déploient à part |
| [0011](0011-liste-des-routes-dans-nginx.md) | Les routes du moteur passent par une liste dans nginx |
| [0012](0012-l-interface-est-en-francais.md) | L'interface est en français |
| [0013](0013-bloquer-l-adresse-jamais-le-compte.md) | Un échec de connexion bloque l'adresse, jamais le compte |
| [0014](0014-interrupteur-avant-le-moteur.md) | Avant le moteur, l'interrupteur est dans `.env` |
| [0015](0015-le-flux-passe-par-caddy.md) | Le flux passe par Caddy, sur le domaine de la console |

## Le gabarit

```markdown
# NNNN · Titre

Acceptée, mois année. Remplace NNNN, s'il y a lieu.

## Contexte

Ce qui pousse à choisir, en quelques phrases.

## Décision

Ce qui est choisi.

## Conséquences

Ce que ça permet, ce que ça coûte, et les fiches de la feuille de route qui en découlent.
```
