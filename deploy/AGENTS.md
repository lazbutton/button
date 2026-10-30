# Consignes pour le déploiement

À lire avec le [AGENTS.md](../AGENTS.md) de la racine. Le guide d'installation est [docs/deploiement.md](../docs/deploiement.md).

## Vérifier

```bash
../scripts/verifier.sh deploy    # docker compose config avec .env.example, ShellCheck si installé
```

Rien de ce dossier ne se lance contre une station en service. Les essais se font sur le banc local ou sur une machine jetable.

## compose.yml

- Le projet Compose s'appelle `button` (`name: button`). Le renommer recrée vides les volumes nommés `button_tusd-data` et `button_share-private`, et change le nom des conteneurs que citent des scripts et des docs.
- L'interface et le scheduler partagent le réseau du playout (`network_mode: service:radiotomate-playout`). **On ne redémarre jamais `radiotomate-playout` seul** : on recrée les trois services du moteur ensemble.
- `RT_TAG` épingle seulement le moteur et le playout. Les autres images suivent `:main` tant que la fiche MAJ-01 n'est pas faite.
- **Docker contourne le pare-feu.** Un port publié sur toutes les interfaces reste joignable même si ufw le ferme. Sur une machine exposée, lier les ports à `127.0.0.1` (par exemple `CONSOLE_PORT=127.0.0.1:30126`) et vérifier depuis une autre machine, pas avec `ufw status`.
- Une variable nouvelle a une valeur par défaut dans `compose.yml` (`${NOM:-défaut}`) et une ligne commentée dans `.env.example`. Un secret vaut `change-me` dans l'exemple, jamais une vraie valeur.
- Le service `share` ne démarre qu'avec `--profile share`. `SMB_BIND` n'est jamais `0.0.0.0` : `share/entrypoint.sh` le refuse, sauf avec `SMB_ALLOW_PUBLIC=1`, qui n'a pas sa place sur une machine exposée.
- Les images sont construites pour `linux/amd64` seulement : une machine ARM ne les lance pas.

## Les scripts

| Où tourne le script | Forme |
|---|---|
| Dans un conteneur : `init-radiotomate.sh`, `beets-import-loop.sh`, `promote-inbox.sh`, `setup-media-tree.sh`, `share/entrypoint.sh` | `#!/bin/sh` et `set -eu` : POSIX, sans bash |
| Sur l'hôte : `backup-radiotomate.sh`, `restore-radiotomate.sh` | `#!/usr/bin/env bash` et `set -euo pipefail` |

- Un script se relance sans danger : il ne refait que ce qui manque, et n'écrase rien.
- Un nouveau script de l'hôte n'a besoin que de Docker, de curl et d'openssl. Les deux scripts de sauvegarde demandent aussi `sqlite3` et `tar` sur l'hôte.
- Chaque message d'erreur dit quoi faire ensuite.
- ShellCheck passe sur chaque script.
- Les tests de `restore-radiotomate.sh` sont dans `engine/tests/test_update_backup.py`, avec la copie qu'il remet : après une modification du script, lancer aussi `../scripts/verifier.sh moteur`. La CI du moteur ne se déclenche pas pour `deploy/`.
- Les scripts Python (`export_share_roles.py`, `refresh_volume.py`, `share/apply_share.py`) n'utilisent que la bibliothèque standard. Leurs tests sont dans `services/catalog/` (`test_share.py`, `test_refresh_volume.py`).

## Pièges

- `init-radiotomate.sh` tourne à chaque démarrage : il applique les migrations du schéma. Revenir à une image plus ancienne demande de redescendre le schéma d'abord : [docs/deploiement.md](../docs/deploiement.md#revenir-en-arrière). Une migration ratée ne laisse rien, mais celles passées avant elle au même démarrage restent, et l'image d'avant ne lit plus la base : [docs/exploitation/sauvegarde.md](../docs/exploitation/sauvegarde.md#remettre-la-copie).
- `deploy/local/` est un banc audio avec des mots de passe de test publics. Il ne sert jamais pour une station.
