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

### Agenda

Émissions à une date : un set enregistré (`kind:"set"`, un fichier) ou un direct (`kind:"live"`, un compte qui peut se brancher). Les instants sont rendus en heure de Paris avec leur décalage (`2026-11-07T22:00+01:00`). En écriture, `start` / `end` sans décalage sont lus comme une heure de Paris : le moteur gère les changements d'heure et refuse l'heure sautée en mars.

`GET /agenda.json?from=AAAA-MM-JJ&to=AAAA-MM-JJ` (session, deux mois au plus) → `{enabled, now, from, to, diffusions, weekly, todo}`. Une diffusion : `{id, version, kind, title, starts_at, ends_at, duration_min, guest, host_username, set_title, tracklist, rights, deadline_at, deposit_closes_at, deposit_open, series_id, air_status, air_reason, aired_start, aired_end, prep, prep_reason, file, overrun_seconds}`. `air_status` : `upcoming`, `on_air`, `aired`, `missed`. `prep` : `attendu`, `analyse`, `a_revoir`, `pret`. `weekly` donne les occurrences des émissions hebdo de la période, avec `cancelled` et `replaced_by`.

Écritures, droit `autodj` :

- `POST /agenda/diffusions/preview.json` : les dates d'une répétition, avec leurs conflits.
- `POST /agenda/diffusions.json` `{kind, title, start, end, guest_id | guest_name, host_username, repeat?:{rule, count | until, nth}, only?}` : tout ou rien, chevauchement refusé (409).
- `PUT` / `DELETE /agenda/diffusions/{id}.json` (`?suivantes=1` pour la suite d'une série).
- `PUT` / `DELETE /agenda/diffusions/{id}/file.json` `{path, duration}` : un fichier de la banque.
- `POST` / `DELETE /agenda/exceptions.json` `{emission_id, date}` : annuler une émission hebdo un jour.
- `GET` / `POST` / `PUT` / `DELETE /agenda/guests[/{id}].json`, `POST /agenda/guests/{id}/token.json` (nouveau lien).

`POST /agenda/diffusions/{id}/stop.json` (droit `live`) arrête un set à l'antenne. `PUT /agenda/settings.json` `{enabled}` (admin) coupe ou rallume l'agenda. `GET /agenda/files/{id}/audio` sert le fichier d'un set.

Sans session : `GET /public/guest/{jeton}.json` et `PUT /public/guest/{jeton}/diffusions/{id}.json` `{set_title, tracklist, rights}` (page de l'invité, `/invitation#jeton`). Le dépôt passe par tus avec l'en-tête `X-Invite-Token` ; `GET /agenda/deposit-auth` répond à l'`auth_request` de nginx. Le catalogue appelle `POST /internal/agenda/deposit-check.json` et `POST /internal/agenda/files.json` avec `X-Auth-Token`.

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

`POST /banks.json` (via `/library/banks.json`), corps JSON `{label, folder}` : crée `20-archives/<folder>` et `00-inbox/archives/<folder>`. `folder` : minuscules, chiffres et tirets, 40 caractères au plus. Réservé à un admin. Le dépôt de fichiers reste ouvert à un admin, ou à un droit sur les bacs ou l'auto-DJ. Réponse `201 {destination}`, `400` ou `409 {error}` en français. Un programmateur reçoit `403`.

`GET /volume.json` (via `/library/volume.json`) : `{name, host}`. `name` est le nom du volume Finder. `host` est vide quand le partage n'est pas publié. Droit de dépôt (admin, bacs ou auto-DJ).

`POST /volume-password.json` (via `/library/volume-password.json`), admin seulement, corps `{username, password}` ou `{username, clear: true}`. Pose ou retire le mot de passe du dossier d'un programmateur ou d'un admin. Le mot de passe n'est pas renvoyé. `503` si le partage n'est pas publié, `400` si le compte est un animateur.

