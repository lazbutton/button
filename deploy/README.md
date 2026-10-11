# Déploiement

| Fichier | Rôle |
|---|---|
| [`compose.yml`](compose.yml) | La station complète : moteur, console, Icecast, titre en cours, catalogue, envoi reprenable |
| [`.env.example`](.env.example) | Modèle des variables : à copier en `.env`, qui reste hors de git |
| [`scripts/`](scripts/) | Initialisation de la station, banque de sons, sauvegarde et restauration |
| [`local/`](local/README.md) | Banc audio de test : Icecast et titre en cours seuls |

Le guide complet : [`docs/deploiement.md`](../docs/deploiement.md).

| Script | Rôle |
|---|---|
| `init-radiotomate.sh` | Premier démarrage et chaque démarrage : config, migrations, Beets, compte admin |
| `setup-media-tree.sh` | Crée l'arborescence de la banque de sons |
| `beets-import-loop.sh` | Boucle d'indexation de la banque (conteneur `radiotomate-dropbox`) |
| `promote-inbox.sh` | Range l'inbox dans la banque, à chaque tour de la boucle |
| `backup-radiotomate.sh`, `restore-radiotomate.sh` | Sauvegarde et restauration : [`docs/exploitation/sauvegarde.md`](../docs/exploitation/sauvegarde.md) |
