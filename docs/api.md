# API JSON du moteur

La console parle au moteur uniquement par ces routes JSON, servies par l'interface (`:6811`). Les pages HTMX d'origine de Radiotomate restent servies par le même processus. Cette page décrit le contrat : une route change de forme seulement si la console change avec elle, dans le même commit.

## Rôles et droits

Le moteur connaît six droits par compte : `admin`, `stream`, `live`, `carts`, `autodj`, `not_audio`. La console ne les montre jamais tels quels : elle raisonne en trois rôles et un interrupteur.

| Rôle | Droits posés à l'écriture du compte |
|---|---|
| Animateur | `live` |
| Programmateur | `live`, `carts`, `autodj` |
| Admin | `admin` |
| Interrupteur « Peut passer en direct » | ajoute `stream` (et `live` s'il manque) |

Lecture inverse : `admin` → Admin ; sinon `carts` ou `autodj` → Programmateur ; sinon Animateur. `stream` allume l'interrupteur. `not_audio` n'est jamais posé par la console.

Pour le direct, le harbor accepte un compte `stream`. Dès qu'une émission hebdomadaire nomme un animateur (`host_username`), un compte non admin n'entre que pendant son propre créneau.

## Routes

La console préfixe `/api` en dev. En prod, nginx ne laisse passer qu’une liste de chemins. Les mutations envoient `X-CSRF-Token` lu dans `GET /csrf.json` → `{csrf_token}`. Refus : `401 {error:"unauthenticated"}`, `403 {error:"forbidden"}`.

### Session

- `POST /login.json` `{username, password}` → `{ok:true, username, permissions}`. Pas besoin de jeton CSRF.
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

### Système

`GET /system/disk.json` → `{total, used, free, path}` : espace disque de la banque (`MEDIA_ROOT`). Droits `carts` ou `autodj`, sinon 403 ; 503 si le disque est illisible.

### Comptes

`GET/POST /users.json`, `PUT/DELETE /users/{id}.json`, admin seulement. Un compte : `{id, username, notes, permissions}`. `PUT` accepte `notes`, `password`, `permissions`, `username`.

### Catalogue (service à part du moteur)

`GET /library/search?q=&limit=&kind=&grouping=&folder=&top=` est le service catalogue (`services/catalog`). Réponse : `{hits:[{id, path, title, artist, kind, grouping, folder, top, duration}], estimatedTotalHits}`. Une liste séparée par des virgules fait un OU : `grouping=ntf1,ntf2`. `top` est le dossier de premier niveau : `top=20-archives` donne toutes les banques d'archives.

`GET /inbox.json` (via `/library/inbox.json`) : `{destinations, quota:{used, limit}, queue, rejected, progress}`. L’envoi reprend par tus sur `/tus/`, pas par Radiotomate.

`destinations` : `[{id, label, group, folder}]`. D'abord `rotation`, puis une banque par dossier de `20-archives` (sauf ceux qui commencent par `.` ou `_`). `id` est le nom du dossier, et la métadonnée `destination` de l'envoi tus. `label` vient du fichier `.banque.json` du dossier (`{"nom": "…"}`), sinon du nom du dossier.

`POST /banks.json` (via `/library/banks.json`), corps JSON `{label, folder}` : crée `20-archives/<folder>` et `00-inbox/archives/<folder>`. `folder` : minuscules, chiffres et tirets, 40 caractères au plus. Même droit que le dépôt (admin, bacs ou auto-DJ). Réponse `201 {destination}`, `400` ou `409 {error}` en français.

