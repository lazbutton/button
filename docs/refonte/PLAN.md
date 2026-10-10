# Brief d'implémentation — Refonte de la console NTR + fonctions V0

> À donner à un agent de code (Grok). Ce document est autonome : il contient le contexte, l'API du moteur, les contraintes et les étapes avec leurs critères d'acceptation. **Lis-le en entier avant d'écrire du code.**

---

## 0. Mission

Refondre la console web `ntr-console` (React) pour en faire un outil **simple, cohérent et professionnel**, et coder les fonctions manquantes de la V0 festival (passer en direct, dépôt de musique par le navigateur, décrochages/relais).

Règle qui gouverne tout : **ce qu'on voit correspond à ce qu'on peut faire.** Le rôle décide de l'écran. Aucun droit fantôme, aucune page qu'on ne peut pas ouvrir, aucun écran orphelin.

Tu livres **lot par lot** (étapes 1 à 10 ci-dessous), chaque lot testé et vérifiable contre ses critères d'acceptation, dans l'ordre donné.

---

## 1. Contexte technique

### Dépôts et briques
- **Console (à refondre)** : `ntr-console`, application **React**. Dev sur `http://127.0.0.1:5175`. Prod sur `https://gabbler.band`.
- **Moteur** : `radiotomate/` — Python (Quart, Quart-Auth, SQLAlchemy/aiosqlite sur SQLite, Beets, Mutagen, config YAML). **Expose une API JSON** que la console consomme. Ne pas réécrire le moteur.
- **Exploitation** : `ntr-ops` (Docker Compose, cron, Caddy, Icecast).
- **Playout** : Liquidsoap 2.4.5 → Icecast. Entrée live (**harbor**) sur Nasgul, port `6800`, mount `/stream`.
- **Ancienne admin HTML** : Radiotomate sur le port `6811` (`/live`, `/carts`, `/autodj`, `/account`). Reste joignable, la console lui parle en JSON. **Ce n'est pas l'app à refondre**, mais la cible est de ne plus en dépendre pour le quotidien.
- **Écoute publique** : `https://radio.lazbutton.xyz/button.mp3` (MP3 128), titre dans `https://radio.lazbutton.xyz/now.json` (`artist`, `title`).

### Machines
- **Nasgul** : fait tourner le moteur + le playout + le harbor. Machine de dev/prod du moteur.
- **VPS-1** (OVH, 2 vCore / 4 Go) : frontal HTTPS (Caddy) + Icecast public. N'héberge pas le moteur.

---

## 2. L'API (contrat à respecter)

La console **ne produit pas le son** : elle envoie des ordres en JSON et lit l'état. **Conserve ces endpoints et leurs formes.** Les noms ci-dessous sont ceux du JSON, pas des libellés d'écran.

Toute mutation envoie `X-CSRF-Token`, lu dans `GET /csrf.json` → `{csrf_token}`. `POST /login.json` `{username, password}` → `{ok:true}` n'en a pas besoin. `GET /logout` est une redirection HTML, pas du JSON. Refus : `401 {error:"unauthenticated"}`, `403 {error:"forbidden"}`.

