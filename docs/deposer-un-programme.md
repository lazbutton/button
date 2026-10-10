# Déposer un programme

Le collectif dépose des fichiers. La banque les prend sans les retaper.

## Où poser le fichier

Le Nextcloud de Nasgul voit déjà la banque BUTTON (`BUTTON Media`, même dossier que le partage `BUTTON-Media`).

| Quoi | Dossier |
| --- | --- |
| Titre pour la rotation | `00-inbox/rotation/` |
| Archive édition 1, 2 ou 3 | `00-inbox/archives/ntf1/`, `ntf2/` ou `ntf3/` |

Nommer le fichier `Artiste - Titre.mp3` (ou flac, ogg, opus, m4a). Un wav ou un aiff est converti en flac. Un autre format est laissé sur place et ignoré.

## Ce qui se passe ensuite

Le conteneur dropbox, à chaque tour (environ 45 s) :

1. déplace le fichier vers `10-rotation/` ou `20-archives/ntfN` ;
2. laisse l’original non tagué dans `00-inbox/_sources/` ;
3. laisse Beets indexer, avec le regroupement `rotation` ou `ntf1` / `ntf2` / `ntf3`.

Une cible déjà présente n’est pas écrasée.

La commande manuelle reste :

```
docker exec button-radiotomate-dropbox-1 sh /promote-inbox.sh --dry-run
docker exec button-radiotomate-dropbox-1 sh /promote-inbox.sh
```

Ce tour automatique est dans le dépôt d’exploitation. Il tourne sur Nasgul quand le conteneur dropbox est recréé depuis ce dépôt. Les archives réelles des éditions 1 à 3 ne sont pas encore dans la banque : les dossiers du banc local contiennent des tons nommés `REMPLACANT`.
