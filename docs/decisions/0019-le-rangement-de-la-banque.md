# 0019 · Le rangement de la banque, à un seul endroit par composant

Acceptée, novembre 2026.

## Contexte

La banque de sons a gardé le rangement de la première station : `00-inbox`, `10-rotation`, `20-archives`, `30-habillage`, `40-emissions`, `50-carts`, `90-trash`, et les liens `Carts/`. Il a trois défauts.

- **Trois vocabulaires pour les mêmes choses.** Le disque dit `20-archives` et `50-carts`, le dossier partagé `Banques` et `Bacs`, la console « collection » et « bac ». « Archives » venait des enregistrements des éditions passées d'un événement, que gardait la première station ; une collection range aujourd'hui n'importe quel ensemble de titres à programmer à part.
- **La rotation et les collections sont traitées à part partout**, alors que pour Beets c'est la même chose : un dossier dont le nom devient le regroupement.
- **Les noms étaient écrits en dur dans près de soixante-dix fichiers** : le moteur, le catalogue, cinq scripts de la station, le dossier partagé, les docs et les tests. La console elle-même lisait les chemins : un bac d'habillage était un bac dont le dossier commence par `30-habillage`, et le bac d'un son à l'antenne se lisait dans `/50-carts/<n>/`.

Changer ces noms sur une station en service touche ce que l'antenne lit : les chemins des sons dans la base du moteur, la bibliothèque de Beets, les liens des bacs. Un tel changement demande une migration, un retour arrière et une version majeure.

## Décision

**Le rangement visé**, quand il se fera :

| Aujourd'hui | Visé | Contenu |
|---|---|---|
| `10-rotation/` | `collections/rotation/` | La rotation, collection par défaut |
| `20-archives/<nom>/` | `collections/<nom>/` | Les autres collections |
| `30-habillage/<type>/` | `habillage/<type>/` | Jingles, idents, pubs, beds, stings, sfx |
| `40-emissions/<émission>/` | `emissions/<émission>/` | Les émissions et les sets des invités |
| `50-carts/<n>/` | `bacs/<n>/` | Le dossier propre d'un bac |
| `00-inbox/…` | `depot/…` | L'arrivée des envois, au même chemin que la destination : `depot/collections/jazz/` va dans `collections/jazz/` |
| `90-trash/` | `corbeille/` | La corbeille de la banque |
| `Carts/` | `.volume/Bacs/` | Les liens vers le dossier de chaque bac, rangés avec la vue du dossier partagé |

Dans le dossier partagé, `Banques` devient `Collections` ; `Rotation` reste au premier niveau, comme dans la console.

**En deux étapes.**

1. **Rien ne bouge sur le disque** (ARC-07). Chaque composant nomme les dossiers à un seul endroit, et la console n'en nomme plus aucun :
   - le moteur dans `engine/radiotomate/services/media_bank.py` ;
   - le catalogue dans `services/catalog/layout.py` ;
   - chaque script de la station en tête de son fichier : `compose.yml` les monte un par un depuis le dossier de la station, et le correctif d'une image doit marcher avec les scripts de la version d'avant. `apply_share.py` les lit dans `refresh_volume.py`, construit dans la même image ;
   - `services/catalog/test_layout.py` compare ces endroits entre eux, et refuse un nom écrit ailleurs dans ces fichiers ; `engine/tests/test_media_bank.py` le refuse dans le reste du moteur, hors des migrations publiées ;
   - l'API dit à la console ce qu'elle lisait dans les chemins : la zone du dossier d'un bac (`bank_zone`), les dossiers d'habillage qu'un bac peut suivre (`habillage` de `/media/bank.json`), le bac du son à l'antenne et de chaque son qui suit (`cart_id` de `/live.json`), la zone et le dossier d'habillage d'un titre dans la recherche (`zone`, `habillage`), le dossier où naît une collection (`collections` d'`/inbox.json`) ;
   - face à un moteur ou à un catalogue plus ancien, la console lit encore les chemins, dans un seul module, `console/src/api/legacyLayout.ts`, à retirer à l'étape 2.
2. **Le nouveau rangement** (ARC-08), dans une version majeure. Au démarrage qui suit la mise à jour, la station renomme ses dossiers, sans copie, puis réécrit les chemins qu'elle garde ailleurs : `sounds.path`, `carts.bank_folder`, `music_categories.query` et les fichiers de l'Agenda dans la base du moteur, la bibliothèque de Beets sans réimport, les liens des bacs, l'état du pont Dropbox. Le retour arrière remet les anciens noms. Rien ne change si un de ces dossiers est un point de montage : la station le dit, et dit quoi faire.

## Conséquences

- L'étape 2 ne change que les endroits des noms, la migration et ses tests. La console ne change pas, sauf à retirer son module de repli.
- Les migrations publiées gardent les noms qu'elles ont écrits (ADR 0006) : `v9` (`path:/media/10-rotation`) et `v12` (`30-habillage/jingles`). La migration de l'étape 2 réécrit leurs valeurs, et sait les remettre.
- Un fichier qui nomme un dossier ailleurs qu'à son endroit fait échouer un test : le moteur, le catalogue, les scripts et la console.
- Une collection garde son nom de dossier, qui est son regroupement Beets : les sélections `grouping:<dossier>` ne changent pas. La rotation garde `grouping:rotation`.
- Les fiches : ARC-07, l'étape 1, et ARC-08, l'étape 2, dans [P2](../feuille-de-route/P2.md).