| Endpoint | Méthode | Rôle | Période de poll |
|---|---|---|---|
| `/account.json` | GET | `{username, permissions:{admin, stream, live, carts, not_audio, autodj}}` (booléens) | à l'entrée |
| `/account.json` | PUT `{password}` | Changer son mot de passe. Déjà en place. Réponse : la même forme que le GET | — |
| `/live.json` | GET | `{status, source, artist, title, album, kind, remaining, elapsed, duration, on_air, emission}` | 1 s |
| `/live.json` | DELETE | Couper le titre en cours → `{ok:true}` si `live` (un admin passe) | — |
| `/autodj/conducteur.json?horizon=360` | GET | `{now, horizon_min, clock, daypart, items, summary}` | 3 s |
| `/autodj/conducteur.json?horizon=30` | POST `{reset:true}` | Reconstruire le conducteur. Droit `autodj`. L'horizon est celui de la query | — |
| `/antenne/state.json` | GET | `{at, playout, engine, incidents, listeners, asrun, next_live_slot}` | 5 s |
| `/antenne/emissions.json` | GET | `{emissions, current, next}` | 3 s |
| `/antenne/emissions.json` | POST `{scope:"session", title, artist}` | Nommer ou remplacer le live. Harbor déjà branché, droit `live` | — |
| `/antenne/emissions.json` | POST `{title, artist, day_of_week, start_minute, end_minute, host_username}` | Créneau hebdo. Droit `autodj`. Chevauchement refusé | — |
| `/antenne/flush.json` | POST | Vider les files Liquidsoap → `{ok:true}`, droit `live` | — |
| `/carts.json` | GET | `{carts:[…]}` | 8 s |
| `/carts/{cartId}/sounds/{soundId}/now.json` | POST | Jouer ce son maintenant (coupe) | — |
| `/library/search?q=&limit=40&kind=&grouping=&folder=` | GET | Catalogue **ntr-ops**, pas Radiotomate. `{hits, estimatedTotalHits}` | 80 ms après frappe |
| `/inbox.json` | GET | File, rejets et quota du dépôt. Servi par le catalogue (**ntr-ops**), proxifié en `/library/inbox.json`. `{quota:{used, limit}, queue, rejected, progress}` | — |

Le harbor n'est pas un booléen de `/live.json`. On le déduit de `source` : elle vaut `stream` ou `harbor`. `status` vaut `playing`, `simulating` ou `offline`. `emission` vaut `null` ou `{id, title, artist, state:"waiting"|"on_air", until, scope, start_minute?, day_of_week?}`.

Un item de conducteur : `{id, at, kind, when, resource, queue, status, status_code, origin, duration, path?, artist?, title?, minute?, sync?, cart?}`. `origin` vaut `desk` pour une ligne posée à la main.

