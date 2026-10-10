# Inventaire — console, API, écarts

28 septembre 2026. Lecture seule du code, sans modification. À lire avec `PLAN.md` et `ANTENNE.md`.

Le code actuel a déjà fait les étapes 1 à 10 du plan. L’API réelle n’utilise pas les noms français du plan. La page Antenne actuelle n’est pas encore la refonte de `ANTENNE.md`.

## 1. Arborescence de la console

Routes dans `ntr-console/src/App.tsx`, toutes sous la coque `Shell`. Aucune ne redirige vers une autre.

| Adresse | Écran | Accès |
|---|---|---|
| `/` et `/antenne` | `AntennePage` | tout compte connecté |
| `/conducteur` | `ConducteurPage` | tout compte connecté |
| `/programmation` | `ProgrammationPage` | `RoleGate` programmateur ou admin |
| `/sons` | `SonsPage` | programmateur ou admin |
| `/reglages` | `ReglagesPage` | tout compte ; les onglets changent selon le rôle |
| `*` | page « Page introuvable » | — |

Onglets via `?onglet=` :

- Programmation : Rotation, Horloges, Semaine, Catégories.
- Sons : Carts, Habillage, Relais, Importer.
- Réglages : Comptes et Automate seulement si admin ; Mon compte pour tout le monde.

`/account.json` est lu une fois dans `src/api/AccountContext.tsx` (`GET` au montage). Le rôle en est déduit dans `src/api/roles.ts` : `admin` → Admin ; sinon `carts` ou `autodj` → Programmateur ; sinon Animateur. `stream` allume « Peut passer en direct ».

L’accès aux pages se décide à deux endroits. Le menu de `src/layout/Shell.tsx` cache Programmation et Sons sous le rôle Programmateur. `RoleGate` dans `App.tsx` affiche « Accès réservé » si on force l’adresse. Réglages reste ouvert, mais `ReglagesPage` retire Comptes et Automate pour un non-admin.

Le pupitre est dans `src/pages/AntennePage.tsx`, avec `DeskGlance`, `DeskFile`, `DeskLibrary`, `DeskHotStrip` et `LiveConnectPanel`.

## 2. JSON réellement exposé

La console préfixe `/api` en dev. En prod, nginx ne laisse passer qu’une liste de chemins. Les mutations envoient `X-CSRF-Token` lu dans `GET /csrf.json` → `{csrf_token}`. Refus : `401 {error:"unauthenticated"}`, `403 {error:"forbidden"}`.

### Session

- `POST /login.json` `{username, password}` → `{ok:true}`.
- `GET /logout` : ce n’est pas du JSON, c’est une redirection HTML.
- `GET /account.json` → `{username, permissions:{admin, stream, live, carts, not_audio, autodj}}`, tous des booléens.
- `PUT /account.json` `{password}` → la même forme. Mot de passe vide → 400.

### Live

`GET /live.json` n’a pas de champ « harbor connecté ». On le déduit de `source`.

```json
{
  "status": "playing|simulating|offline",
  "source": "autodj|stream|relay|carts|jingles|…",
  "artist": "",
  "title": "",
  "album": "",
  "kind": "",
  "remaining": 0,
  "elapsed": 0,
  "duration": 0,
  "on_air": "",
  "emission": null
}
```

`emission`, ajouté par-dessus, vaut `null` ou `{id, title, artist, state:"waiting"|"on_air", until, scope, start_minute?, day_of_week?}`. `DELETE /live.json` → `{ok:true}` si le compte a `live` (un admin passe).

### Conducteur

`GET /autodj/conducteur.json?horizon=360` → `{now, horizon_min, clock, daypart, items, summary}`.

Un item : `{id, at, kind, when, resource, queue, status, status_code, reason, clock, daypart, duration, clock_id, position_id, cart_id, sound_id, origin, path?, artist?, title?, minute?, sync?, category?, cart?}`. `origin` vaut `desk` pour une ligne posée à la main.

`POST` sur la même URL, `{reset:true}`, exige `autodj`. L’horizon vient de la query (`horizon=30` dans Automate).

Écritures du pupitre, droit `live` : `POST /autodj/conducteur/items.json` (à la suite, ou `{suppress_at}` pour masquer un item d’horloge), `DELETE …/items/{id}.json`, `PUT …/items/ranks.json` `{ids}`, `POST …/now.json`.

### Émissions

`GET /antenne/emissions.json` → `{emissions, current, next}`.

Hebdo : `{id, version, scope:"weekly", title, artist, day_of_week, start_minute, end_minute, host_username}`. Session : `starts_at` / `ends_at` à la place des minutes.

`POST` session `{scope:"session", title, artist}` exige le harbor déjà branché et le droit `live`. Il remplace la session en cours. `POST` hebdo `{title, artist, day_of_week, start_minute, end_minute, host_username}` exige `autodj`. Chevauchement refusé.

