# Déploiement

| Fichier | Rôle |
|---|---|
| [`station`](station) | La commande d'une station sur un VPS : `station install` l'installe en une commande, et la répare. Voir [`docs/deploiement.md`](../docs/deploiement.md#installer-sur-un-vps) |
| [`compose.yml`](compose.yml) | La station complète : moteur, console, Icecast, titre en cours, catalogue, envoi reprenable |
| [`.env.example`](.env.example) | Modèle des variables : à copier en `.env`, qui reste hors de git |
| [`Caddyfile`](Caddyfile) | HTTPS sur Internet : Caddy devant la console, le flux et `now.json`, avec `--profile vps` |
| [`scripts/`](scripts/) | Initialisation de la station, banque de sons, dossier partagé, pont Dropbox, sauvegarde et restauration |
| [`share/`](share/) | Image du dossier partagé (Samba), lancée seulement avec `--profile share` |
| [`local/`](local/README.md) | Banc audio de test : Icecast et titre en cours seuls |
| [`tests/`](tests/) | Les tests de `station`, avec `bats`, sur une machine jouée par de faux outils |

Le guide complet : [`docs/deploiement.md`](../docs/deploiement.md). Pour travailler dans ce dossier : [AGENTS.md](AGENTS.md).

| Script | Rôle |
|---|---|
| `init-radiotomate.sh` | Premier démarrage et chaque démarrage : secrets, config, migrations, Beets, compte admin |
| `setup-media-tree.sh` | Crée l'arborescence de la banque de sons |
| `beets-import-loop.sh` | Boucle d'indexation de la banque (conteneur `radiotomate-dropbox`) |
| `promote-inbox.sh` | Range l'inbox dans la banque, à chaque tour de la boucle |
| `refresh_volume.py` | Reconstruit la vue Finder de la banque : des liens vers les dossiers réels |
| `export_share_roles.py` | Écrit les rôles des comptes pour le dossier partagé, sans aucun mot de passe |
| `cloud-sync.sh` | Copie dans son bac un son déposé dans Dropbox, avec `--profile cloud` (conteneur `cloud-sync`) : [`docs/exploitation/bacs-dropbox.md`](../docs/exploitation/bacs-dropbox.md) |
| `backup-radiotomate.sh`, `restore-radiotomate.sh` | Sauvegarde et restauration, sur l'hôte : [`docs/exploitation/sauvegarde.md`](../docs/exploitation/sauvegarde.md) |

Dans `share/`, `apply_share.py` crée les comptes Samba et verrouille les dossiers ; `entrypoint.sh` refuse une écoute sur `0.0.0.0`, sauf avec `SMB_ALLOW_PUBLIC=1`. Le dossier partagé est décrit dans [`docs/exploitation/dossier-reseau.md`](../docs/exploitation/dossier-reseau.md).