**Écritures du pupitre** (droit `live`) : `POST /autodj/conducteur/items.json` (à la suite, ou `{suppress_at}` pour masquer un item d'horloge), `DELETE …/items/{id}.json`, `PUT …/items/ranks.json` `{ids}`, `POST …/now.json`.

**Filtres de `/library/search`** : `grouping=rotation` (musique), `kind=jingle` (jingles). `grouping` est une égalité simple : `ntf1,ntf2,ntf3` ne fait pas un OU. Dossiers habillage : `30-habillage/…`.

**Modèle Cart** : `title`, `notes`, `mode` (`playlist`, `playlist_loop`, `random`, `relay`), `schedule_mode` (`clock`, `jingles`, `timed`), `bank_folder`, `ident_pads` (drapeau des pads d'idents, déjà en place), sons (`id, rank, title, duration, active, path`). Un cart `relay` porte `url` (HTTP avec un chemin) et `max_duration` en secondes, obligatoire. La console les édite déjà dans Sons → Relais.

**Modèle Émission** : `title` (nom), `artist` (phrase), `scope` (`session` ou `weekly`). Hebdo : `day_of_week`, `start_minute`, `end_minute`, `host_username` (compte nommé, ou chaîne vide). Il n'y a pas de champ `on_air` : l'état courant est `state` (`waiting` ou `on_air`) sur `current`. `POST` session remplace la session en cours.

**Priorité des sources du moteur** (ne pas changer) : `harbor` (live) > `relais` > `carts` > `jingles` > `auto-DJ`.

**Droits moteur** : `admin`, `stream` (ouvre le harbor), `live` (gestes du pupitre), `carts`, `autodj`, `not_audio` (jamais posé par la console, absent de l'UI).

Le dépôt reprenable n'est pas un endpoint Radiotomate : tus vers `/tus/` (`tusd` dans ntr-ops), puis le hook du catalogue range le fichier dans `00-inbox`.

---

## 3. Règles d'or (contraintes non négociables)

1. **Ne pas casser le moteur.** La console parle au moteur via les endpoints JSON existants. Toute modification du moteur doit être minimale, justifiée en tête de commit, et rétro-compatible.
2. **Rôles, pas droits bruts.** La console raisonne en **rôles** (voir étape 1) ; elle traduit rôle → drapeaux moteur au moment d'écrire un compte. Elle n'expose jamais les six cases brutes.
3. **Une route par écran.** Supprime les routes qui redirigent. Chaque concept a une adresse stable.
4. **Français partout**, thème **clair et sombre**, **mobile** propre (le même écran doit tenir sur téléphone).
5. **AGPL** : garde un lien « Code source » accessible dans l'interface.
6. **Pas de dépendance lourde inutile** : reste dans la stack React existante. Pour l'upload, `Uppy` + `tusd` sont imposés (étape 7).
7. **Ne pas casser l'existant pendant la bascule** : si un écran refondu n'est pas prêt, garde l'ancien derrière la même route jusqu'à ce que le nouveau passe ses critères. Pas de page blanche en prod.
8. **Chaque geste d'écriture gère ses refus** : session expirée, droit manquant, moteur injoignable → message clair, pas d'échec muet.
9. **Accessibilité** : navigable au clavier, contrastes suffisants, cibles tactiles ≥ 40 px.

---

## 4. Le modèle de rôles (fondement — étape 1)

Remplace les deux personas (`admin` / non-admin) et les six droits épars par **trois rôles** + **un interrupteur**.

| Section | Animateur | Programmateur | Admin |
|---|---|---|---|
| Antenne (pupitre) | pilote | pilote | pilote |
| Conducteur | lecture | pilote | pilote |
| Programmation | — | édite | édite |
| Sons | — | édite | édite |
| Comptes | — | — | édite |
| Dépannage | — | reconstruire | tout |

**Interrupteur « Peut passer en direct »** (orthogonal au rôle) : ouvre le harbor sur le créneau de la personne.

**Traduction rôle → drapeaux moteur** (au moment d'écrire un compte) :
- Animateur → `live`.
- Programmateur → `live`, `carts`, `autodj`.
- Admin → `admin` (+ tous les gestes acceptés).
- Interrupteur direct ON → ajoute `stream` (+ `live` s'il manque).
- `not_audio` → jamais posé par la console, absent de l'UI.

**Lecture inverse** (déduire le rôle d'un compte existant à partir de ses drapeaux) : `admin` → Admin ; sinon `carts`||`autodj` → Programmateur ; sinon → Animateur. `stream` → interrupteur direct ON.

---

## 5. La navigation cible (étape 2)

Cinq sections, une route par écran :

```
Console
├─ Antenne              /antenne          (pupitre P0, voir étape 3)
├─ Conducteur          /conducteur
├─ Programmation       /programmation     onglets: Rotation · Horloges · Semaine · Catégories
├─ Sons                /sons              onglets: Carts · Habillage · Relais · Importer
└─ Réglages            /reglages          onglets: Comptes · Mon compte · Automate
```

- Le menu n'affiche que les sections permises par le rôle.
- **Bouton de déconnexion** présent dans la coque, sur toutes les pages, mobile compris.
- **Supprime** les routes qui redirigent (`/comptes`, `/horloges`, `/categories`, `/semaine`, `/habillage`, `/carts` seul…) : elles deviennent des onglets des cinq sections.
- Login **par compte personnel** : plus de préremplissage du compte de la marque.

---

## 6. Étapes d'implémentation

Chaque étape est un lot livrable. Fais-les **dans l'ordre**. Format de chaque étape : objectif, tâches, endpoints/fichiers, critères d'acceptation, à ne pas faire.

### Étape 1 — Rôles et accès *(fondement, à faire en premier)*

**Objectif.** Le rôle décide de ce qu'on voit et peut faire.

**Tâches.**
- Introduire un modèle de rôle côté console (Animateur / Programmateur / Admin) + interrupteur direct, déduit de `/account.json` (lecture inverse, §4).
- Router les sections selon le rôle. Un accès non autorisé renvoie proprement (pas de page blanche, message « accès réservé »).
- La création/édition d'un compte se fait par **rôle + interrupteur**, jamais par les six cases. Traduire rôle → drapeaux à l'écriture.

**Critères d'acceptation.**
- [x] Un compte Animateur ne voit que Antenne et Conducteur ; il n'a aucune route ouvrable en plus.
- [x] Créer un compte = choisir un rôle ; les drapeaux moteur posés correspondent au tableau §4.
- [x] Un compte avec l'interrupteur direct ON reçoit `stream` + `live` et apparaît dans la liste « identifiant du plateau ».
- [x] `not_audio` n'apparaît nulle part.

**À ne pas faire.** Exposer les drapeaux bruts. Créer un compte qui voit un menu sans pouvoir ouvrir les pages.

---

### Étape 2 — Coque, navigation, déconnexion

**Objectif.** Cinq sections, une route par écran, on peut sortir.

**Tâches.**
- Coque unique : colonne de navigation (repliable, état mémorisé), barre du haut (pastille d'état globale, thème clair/sombre, casque pour l'admin, lien Code source AGPL).
- Router les cinq sections (§5). Supprimer les redirections.
- Bouton **Déconnexion** dans la coque (et dans le panneau mobile).
- Login par compte personnel (retirer le préremplissage `lazbutton`).

**Critères d'acceptation.**
- [x] Les cinq sections ont chacune une route stable ; aucune route ne redirige vers une autre.
- [x] On se déconnecte depuis n'importe quelle page, sur ordinateur et sur mobile.
- [x] Le champ identifiant du login est vide au départ.
- [x] La navigation marche au clavier et le menu se replie sur mobile.

---

### Étape 3 — Page Antenne P0 *(l'écran quotidien, voir maquette plus bas)*

**Objectif.** Un seul écran, sans jargon, qu'un bénévole tient sans explication. Même page pour tous les rôles.

**Retirer de la page.**
- Les cinq puces (Horloge, Ancre, Suivant, Jingle, Émission) — jargon de programmation.
- Les six pastilles de santé **et** le dépannage → ils partent dans Réglages → Automate (étape 9).
- La rangée de pads **Pubs** (garder une seule rangée, « Idents »).
- Le bloc **Passé** → il vit sur le Conducteur.
- Les onglets de recherche **Pubs, Habillage, Émissions**.
- Le geste **Remplacer** (et la sélection de ligne préalable).

**Garder, clarifié.**
- **Bandeau d'état unique**, lisible à trois mètres : `En onde` (vert), `Silence` (rouge/orange), `Direct : {nom}` (rouge), `Problème` (orange), + l'heure locale.
- **Carte maintenant** : temps restant en gros, artiste — titre, barre de progression, badge source + « fin hh:mm », bouton **Passer** (`DELETE /live.json`, inactif si arrêt ou harbor).
- **File** (colonne large) : jusqu'à 10 prochains + « encore N dans le conducteur » ; retrait avec **Annuler** (toast 8 s) ; glisser-déposer pour réordonner les lignes `origin: desk` uniquement ; lignes verrouillées (ancre, titre en cours) non déplaçables.
- **Bibliothèque** (colonne étroite) : recherche (`/library/search`), onglets réduits à **Tous · Musique · Jingles · Archives**, récents (navigateur), et **deux actions par résultat** : **Jouer maintenant** et **À la suite**.
- **Idents** : une rangée de 6 pads (le cart dédié aux idents/jingles), clic ou touches 1–6.
- **Passer en direct** : quand le harbor se branche (`source` vaut `stream` ou `harbor`), bandeau calme « Direct — l'horloge est en pause » + formulaire **Nommer ce live** (`title` + `artist`, `POST /antenne/emissions.json {scope:"session", title, artist}`). Pads et Passer inactifs pendant le direct.

**Ajouter.**
- Deux actions nommées en clair (**Jouer maintenant** / **À la suite**) remplacent « Ensuite / Remplacer ».
- Écran vide qui dit quoi faire (« Cherche un titre et mets-le à la suite »), au lieu d'un tiret.
- Clavier réduit : `Espace` (passer), `1–6` (idents), `/` (chercher), `Entrée` (à la suite). Retirer `Maj+1–6`, `Maj+Entrée`, `Remplacer`.

**Maquette cible.**
```
┌ ● En onde ───────────────────────────────────── 14:32 ┐

┌ 2:14        Artiste — Titre                 [ Passer ] ┐
│ restant     ▓▓▓▓▓▓▓▓▓░░░░░░░░                          │
│             Auto-DJ · fin 14:35                         │
└────────────────────────────────────────────────────────┘

┌ File ───────────────────┐   ┌ Bibliothèque ───────────┐
│ N  Artiste — Titre  2:58 │   │ [ Titre, artiste…      ]│
│ 2  Titre            3:10 │   │ Titre A   [Jouer][Suite]│
│ + 6 dans le conducteur   │   │ Titre B   [Jouer][Suite]│
└──────────────────────────┘   └─────────────────────────┘

┌ Idents   [1] [2] [3] [4] [5] [6] ─────────────────────┐
```

**Critères d'acceptation.**
- [x] Un bénévole tient une heure d'antenne (chercher, jouer, mettre à la suite, envoyer un ident, passer en direct) sans autre écran.
- [x] Aucune puce, aucune pastille multiple, aucun dépannage sur cette page — l'admin voit la même page.
- [x] En direct, pads et Passer sont inactifs ; le champ « Nommer ce live » apparaît si l'émission n'est pas nommée.
- [x] La page tient sur téléphone (colonnes empilées, idents sur une ligne).

---

### Étape 4 — Programmation unifiée

**Objectif.** Rassembler en un seul endroit ce qui est aujourd'hui éclaté entre Auto-DJ (fourre-tout), Horloges (écran mort), Catégories (écran mort) et Semaine (bloc replié).

**Tâches.** Section `/programmation`, quatre onglets :
- **Rotation** : ce qui tourne (jingles, programme, pubs), réordonner, lien vers le cart, ancres `:20`/`:40`.
- **Horloges** : ressusciter l'Atelier Horloges (liste, motif, inspecteur de case, poser un cart, réparer un cart manquant).
- **Semaine** : remonter la grille hebdo au premier plan — départs (heure → horloge) et émissions (`title`, `artist`, `host_username`, `day_of_week`, `start_minute`, `end_minute`, chevauchement refusé par le moteur).
- **Catégories** : ressusciter la table (nom, requête, requête de repli, nombre de titres ; créer/éditer/supprimer, essayer la requête).

**Critères d'acceptation.**
- [x] La grille de la semaine se pose sans ouvrir Auto-DJ ni dérouler un bloc.
- [x] Horloges et Catégories ont chacune une adresse et un écran fonctionnel.
- [x] Poser un départ, une émission et une catégorie fonctionne bout à bout contre le moteur.

**À ne pas faire.** Laisser du code d'écran sans route. Recréer un « tout sur une page ».

---

### Étape 5 — Sons + relais éditable *(inclut les décrochages)*

**Objectif.** Une section `/sons` complète : carts, habillage, **relais éditable**, import.

**Tâches.**
- Onglets **Carts** et **Habillage** : liste, création (titre + mode), import de fichiers/dossier, attacher depuis la banque, inspecteur (titre, notes, mode, dossier, sons).
- **Pads par drapeau** : un cart devient « pads idents » via un **drapeau explicite** sur le cart, pas par son titre exact `Jingles`/`Pubs`. Migrer la logique de l'étape 3 vers ce drapeau.
- Onglet **Relais** : éditer les carts `relay` — **URL HTTP** + **durée max** (obligatoire). Le moteur les connaît déjà ; il manque l'écran.
- **Décrochages** : documenter et rendre pilotable le relais entrant/sortant (un partenaire prend le flux, ou la NTR relaie un partenaire) via ces carts relay et la priorité des sources.

**Critères d'acceptation.**
- [x] Un relais s'édite dans Sons (URL + durée max) et joue via la priorité des sources.
- [x] Un cart devient pads d'idents sans dépendre de son titre.
- [x] Import d'un fichier et attache depuis la banque fonctionnent.

---

### Étape 6 — Passer en direct (panneau + fiche) *(fonction V0)*

**Objectif.** Rendre le direct compréhensible sans quitter l'app. Le branchement reste externe (encodeur), la console guide et reflète l'état.

**Tâches.**
- Panneau **Passer en direct** dans Antenne (ou `/antenne` sous-vue) montrant l'**état du harbor** (branché / absent / en attente) lu depuis `/live.json` + `/antenne/state.json`.
- **Fiche mode d'emploi** d'une page (réglages encodeur) :
  - Type : Icecast source (BUTT ou Mixxx)
  - Adresse : Nasgul (`192.168.1.100` sur place, nom Tailscale hors studio)
  - Port : `6800` — Mount : `/stream`
  - Utilisateur : identifiant de son compte (droit **Stream**) — Mot de passe : celui du compte
  - Format : MP3 128–192 kbps
- Rappeler la règle des créneaux : si une émission nomme un identifiant, seul ce compte (ou un admin) passe sur ce créneau ; sinon tout compte `stream` peut se brancher.
- À la connexion : bascule Direct + « Nommer ce live » (déjà en étape 3). À la coupure : le moteur vide les files et saute le titre auto-DJ (comportement existant, ne pas dupliquer).

**Critères d'acceptation.**
- [x] Depuis l'app, un animateur voit s'il est en direct et comment se brancher, sans doc externe.
- [ ] Trois directs d'une heure passent sans intervention ; un compte sans droit direct hors créneau est refusé proprement.

**À ne pas faire.** Créer un bouton « passer en direct » dans la console (le direct vient de l'encodeur). Réimplémenter la coupure côté console.

---

### Étape 7 — Dépôt de musique par le navigateur *(fonction V0)*

**Objectif.** Une radio envoie sa musique depuis un navigateur, sans SMB ni intervention.

**Tâches.**
- Frontend **Uppy** dans un onglet **Sons → Importer** : upload **reprenable** (tus).
- Backend **tusd** (dans `ntr-ops`) : dépose les fichiers dans `00-inbox/rotation` (rotation) ou `00-inbox/archives/ntf1..ntf3` (archives), selon le choix de l'onglet.
- Le conteneur **dropbox** promeut, **Beets** indexe (chaîne existante). Prévoir un petit endpoint (moteur ou ntf-ops) exposant la **file d'attente** et les **fichiers rejetés** (format inconnu, doublon), avec la raison.
- Afficher l'avancement, les rejets avec leur motif, et un **quota** de stockage par station. Refuser les formats inconnus.

**Critères d'acceptation.**
- [ ] Un album de 2 Go envoyé en 4G, coupé puis repris, passe en rotation en moins de 10 min avec les bons tags.
- [x] Les fichiers rejetés s'affichent avec la raison ; la file d'attente est visible.

**À ne pas faire.** Réimplémenter l'indexation (c'est Beets). Uploader sans reprise.

---

### Étape 8 — Mon compte

**Objectif.** Le b.a.-ba par personne.

**Tâches.** Onglet **Réglages → Mon compte** : changer son mot de passe, voir son rôle et ses créneaux, se déconnecter. Et dans **Comptes** (admin) : réinitialiser le mot de passe d'un compte, éditer les notes, voir les créneaux de la personne sur sa fiche.

**Critères d'acceptation.**
- [x] Chacun change son mot de passe depuis l'app.
- [x] L'admin réinitialise un mot de passe et voit les créneaux d'un compte sur sa fiche.

---

### Étape 9 — Dépannage et Automate

**Objectif.** Un seul endroit pour réparer et voir l'état (aujourd'hui éclaté entre le pupitre et le Conducteur).

**Tâches.** Onglet **Réglages → Automate** (admin) :
- **Santé complète** : les six pastilles (Antenne, Public, Local, Direct, Moteur, Alertes) avec leurs popovers, déplacées ici depuis la page Antenne.
- **Dépannage unifié** : Recharger l'état, Vider les files (`POST /antenne/flush.json`), Reconstruire le conducteur (`POST /autodj/conducteur.json?horizon=30 {reset:true}`). Fusionner ici les gestes aujourd'hui doublés (Dépannage du pupitre + Relancer/Réinitialiser du Conducteur).
- **Page de statut** lisible (état du flux, du moteur, des sorties).

**Critères d'acceptation.**
- [x] Un seul endroit répare l'antenne ; plus de geste de réparation ailleurs.
- [x] La santé détaillée et les incidents sont visibles dans Automate.

---

### Étape 10 — Polissage

**Objectif.** Rendre le tout présentable et cohérent.

**Tâches.**
- **Nommage unique** : mêmes mots partout (plus de pastilles renommées selon le rôle).
- **Messages d'erreur** qui disent quoi faire (session, droit, moteur injoignable).
- **Mobile** vérifié sur chaque écran.
- **Accessibilité** : focus visibles, clavier complet, contrastes.
- Retirer le code mort et les routes fantômes restantes.

**Critères d'acceptation.**
- [ ] Un nouvel arrivant se sert de l'app sans qu'on la lui explique.
- [x] Aucune route morte, aucun écran orphelin dans le code.

---

## 7. Ordre d'exécution et jalons

1. **Étape 1 (Rôles)** — le fondement, rien ne se construit correctement avant.
2. **Étapes 2 et 3** (Coque + Antenne P0) — la structure et l'écran quotidien : premier gain visible.
3. **Étapes 4 et 5** (Programmation + Sons) — le cœur de la programmation.
4. **Étapes 6 et 7** (Direct + Dépôt web) — les fonctions V0 festival.
5. **Étapes 8, 9, 10** (Mon compte, Automate, Polissage) — finition.

Livre chaque étape séparément, avec ses critères cochés.

---

## 8. Définition de « fini »

- [x] Ce qu'on voit correspond au rôle : aucun droit fantôme, aucune page inaccessible.
- [x] Chaque concept a une page ; aucune route morte, aucun écran orphelin.
- [x] On se connecte avec son compte, on se déconnecte, on change son mot de passe.
- [x] Un seul endroit pour programmer, un seul pour réparer.
- [x] Déposer un titre, passer en direct et suivre l'état ont chacun une page.
- [x] Vocabulaire cohérent, erreurs claires, mobile propre.
- [ ] Un bénévole tient l'antenne sans qu'on lui explique l'écran.

---

## 9. Ce que tu livres à chaque étape

- Le code (dans `ntr-console`, et `ntr-ops` / `radiotomate/` seulement si l'étape l'exige, avec justification).
- Un court résumé : ce qui a changé, les fichiers touchés, les endpoints appelés.
- Les critères d'acceptation de l'étape, cochés, avec comment les vérifier.
- Toute modification du moteur signalée explicitement et gardée rétro-compatible.

**Avant de commencer une étape** : lis le code existant concerné (console + moteur) pour confirmer les formes exactes des requêtes/réponses, et préserve-les.