### Antenne

`GET /antenne/state.json` → `{at, playout, engine, incidents, listeners, asrun, next_live_slot}`. `playout` porte `reachable, source, silence_s, rms_db, harbor_s`. Un incident : `{kind, detail, since_s, notified}`. `POST /antenne/flush.json` → `{ok:true}`, droit `live`.

### Carts

`GET /carts.json` → `{carts:[…]}`. Un cart : `{id, version, title, notes, mode, url, queue, max_duration, bank_folder, ident_pads, sounds:[…]}`.

`mode` vaut `playlist`, `playlist_loop`, `random` ou `relay`. Ce n’est pas `clock` / `loop` / `once`. `schedule_mode` est à part (`clock`, `jingles`, `timed`). `url` n’est rempli qu’en `relay`. `ident_pads` est le drapeau des pads. Un son : `{id, rank, title, duration, active, available, gain, peak, last_played, uploader, path}`.

Créer un relais : `POST /carts.json` avec `mode:"relay"`, une URL HTTP complète et `max_duration` en secondes. Sans durée max, le moteur répond 400.

### Comptes

`GET/POST /users.json`, `PUT/DELETE /users/{id}.json`, admin seulement. Un compte : `{id, username, notes, permissions}`. `PUT` accepte `notes`, `password`, `permissions`, `username`.

### Catalogue, pas Radiotomate

`GET /library/search?q=&limit=&kind=&grouping=&folder=` est le service `ntr-ops/catalog`. Réponse : `{hits:[{id, path, title, artist, kind, grouping, folder, duration}], estimatedTotalHits}`. `grouping` est une égalité simple : `ntf1,ntf2,ntf3` ne fait pas un OU.

`GET /inbox.json` (via `/library/inbox.json`) : `{quota:{used, limit}, queue, rejected, progress}`. L’envoi reprend par tus sur `/tus/`, pas par Radiotomate.

## 3. Écarts

### Le plan et l’API

Le tableau du plan est un raccourci. À corriger avant de coder dessus :

- Nommer ou créer une émission envoie `title` et `artist`, pas `nom` / `phrase`. L’identifiant du plateau est `host_username`. Le créneau est `day_of_week` + `start_minute` + `end_minute`, pas `début` / `fin`.
- Il n’y a pas de champ `on_air` sur l’émission. L’état courant est `state: "waiting"` ou `"on_air"`.
- Le harbor n’est pas un booléen de `/live.json`. C’est `source` qui contient `stream` ou `harbor`.
- Les modes de cart sont `playlist`, `playlist_loop`, `random`, `relay`. Le plan écrit `clock`, `loop`, `random`, `once`.
- `ident_pads` et `PUT /account.json` existent déjà. Le plan ne les nomme pas.
- `/library/search` n’est pas un endpoint Radiotomate.

### Rôles

La traduction et la lecture inverse du plan sont en place, et `not_audio` n’est pas dans l’interface. Deux écarts restent :

- [x] Un Animateur ne peut plus modifier le Conducteur (retirer une ligne, réparer une case). Programmateur et Admin, si. La file de l’antenne reste ouverte à l’animateur. Reconstruire le conducteur reste dans Automate, donc réservé à l’admin — le plan le donnait aussi au programmateur.
- Un admin sans interrupteur Stream peut quand même se brancher : le moteur l’autorise. L’interface le dit. Le plan, lui, ne pose `stream` que si l’interrupteur est allumé.

### ANTENNE.md

La page actuelle est encore le pupitre d’avant cette spec.

| `ANTENNE.md` | Code actuel |
|---|---|
| Pas de défilement | La page défile, surtout à cause de la fiche encodeur |
| Bandeau : état, cause, heure, lien « Passer en direct ? » | Bandeau : En onde / Silence / Direct / Problème + heure, sans cause |
| Bouton **Suivant** | Bouton **Passer** |
| Fiche encodeur repliée | Fiche toujours ouverte, sous le bandeau |
| Bibliothèque : toucher = à la suite, un bouton ▶ | Deux boutons « Jouer maintenant » et « À la suite » |
| Plus d’idents, plus de touche 1–6 | Rangée Idents + 1–6, drapeau `ident_pads` |
| Plus le mot « pupitre » | Badge « pupitre » sur les lignes ajoutées à la main |
| Renommer le live pendant tout le direct | Le formulaire n’apparaît que s’il n’y a pas encore d’émission |

Le renommage n’a pas besoin d’un nouvel endpoint : `POST /antenne/emissions.json` avec `scope:"session"` efface déjà la session et en crée une autre, tant que le harbor est branché. Les champs restent `title` et `artist`.
