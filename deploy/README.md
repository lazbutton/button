# Déploiement

| Fichier | Rôle |
|---|---|
| [`compose.yml`](compose.yml) | La station complète : moteur, console, Icecast, titre en cours, catalogue, envoi reprenable |
| [`.env.example`](.env.example) | Modèle des variables : à copier en `.env`, qui reste hors de git |
| [`scripts/`](scripts/) | Initialisation de la station, banque de sons, dossier partagé, sauvegarde et restauration |
| [`share/`](share/) | Image du dossier partagé (Samba), lancée seulement avec `--profile share` |
| [`local/`](local/README.md) | Banc audio de test : Icecast et titre en cours seuls |

Le guide complet : [`docs/deploiement.md`](../docs/deploiement.md). Pour travailler dans ce dossier : [AGENTS.md](AGENTS.md).

| Script | Rôle |
|---|---|
| `init-radiotomate.sh` | Premier démarrage et chaque démarrage : config, migrations, Beets, compte admin |
| `setup-media-tree.sh` | Crée l'arborescence de la banque de sons |
| `beets-import-loop.sh` | Boucle d'indexation de la banque (conteneur `radiotomate-dropbox`) |
| `promote-inbox.sh` | Range l'inbox dans la banque, à chaque tour de la boucle |
| `refresh_volume.py` | Reconstruit la vue Finder de la banque : des liens vers les dossiers réels |
| `export_share_roles.py` | Écrit les rôles des comptes pour le dossier partagé, sans aucun mot de passe |
| `backup-radiotomate.sh`, `restore-radiotomate.sh` | Sauvegarde et restauration, sur l'hôte : [`docs/exploitation/sauvegarde.md`](../docs/exploitation/sauvegarde.md) |

Dans `share/`, `apply_share.py` crée les comptes Samba et verrouille les dossiers ; `entrypoint.sh` refuse une écoute sur `0.0.0.0`, sauf avec `SMB_ALLOW_PUBLIC=1`. Le dossier partagé est décrit dans [`docs/exploitation/dossier-reseau.md`](../docs/exploitation/dossier-reseau.md).
