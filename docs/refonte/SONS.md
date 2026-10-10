# Refonte de la page Sons — ntr-console

> Spec de la refonte de `/sons`. À placer dans le repo (ex. `docs/refonte/SONS.md`). Complète, ne remplace pas, le contrat moteur du PLAN. La page existe déjà (quatre onglets) ; cette refonte les ramène à deux, sans rien perdre.

## Principe

1. **Deux onglets.** Tes **bacs** de sons, et la **banque** commune. Fini les quatre onglets dont deux montraient les mêmes carts.
2. **Une source, un endroit.** Fichiers, habillage et relais vivent dans une seule liste, triée par un filtre — plus de vue en double.
3. **Trois gestes d'ajout, bien séparés.** Ajouter des fichiers à un bac, attacher un dossier de la banque, ou déposer dans la banque : chacun son nom, chacun sa place.
4. **Des mots simples.** « cart » → « bac de sons » ; « Importer » → « Banque ». Le code garde ses noms.

## Les trois façons d'ajouter des sons (à ne pas confondre)

```
Ton ordinateur  --Ajouter---------------->  Un bac         (copie dans le bac)
La banque       --Attacher (sans copie)-->  Un bac         (lien, pas de copie)
Ton ordinateur  --Déposer-->  La banque  --Beets indexe-->  Dispo partout
```

- **Ajouter** copie des fichiers dans un bac. **Attacher** relie un dossier de la banque à un bac, sans copier. **Déposer** envoie dans la banque commune (onglet Banque), où Beets indexe pour toute la station.

## Onglet Bacs — toutes les sources en un endroit

Fusion de Carts + Habillage + Relais en une liste, avec un filtre par type. L'éditeur s'adapte au type du bac.

```
┌ Bacs ────────────────┐ ┌ Jingles · Aléatoire             ▶ Maintenant ┐
│ Tous·Fichiers·        │ │ ▶ Jingle 1                       00:03  ☑    │
│   Habillage·Relais    │ │ ▶ Jingle 2                       00:03  ☑    │
│ + Nouveau             │ │ ▶ Jingle 3                       00:03  ☑    │
│ ▸ Jingles   fichiers  │ │ + Ajouter des fichiers  + Attacher un dossier│
│   Virgules  fichiers  │ │ Réglages                                     │
│   Radio Zef relais    │ │   Mode : Aléatoire                           │
│                       │ │   (dossier banque, Finder, pads — avancé)    │
└───────────────────────┘ └──────────────────────────────────────────────┘
```

- **Gauche** : tous les bacs + un filtre par type (Tous / Fichiers / Habillage / Relais). Habillage = les bacs dont le dossier banque commence par `30-habillage` ; ce n'est plus un onglet. Plus de doublon (un bac d'habillage n'apparaît qu'une fois).
- **Droite, éditeur adaptatif** : pour un bac de fichiers, la liste des sons (rang, aperçu local, titre éditable, durée, actif/inactif, envoyer maintenant, supprimer) + **Ajouter** et **Attacher** ; pour un relais, l'**URL du flux** et la **durée max**.
- **Réglages essentiels** visibles (nom, mode). **Avancé, replié** : dossier banque, bloc Finder/SMB, pads d'idents.
- Tous les modes au même endroit, y compris « Une fois » (aujourd'hui caché dans l'inspecteur).

## Onglet Banque — alimenter la bibliothèque

L'ancien onglet *Importer*, renommé.

- **Destination** : Rotation, ou Archive NTF 1, 2, 3.
- **Envoi reprenable** (tus) ; formats audio courants ; **quota** en jauge.
- **Trois listes** : en cours, file d'attente (avant l'index Beets), rejets avec leur raison.
- À ne pas confondre avec « Ajouter » dans un bac : ici on remplit la bibliothèque de la station.

## Vocabulaire (interne → écran)

| Mot interne | Mot à l'écran |
|---|---|
| Cart | Bac (bac de sons) |
| Onglet Importer | Banque |
| `bank_folder` | Dossier de la banque |
| Attacher depuis la banque | Lier un dossier (sans copie) |
| `playlist_loop` | Boucle |
| `random` | Aléatoire |
| `playlist` | Une fois |
| `relay` | Relais |
| `ident_pads` | Pads d'idents (avancé) |

Le renommage **cart → bac** vaut pour toute l'app (sinon deux mots pour la même chose). Si tu préfères garder « cart », garde-le partout.

## Décisions

| Aujourd'hui | Refonte | Type |
|---|---|---|
| Carts, Habillage, Relais : trois onglets, le même écran filtré | Un seul onglet Bacs, filtre par type | Fusionné |
| Un bac d'habillage apparaît deux fois | Une seule liste, plus de doublon | Simplifié |
| Trois imports qu'on confond | Trois gestes nommés : deux dans le bac, la Banque à part | Clarifié |
| Onglet « Importer » | Onglet « Banque » | Renommé |
| « cart » | « bac de sons » | Simplifié |
| Inspecteur chargé (Finder SMB, dossier banque, URL…) | Essentiels visibles, le reste en avancé | Simplifié |
| Mode « Une fois » caché | Tous les modes au même endroit | Corrigé |
| Changer d'onglet perd recherche/sélection | Moins d'onglets, état conservé | Corrigé |
| « Pads d'idents » promet la rangée Antenne (retirée en P0) | Marqué « avancé », aide neutre | Corrigé |

## Contrat moteur (ne pas casser)

Refonte côté console. Mêmes endpoints, mêmes champs. On renomme l'affichage, pas l'API.

- **Lectures** : `/carts.json`, `/autodj/clocks.json` (usage d'un bac), `/media/bank.json`, `/library/inbox.json`, `/tus/`.
- **Écritures** (`X-CSRF-Token`) : bac `POST` / `PUT` / `DELETE /carts[/{id}].json` ; sons `POST /carts/{id}/sounds.json?delta=1` (fichiers ou `{folders}`), `PUT .../sounds/ranks.json {ranks}`, `PUT .../sounds/{id}.json {title|active}`, `POST .../sounds/delete.json {ids}`, `DELETE .../sounds/{id}.json` ; envoyer `POST .../sounds/{id}/now.json`, `POST /carts/{id}/now.json`.
- **Création** : `POST /carts.json` avec `title`, `mode`, `schedule_mode:"clock"`, plus `bank_folder` (habillage → `30-habillage/jingles`), `url` + `max_duration` en relais.
- Modes : `playlist`, `playlist_loop`, `random`, `relay`. Un relais exige URL HTTP avec chemin + `max_duration` > 0 ; il ne remplace pas le mount public.
- Un seul bac porte `ident_pads` ; repli sur le bac nommé Jingles sans drapeau.
- La **Banque** (`/library/inbox.json`, `/tus/`) passe par `ntr-ops`, pas par `/carts.json`.
- Priorité des sources (au moteur) : direct > relais > carts > jingles > rotation.

**Tout ce que la page doit encore savoir faire**

- [ ] Lister, créer, renommer, supprimer un bac, avec son mode.
- [ ] Importer fichiers/dossier dans un bac, réordonner (sauf aléatoire), activer/désactiver, renommer, supprimer, écouter en local.
- [ ] Envoyer un son maintenant, ou le bac entier.
- [ ] Attacher des dossiers de la banque sans les recopier.
- [ ] Régler un relais (URL + durée max), sans toucher au mount public.
- [ ] Marquer un seul bac comme pads d'idents.
- [ ] Voir si un bac est dans une horloge, l'ouvrir depuis Programmation (`?id=`).
- [ ] Déposer vers la banque (rotation, NTF 1–3), envoi reprenable, quota, file, rejets motivés.
- [ ] Rester réservé au programmateur et à l'admin.
