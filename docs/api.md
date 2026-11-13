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

L'encodeur envoie l'identifiant du compte, et son jeton d'encodeur comme mot de passe (voir [Comptes](#comptes)). Le mot de passe du compte passe aussi, tant que le réglage `features.allow_account_password` de la table `settings` n'est pas faux : `0`, `false`, `off` ou une valeur vide. Une clé absente compte comme vraie. Le moteur relit le réglage à chaque connexion de l'encodeur.

## Routes

La console préfixe `/api` en dev. En prod, nginx ne laisse passer qu’une liste de chemins (`console/docker/nginx.conf.template`) : une route nouvelle doit y entrer, et `console/src/api/nginxRoutes.test.ts` le vérifie. Les mutations envoient `X-CSRF-Token` lu dans `GET /csrf.json` → `{csrf_token}`. Refus : `401 {error:"unauthenticated"}`, `403 {error:"forbidden"}`.

Une erreur métier répond `{error, code, message, field?}`, avec `error` et `message` en français : 400 (`validation_error`), 404 (`not_found`) ou 409 (`conflict`). Ces erreurs viennent de `engine/radiotomate/domain/errors.py`.

Une route que le moteur ne connaît pas répond 404 `{error}`, avec la description par défaut de werkzeug, en anglais : « The requested URL was not found on the server. … ». La console y reconnaît un moteur plus ancien qu'elle (`console/src/api/unknownRoute.ts`), et dit de le mettre à jour.

Moteur arrêté, nginx répond lui-même 502, ou 504 si le moteur tarde, avec sa page HTML. Hors 401, 403, 405 et 413, qui ont chacun leur message, la console traite 502, 503 et 504, et toute erreur dont le corps est du HTML, comme un moteur injoignable (`console/src/api/engineUnreachable.ts`) : elle ne montre jamais ce HTML. Seule exception, un 502 `{error:"playout_unavailable"}` : le moteur répond, mais son playout non. La console dit alors « Le playout ne répond pas. Vérifie l’antenne avant de recommencer. » (`console/src/api/playoutUnavailable.ts`). Sur `/login`, où le moteur répond lui-même en HTML, seul le statut compte. Un 413 dit qu'un envoi dépasse ce que nginx accepte, 512 Mo (`client_max_body_size`) : la console dit de déposer moins de fichiers à la fois. Une erreur que la console doit montrer telle quelle ne prend donc ni 502, ni 503, ni 504.

La console abandonne une lecture JSON (`GET`) restée sans réponse au bout de 10 s, corps compris, et la traite comme un moteur injoignable (`console/src/api/readDeadline.ts`). nginx, lui, attend le moteur une heure. Une route que la console lit répond donc en moins de 10 s : le moteur attend lui-même le scheduler jusqu'à 8 s, sur `/antenne/state.json`.

Un son se lit en entier avant d'être joué, pour la pré-écoute d'un bac ou le casque sur les fichiers du conducteur (`GET /carts/{id}/sounds/{son}`, `GET /autodj/beets/{id}`). Sur un réseau lent, c'est bien plus long que 10 s : le délai vaut pour la réponse, puis pour chaque morceau du son (`withBodyDeadline`). Seul un son qui n'avance plus pendant 10 s est abandonné, et compte comme un moteur injoignable. Le moteur rend lui-même en HTML l'erreur d'un son, introuvable ou absent du disque : comme sur `/login`, seul le statut compte, et seuls 502, 503 et 504 y disent le moteur injoignable.

Un geste (`POST`, `PUT`, `PATCH` ou `DELETE`) a 10 s pour répondre, corps compris, et lier un dossier de la banque à un bac 60 s : le moteur y lit jusqu'à 2000 fichiers (`console/src/api/sendDeadline.ts`). Le jeton CSRF qu'un geste demande d'abord se lit comme une lecture, avec son délai. Passé ce délai, le moteur a peut-être fait le geste : la console l'abandonne et dit « L’automate ne répond pas. Le geste a peut-être été fait : vérifie avant de réessayer. » L'aperçu d'une série de l'Agenda (`POST /agenda/diffusions/preview.json`) ne crée rien : sans réponse, la console le traite comme un moteur injoignable. Une route qui reçoit un geste répond donc en moins de 10 s : pour un geste, le moteur attend lui-même le scheduler 5 s au plus.

Un dépôt de sons en multipart (`POST /carts/<id>/sounds.json`) dure le temps de l'envoi. Tant que le corps part, il n'est coupé que si aucun octet ne part pendant 30 s : nginx garde le corps entier avant de le relayer, le moteur n'a donc rien reçu, et la console dit que l'automate ne répond pas. Après le dernier octet, la console attend la réponse 30 s, puis dit que le geste a peut-être été fait, sans couper le dépôt : le moteur écrit les fichiers sous leur nom dans le dossier du bac, et un dépôt coupé y laisserait un son tronqué, que le scheduler rattacherait au bac.

La forme exacte des objets est dans `console/src/api/types.ts`, et côté moteur dans les fonctions `*_payload` des services. Cette page donne les routes, les droits et les champs qui comptent.

### Santé

`GET /health/live` et `GET /health/ready`, sans session, sur l'interface comme sur le scheduler. `ready` vérifie la base, et pour le scheduler aussi le battement et le playout. Un contrôle sans compte passe par là.

### Site de la station

Deux routes sans session ni cookie, en lecture seule, pour le site web de la station, hébergé sur un autre domaine. Elles répondent `Access-Control-Allow-Origin: *` et `X-Robots-Tag: noindex`, et se gardent en cache (`Cache-Control: public`) ; une erreur répond `no-store`. Elles ne donnent que des titres, des heures, un type, et l'artiste et l'album d'un titre de musique : jamais d'invité, d'animateur, de fichier, de droits, de tracklist ni d'état de préparation. Les titres, artistes et albums de l'historique viennent des tags des fichiers : un site les échappe avant de les mettre dans une page HTML. Les heures sont celles de Paris, à la seconde, avec leur décalage : `2026-10-30T18:00:00+01:00`. nginx les relaie par son bloc `/public/`, limité à 10 requêtes par seconde et par adresse.

Le réglage `features.public_site_routes` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), coupe les deux routes : elles répondent `404 {error, code:"not_found", message}`, en français, avec `no-store`. Une clé absente compte comme vraie. Le moteur relit le réglage à chaque appel.

- `GET /public/programme.json` → `{timezone, from, to, items}`, en cache une minute. Les sept jours qui commencent aujourd'hui, triés par début. Un item : `{starts_at, ends_at, title, kind}`. `kind` vaut `emission` (une émission hebdo), `set` (un set enregistré de l'Agenda) ou `direct` (un direct daté de l'Agenda). Une émission hebdo annulée ce jour-là, ou couverte par une diffusion datée, n'y figure pas ; une diffusion manquée non plus. Quand l'Agenda est coupé (`agenda_enabled`), `items` donne la grille hebdo seule, comme le reste du moteur : sans annulation, ni remplacement, ni diffusion datée.
- `GET /public/historique.json?limit=20` → `{items}`, en cache 15 secondes. Les titres de musique des sept derniers jours, le plus récent d'abord. Un item : `{played_at, title, artist, album}`. `limit` vaut 20 par défaut et 50 au plus ; un nombre illisible ou inférieur à 1 répond 400 (`field: "limit"`). La source est le journal d'antenne (`metadata_log`), et une ligne n'y passe que si elle est rattachée à un élément `musique` du conducteur et jouée par l'automate (files `autodj` ou `carts`). Restent donc dehors les jingles, idents, pubs, sons, sets, directs (`stream`) et relais. Un titre vide est écarté, comme la ligne qu'écrit une synchro dure pour le titre qu'elle coupe (`extra.skipped`) : un titre coupé reste, à l'heure de son début, s'il a été noté à l'antenne avant la coupure. Un titre repris après une coupure ne compte qu'une fois, à l'heure de son début.

### Session

- `POST /login.json` `{username, password}` → `{ok:true, username, permissions}`. Pas besoin de jeton CSRF.
- Les échecs de connexion se comptent par adresse, jamais par compte ([décision 0013](decisions/0013-bloquer-l-adresse-jamais-le-compte.md)). Au cinquième en 15 minutes, l'adresse est bloquée 15 minutes, puis le double à chaque nouveau blocage, 24 heures au plus. Bloquée, elle reçoit `429 {error:"too_many_attempts", retry_in}`, le délai en secondes, avec l'en-tête `Retry-After`, quels que soient l'identifiant et le mot de passe : dès l'échec qui la bloque, jusqu'à la fin du délai. Le formulaire HTMX `POST /login` compte avec `/login.json` : bloqué, il affiche « Trop d'essais. Réessaie dans N minutes. » La console dit de même (`console/src/api/tooManyAttempts.ts`). Tout est en mémoire (`engine/radiotomate/domain/login_guard.py`) : une adresse calme pendant un jour est oubliée, et un redémarrage du moteur les oublie toutes.
- nginx freine aussi `/login` et `/login.json` ensemble : 5 essais par minute et par adresse, après une rafale de 5. Il refuse en 429, et non en 503, son code par défaut, que la console prendrait pour un moteur injoignable. Sa réponse a la forme de celle du moteur : `{error:"too_many_attempts", retry_in:60}`, avec `Retry-After: 60`. Le 429 du moteur passe tel quel.
- L'adresse comptée est celle du client. Derrière un reverse proxy, nginx la lit dans `X-Forwarded-For`, mais seulement venant des adresses de `TRUSTED_PROXIES`, une variable de l'image de la console : des adresses ou des réseaux séparés par des espaces. Par défaut, la boucle locale et les réseaux privés, où est un reverse proxy installé sur la machine ou dans Compose. Sur un réseau privé sans reverse proxy, un poste pourrait alors choisir son adresse : `TRUSTED_PROXIES=127.0.0.1` l'en empêche. nginx passe l'adresse au moteur dans `X-Real-IP`. Le moteur ne croit cet en-tête que venant de la boucle locale ou d'un réseau privé : son port n'est pas publié, seuls nginx et les services de la station le joignent.
- `GET /logout` : ce n’est pas du JSON, c’est une redirection HTML. La console l'attend 10 s au plus, puis oublie sa session quoi qu'il arrive (`console/src/api/sessionLogout.ts`). Sans réponse dans ce délai, sur une connexion refusée, ou sur un 502, 503 ou 504 de nginx, rien ne dit que le moteur a reçu la demande. La session y est peut-être encore ouverte, et son cookie valable : un rechargement la rouvre une fois le moteur revenu. L'écran de connexion le dit.
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

`emission`, ajouté par-dessus, vaut `null` ou `{id, title, artist, state:"waiting"|"on_air", until, scope, start_minute?, day_of_week?}`. `DELETE /live.json` → `{ok:true}` si le compte a `live` (un admin passe). Si le scheduler ne répond pas : `502 {error:"scheduler_unavailable"}`. Si c'est le playout : `502 {error:"playout_unavailable"}`, voir [Antenne](#antenne).

### Conducteur

`GET /autodj/conducteur.json?horizon=360` → `{now, horizon_min, clock, daypart, items, summary}`.

Un item : `{id, at, kind, when, resource, queue, status, status_code, reason, clock, daypart, duration, clock_id, position_id, cart_id, sound_id, origin, path?, artist?, title?, minute?, sync?, category?, cart?}`. `origin` vaut `desk` pour une ligne posée à la main.

Une ligne `planned` ou `rescue` d’un cart en `playlist` ou `playlist_loop` peut changer de son entre deux lectures. Quand l’horloge tire elle-même une coupure de ce cart, faute de ligne prévue à sa minute, les lignes prévues du cart prennent les sons qui suivent, dans l’ordre du cart : `sound_id`, `path`, `resource`, `title` et `duration` changent. Une ligne du pupitre garde le son choisi pour elle, et une ligne de coupure d’avant cette minute garde le sien. Le réglage `features.ordered_lines_follow_clock` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), laisse les lignes prévues telles quelles. Une clé absente compte comme vraie.

Une ligne de coupure qui ne passera pas est `skipped`, avec sa raison dans `reason` :

- `dépassé par une ancre dure` : une coupure molle qu’une coupure dure rattrape, parce que le titre en cours finit après elle, dans le même créneau ou quand la coupure dure ouvre le suivant, à minuit par exemple. Une coupure dure qui n’a rien à jouer ne rattrape rien. L’antenne ne joue pas la coupure molle. Quand le conducteur la prévoit ainsi, sa ligne nomme son cart, sans son (`sound_id` vaut `null`) ; une ligne déjà prévue que l’antenne ferme garde le sien. Le réglage `features.skip_overtaken_soft_anchors` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), ne la saute plus : le conducteur la prévoit, et l’antenne la joue après la coupure dure, comme avant. Une clé absente compte comme vraie ;
- `retenue pendant le direct`, `retenue pendant un set de l'Agenda` : une coupure due pendant un direct ou un set daté, que l’horloge laisse tomber ;
- `heure passée` : une coupure encore prévue une heure après son heure, qui ne partira plus.

Une ligne que la prévision ne peut pas jouer est `failed`, sans `sound_id` : raison `aucun titre Beets` pour une sélection vide, `cart introuvable` pour un cart absent ou sans son prêt, `bac en relais` quand le cart que nomme la ligne, le premier de la position, est un relais. Une horloge ne lance pas de relais : elle passe le cart, puis essaie le secours de la position, puis celui de l'horloge. Une ligne prévue avec un secours est `rescue`, et une coupure que l'antenne tire elle-même, faute de ligne prévue, porte `fallback_used`. Quand l'antenne tire elle-même une coupure dont le cart est un relais, sans secours qui ait un son, elle écrit une ligne `skipped`, raison `bac en relais`, une fois pour l'occurrence, si la prévision n'en a pas. Une ligne de l'horloge prévue avant que son cart ne passe en relais ne part pas : à son tour, elle devient `skipped`, raison `bac en relais`, et la position essaie ses secours.

Un jingle du motif dont le tour est passé est aussi `skipped`, raison `tour passé` : une ligne du motif prévue après lui est passée à l’antenne sans lui. Il ne part plus, même en retard. Le réglage `features.motif_jingles_air` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), rend l’ancien comportement : un jingle du motif attend que la file de l’auto-DJ soit vide, et reste `planned` tant qu’il n’est pas parti. Une clé absente compte comme vraie.

`POST` sur la même URL, `{reset:true}`, exige `autodj`. L’horizon vient de la query (`horizon=30` dans Automate).

Écritures du pupitre, droit `live` : `POST /autodj/conducteur/items.json` (à la suite, ou `{suppress_at, suppress_id}` pour masquer un item d’horloge), `PATCH …/items/{id}.json` (`path`, `kind`, `artist`, `title`, `duration`), `DELETE …/items/{id}.json`, `PUT …/items/ranks.json` `{ids}`, `POST …/now.json`. Elles répondent l'état du pupitre. `PATCH …/items/{id}.json` ne modifie qu'une ligne du pupitre, et `DELETE …/items/{id}.json` n'efface qu'une ligne du pupitre ou un retrait : un item d'horloge est refusé en `409 {error, code:"conflict"}`, avec `error` « Ce passage vient de l'horloge. », ou la raison d'un refus d'abord dû : un item à l'antenne, une ancre dure, un item déjà envoyé au playout. Effacé, il ne reviendrait pas : le conducteur n'ajoute des items qu'après le dernier. Il quitte la file par un retrait, `{suppress_at, suppress_id}`, que l'effacement du retrait lève. Une ligne posée par `POST …/items.json` ne part jamais avant maintenant. Mise à la suite, ou devant une ligne déjà commencée (`before_id`), elle attend aussi la fin du titre à l'antenne. Elle attend de même la fin des items déjà envoyés au playout, que Liquidsoap joue d'abord, dans l'ordre où il les a reçus, même placée devant l'un d'eux : l'horloge en garde deux d'avance. Le scheduler la pousse à son tour, dans la file de son type (`queue`). Une musique part dans `autodj`, à sa place parmi les items de l'horloge, devant celui qui est prévu à la même heure. Un jingle part dans `jingles`, un son ou une pub dans `carts`, deux files qui coupent ce qui joue : la ligne y part quand plus aucun titre prévu avant elle n'attend dans une file qu'elle doublerait, à la fin du titre à l'antenne, ou tout de suite derrière un titre d'une file aussi forte, comme un cart à l'antenne. Une ligne qui finirait après une coupure dure attend la coupure, et les items suivants avec elle. Le conducteur la suit comme un item de l'horloge, `in_queue`, `on_air`, puis `played`, et la décale avec les autres sur ce qui passe vraiment. Une ligne déjà envoyée ne se modifie plus : `PATCH …/items/{id}.json` la refuse en 409. Elle reste dans la file après son heure tant qu'elle attend son tour dans Liquidsoap, une heure au plus. Une ligne posée avec `{replace_at}` passe à la place des items d'horloge qu'elle masque : ils ne partent pas, et deviennent `replaced`, raison « remplacé au pupitre », quand elle part. `{suppress_at, suppress_id}` masque l'item d'horloge `suppress_id`, prévu à l'heure `suppress_at`, et lui seul : un autre item prévu à la même heure exacte, ce qui arrive après des réordres, reste visible, comme un item qu'un réordre range ensuite à cette heure. `{replace_at, replace_id}` ne masque de même que l'item `replace_id`. Un identifiant qui ne désigne pas un item d'horloge prévu à cette heure, hors ancre, est refusé en `409 {error, code:"conflict"}`, avec `error` en français : la file a changé entre-temps. Sans identifiant, comme d'une console plus ancienne, le retrait masque tous les items d'horloge prévus à son heure, hors ancre, au moment où il est posé. Le scheduler ne pousse pas l'item tant que le retrait existe : il passe au suivant. Effacer le retrait par `DELETE …/items/{id}.json`, ce que fait « Annuler », rend l'item au scheduler. Le retrait expire 30 s après cette heure, à la lecture suivante du conducteur : l'item, s'il n'est pas parti, devient alors `skipped`, raison « retiré de la file ». Un item que le scheduler a déjà envoyé au playout, de statut `reserved`, `pending_push`, `sent`, `accepted` ou `in_queue`, ne se retire ni ne se déplace plus : Liquidsoap le joue dans l'ordre où il l'a reçu, et ne sait pas le rendre. `{suppress_at}`, `{replace_at}`, `DELETE …/items/{id}.json` et `PUT …/items/ranks.json` le refusent en `409 {error, code:"conflict"}`, avec `error` en français. Le réglage `features.skip_removed_lines` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), rend l'ancien comportement : l'item masqué passe à son tour. Une clé absente compte comme vraie. `PUT …/items/ranks.json` range les lignes données à la suite les unes des autres, à partir du plus tôt de leurs départs. Une ligne qui prend la première place ne part jamais avant maintenant, ni avant la fin du titre à l'antenne, ni avant celle des items déjà envoyés au playout. Si le scheduler ne répond pas, `POST …/now.json` rend `502 {error:"scheduler_unavailable"}`, et `502 {error:"playout_unavailable"}` si c'est le playout. S'il refuse l'ordre, par exemple pour un fichier que le playout ne sait pas lire : `400 {error, code:"playout_rejected"}`, avec `error` en français. Un titre de la banque n'entre au conducteur, en ligne du pupitre, qu'une fois l'ordre passé, avec ses seuls `path`, `kind`, `artist`, `title` et `duration` : un ordre qui échoue n'y laisse rien. Sa ligne entre en `in_queue` : le titre est déjà dans sa file, et le scheduler ne le pousse pas une seconde fois. À l'antenne, elle ne décale pas les items suivants : elle passe tout de suite, et le titre qu'elle coupe reprend après elle. Le réglage `features.desk_lines_air` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), rend l'ancien comportement : le scheduler ne pousse aucune ligne du pupitre, qui quitte la file une fois son heure passée, sans être allée à l'antenne ; une ligne mise à la suite n'attend que la fin du titre à l'antenne, et celle de `POST …/now.json` reste `planned`. Une clé absente compte comme vraie.

### Programmation

Lecture avec une session, écriture avec le droit `autodj`. Une création répond 201.

- `GET /autodj/clocks.json` → `{clocks}`. Une horloge : `{id, version, name, fallback_cart, fallback_cart_id, motif, anchors}` : `motif` est la suite enchaînée des positions, `anchors` les positions calées sur une minute.
- `POST /autodj/clocks.json` → `{clock}`, `PUT` et `DELETE /autodj/clocks/{id}.json`. Une horloge ne lance pas de relais : `POST` et `PUT` refusent un cart en mode `relay` pour une position, son secours ou celui de l'horloge, en 400 `validation_error`, avec `field` à `cart` ou `fallback_cart` et `error` en français, et rien n'est écrit. Une horloge enregistrée avant ce refus, ou dont un cart est passé en relais depuis, se lit telle quelle.
- `GET /autodj/slots.json` → `{slots}`. Un créneau : `{id, version, day_of_week, minute, title, color, clock_id, clock}`.
- `POST /autodj/slots.json` → `{slot}`, `PUT` et `DELETE /autodj/slots/{id}.json`.
- `GET /autodj/categories.json` → `{categories}`. Une catégorie : `{id, name, query, empty_query, count}`, où `query` est une requête Beets.
- `POST /autodj/categories.json` → `{category}`, `PUT` et `DELETE /autodj/categories/{id}.json`. Une requête refusée répond 400 `validation_error`, avec `field` à `query` ou `empty_query`, et rien n'est écrit : une virgule en trop, comme `grouping:jazz,` ou `, grouping:jazz`, où Beets lirait une partie vide qui prend toute la bibliothèque, un guillemet ouvert, ou une valeur que Beets ne sait pas lire, comme `year:abc`. Une catégorie enregistrée avant ce refus garde sa requête : l'auto-DJ et `count` en ignorent la partie vide.
- `GET /autodj/testquery.json?query=…` → `{count, sample}` : essaie une requête avant de l'enregistrer. Il refuse les mêmes requêtes, de la même façon, avec `field` à `query`.

Une modification d'horloge ou de créneau porte la `version` lue : si l'objet a changé entre-temps, elle est refusée.

### Émissions

`GET /antenne/emissions.json` → `{emissions, current, next}`.

Hebdo : `{id, version, scope:"weekly", title, artist, day_of_week, start_minute, end_minute, host_username}`. Session : `starts_at` / `ends_at` à la place des minutes.

`next` est le prochain direct à venir, celui que la page Antenne annonce (`next_live_slot`) : une émission hebdomadaire, sauf un jour où l'Agenda l'annule ou la remplace par une diffusion datée, ou un direct daté de l'Agenda. Un direct en cours n'est jamais `next` : `current` le nomme. `next` vaut `null` s'il n'y a pas de direct dans la semaine à venir, comme sur la page Antenne : une émission hebdomadaire jusqu'au même jour de la semaine suivante, un direct daté jusqu'à huit jours. `next` porte `{id, title, artist, scope, at, until, day_of_week, start_minute}`. `at` et `until` sont des heures de Paris avec leur décalage : ils datent cette occurrence, celle de la semaine d'après quand l'Agenda annule l'émission de ce soir. `day_of_week` (0 = lundi) et `start_minute` disent le jour et l'heure du début, ceux de l'émission hebdomadaire ou du direct daté. Une émission hebdomadaire a `scope:"weekly"`, son `id` et son `end_minute`. Un direct de l'Agenda a `scope:"dated"`, `kind:"live"` et l'`id` de sa diffusion. Si ce calcul échoue, `next` vaut `null`, le reste de la réponse ne change pas, et le moteur note l'erreur dans son journal. Un moteur plus ancien rend l'émission hebdomadaire suivante sans lire l'Agenda : la console date `at` de la même façon.

`POST` session `{scope:"session", title, artist}` exige le harbor déjà branché et le droit `live`. Il remplace la session en cours. `POST` hebdo `{title, artist, day_of_week, start_minute, end_minute, host_username}` exige `autodj`. Chevauchement refusé.

`PUT /antenne/emissions/{id}.json` modifie une émission hebdo (`autodj`). `DELETE /antenne/emissions/session.json` termine la session en cours (`live`). `DELETE /antenne/emissions/{id}.json` demande `live` pour une session, `autodj` pour une émission hebdo.

### Agenda

Émissions à une date : un set enregistré (`kind:"set"`, un fichier) ou un direct (`kind:"live"`, un compte qui peut se brancher). Les instants sont rendus en heure de Paris avec leur décalage (`2026-11-07T22:00+01:00`). En écriture, `start` / `end` sans décalage sont lus comme une heure de Paris : le moteur gère les changements d'heure et refuse l'heure sautée en mars.

`GET /agenda.json?from=AAAA-MM-JJ&to=AAAA-MM-JJ` (session, deux mois au plus) → `{enabled, now, from, to, diffusions, weekly, todo}`. Une diffusion : `{id, version, kind, title, starts_at, ends_at, duration_min, guest, host_username, set_title, tracklist, rights, deadline_at, deposit_closes_at, deposit_open, series_id, air_status, air_reason, aired_start, aired_end, prep, prep_reason, file, overrun_seconds}`. `air_status` : `upcoming`, `on_air`, `aired`, `missed`. `prep` : `attendu`, `analyse`, `a_revoir`, `pret`. `weekly` donne les occurrences des émissions hebdo de la période, avec `cancelled` et `replaced_by`.

Écritures, droit `autodj` :

- `POST /agenda/diffusions/preview.json` : les dates d'une répétition, avec leurs conflits.
- `POST /agenda/diffusions.json` `{kind, title, start, end, guest_id | guest_name, host_username, repeat?:{rule, count | until, nth}, only?}` : tout ou rien, chevauchement refusé (409).
- `GET /agenda/diffusions/{id}.json` (session) → `{diffusion}`. `PUT` / `DELETE` sur la même adresse (`?suivantes=1` pour la suite d'une série).
- `PUT` / `DELETE /agenda/diffusions/{id}/file.json` `{path, duration}` : un fichier de la banque.
- `POST` / `DELETE /agenda/exceptions.json` `{emission_id, date}` : annuler une émission hebdo un jour.
- `GET` / `POST` / `PUT` / `DELETE /agenda/guests[/{id}].json`, `POST /agenda/guests/{id}/token.json` (nouveau lien).

`POST /agenda/diffusions/{id}/stop.json` (droit `live`) arrête un set à l'antenne. `PUT /agenda/settings.json` `{enabled}` (admin) coupe ou rallume l'agenda. `GET /agenda/files/{id}/audio` sert le fichier d'un set.

Sans session : `GET /public/guest/{jeton}.json` et `PUT /public/guest/{jeton}/diffusions/{id}.json` `{set_title, tracklist, rights}` (page de l'invité, `/invitation#jeton`). Le dépôt passe par tus avec l'en-tête `X-Invite-Token` ; `GET /agenda/deposit-auth` répond à l'`auth_request` de nginx. Le catalogue appelle `POST /internal/agenda/deposit-check.json` et `POST /internal/agenda/files.json` avec `X-Auth-Token`.

### Antenne

`GET /antenne/state.json` → `{at, playout, engine, incidents, listeners, asrun, next_live_slot}`, ou `502 {error:"scheduler_unavailable"}` si le scheduler ne répond pas. `playout` porte `reachable, source, silence_s, rms_db, harbor_s`. Un incident : `{kind, detail, since_s, notified}`. `kind` vaut `silence`, `playout_down`, `heartbeat`, `playout_stalled`, `icecast_down`, `live_absent`, `agenda` ou `disk`. `since_s` compte depuis le début de l'incident quand le moteur le mesure, comme la première seconde d'un silence, sinon depuis le relevé qui l'a vu. `playout_stalled` dit un playout figé : l'antenne passe le même son en boucle, et sa file n'avance plus. Le scheduler l'ouvre quand deux signes tiennent ensemble : le temps restant des battements du playout n'a pas bougé pendant 15 s d'antenne (`alerts.stall_seconds`), et le niveau que rend le playout, lu deux fois à une seconde et demie d'écart, est le même au chiffre près, un battement entre les deux disant que l'antenne a continué. Il le ferme quand le temps restant bouge de nouveau, quand les battements s'arrêtent, ou après cinq minutes d'une antenne dont le niveau bouge, un long programme passé par-dessus la file figée. Le réglage `features.stalled_playout_alert` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), coupe cet incident, et lui seul. Une clé absente compte comme vraie. Le scheduler relit le réglage à chaque tour de sa surveillance. `notified` dit s'il est parti vers une cible, ntfy, e-mail, webhook ou Vikunja, et pas seulement au journal. Le scheduler relève les incidents même sans alerte réglée ; `alerts.enabled: false`, dans `radiotomate.yaml`, coupe ce relevé, et `incidents` reste vide. `next_live_slot` est le direct en cours ou le prochain, `{title, label, starts_in_s, active}`, ou `null` s'il n'y en a pas d'ici 7 jours : un direct daté de l'Agenda, ou une émission hebdomadaire, sauf un jour où l'Agenda l'annule ou la remplace par une diffusion datée. `POST /antenne/flush.json` → `{ok:true}`, droit `live`, ou `502 {error:"scheduler_unavailable"}`. Il arrête aussi un bac lancé : l'horloge ne met plus ses sons suivants en file. Les lignes du conducteur dont il retire le titre passent `skipped`, raison « file vidée », et l'horloge reprend aux lignes suivantes. Le titre à l'antenne finit, et celui qu'une file a déjà chargé passe : leurs lignes restent.

Les gestes d'antenne passent par le scheduler, puis par le playout : « Suivant » (`DELETE /live.json`), « Vider les files » (`POST /antenne/flush.json`), jouer tout de suite un bac, un son ou une ligne du pupitre. Si le playout ne répond pas, arrêté ou figé, ils rendent `502 {error:"playout_unavailable"}`. « Suivant » et « Vider les files » le rendent aussi pour toute autre erreur du scheduler ou du playout. Un playout seulement lent a pu faire l'ordre : le scheduler ne renvoie un geste que si la connexion a été refusée, et l'interface attend son verdict jusqu'à 12 s.

### Carts

`GET /carts.json` → `{carts:[…]}`. Un cart : `{id, version, title, notes, mode, url, queue, max_duration, bank_folder, ident_pads, skipped_files:[…], sounds:[…]}`.

`mode` vaut `playlist`, `playlist_loop`, `random` ou `relay`. Ce n’est pas `clock` / `loop` / `once`. En `playlist`, les sons prêts jamais passés partent d’abord, dans l’ordre ; quand il n’y en a plus, la playlist reprend au début, comme `playlist_loop`. En `random`, le moteur tire sans redite : chaque son prêt passe une fois par tour, dans un ordre tiré au sort, et d’un tour à l’autre la moitié des sons passée en dernier attend. Un son compte comme passé quand le playout le dit à l’antenne, et ceux que le conducteur prévoit déjà gardent leur tour. Quand le tour n’a plus que des sons entendus à l’instant, ou que le conducteur prévoit déjà tous les autres, le tour suivant s’ouvre avec le son le plus loin de son dernier passage et du prochain prévu ; à égalité, celui entendu le moins récemment. Le réglage `features.random_no_repeat` de la table `settings`, à faux (`0`, `false`, `off` ou une valeur vide), rend l’ancien tirage, parmi tous les sons prêts à chaque fois. Une clé absente compte comme vraie. `next_sound_id` est le son que « Diffuser maintenant » jouerait : `null` en `random`, en `relay`, ou si aucun son n’est prêt. `schedule_mode` est à part (`clock`, `jingles`, `timed`). `url` n’est rempli qu’en `relay`. `ident_pads` est le drapeau des pads. Un son : `{id, rank, title, duration, active, available, gain, peak, last_played, uploader, path}`.

`skipped_files` dit les fichiers du dossier du bac que le scheduler n’a pas pris : `{path, reason}`. `path` est le chemin du fichier dans ce dossier, ou `.` pour le dossier entier, quand il a plus de 2000 fichiers audio : le bac n’en prend alors plus aucun. `reason` est en français, à afficher tel quel : « ce n'est pas un fichier audio », « durée illisible », « lecture impossible », « fichier vide », « l'automate ne lit pas ce format » pour un `.wma` ou un `.webm`, ou la raison du plafond. Le scheduler tient cette liste à chaque relevé du dossier, toutes les 12 s, dans un fichier `.refus.json` posé dans ce dossier. Un fichier changé depuis moins de 10 s n’y entre pas encore, ni un fichier vide depuis moins de 45 s : il arrive peut-être. Un fichier en sort quand il entre dans le bac, ou quand il quitte le dossier. La liste est vide pour un relais. Un moteur plus ancien n’envoie pas le champ : la console le lit comme une liste vide.

Créer un relais : `POST /carts.json` avec `mode:"relay"`, une URL HTTP complète et `max_duration` en secondes. Sans durée max, le moteur répond 400.

Écritures, droit `carts` :

- `POST /carts.json` → `201 {cart}`, `PUT /carts/{id}.json` avec la `version` lue → `{cart}`, `DELETE /carts/{id}.json`. Un bac changé depuis cette version est refusé, sans rien écrire : `409 {error, code:"conflict", message, field:"version"}`. Sans `version`, le moteur ne compare pas. La version suit la ligne du bac, et pas seulement ses réglages : la durée moyenne, quand les pages HTMX du moteur la recalculent à l'ajout d'un son, et les pads d'idents, retirés d'un bac quand un autre les prend, la font aussi monter. Sur ce refus, la console relit le bac, et ne renvoie, une fois, que si rien de ce qu'elle envoie n'a changé entre-temps, ou seulement pour la valeur qu'elle envoie.
- `POST /carts/{id}/sounds.json` : des fichiers envoyés (multipart, `?delta=1` pour répondre seulement le cart), ou `{folders:[…]}` pour rattacher des dossiers de la banque. Un envoi coupé ou mal formé, ou un fichier dont le nom ne se lit pas, comme un nom qui finit par `\`, fait refuser tout l’envoi : `400 {error}`, avec `error` en français, et aucun fichier de l’envoi ne reste.
- `POST /carts/{id}/sounds/delete.json` `{ids}` → `{cart}`.
- `PUT /carts/{id}/sounds/{son}.json`, par exemple `{title}` ou `{active}` → `{cart, sound}` ; `DELETE` → `{cart}`.
- `PUT /carts/{id}/sounds/ranks.json` `{ranks:[ids]}` → `{cart}`.

Jouer tout de suite, droit `live` : `POST /carts/{id}/now.json` et `POST /carts/{id}/sounds/{son}/now.json` → `{ok:true}`. Sur un bac `playlist` ou `playlist_loop` de la file des carts, `POST /carts/{id}/now.json` joue le bac une fois, à partir de `next_sound_id` : deux sons partent, puis l'horloge met les suivants en file, chacun une fois au plus. En `playlist`, ce sont les sons jamais passés, ou tous s'ils sont tous passés ; en `playlist_loop`, tous. Un autre bac, ou un son seul, ne joue qu'un son. Pendant un direct : `409 {error, code:"harbor_live"}`. Un bac dont aucun son n'est prêt, c'est-à-dire actif et analysé : `POST /carts/{id}/now.json` rend `409 {error, code:"cart_empty"}`, avec `error` en français, et rien ne part à l'antenne. Une playlist simple déjà passée en entier n'en fait pas partie : elle reprend au début, comme à l'horloge. Si le scheduler ne répond pas : `502 {error:"scheduler_unavailable"}`. Si c'est le playout : `502 {error:"playout_unavailable"}`. S'il refuse l'ordre : `400 {error, code:"playout_rejected"}`, comme au pupitre.

### Banque

`GET /media/bank.json` (session) → `{available, folders:[{path, count}]}` : les dossiers de la banque qu'un cart peut rattacher. `available` est faux si la banque n'est pas montée.

### Système

`GET /system/disk.json` → `{total, used, free, path}` : espace disque de la banque (`MEDIA_ROOT`). Droits `carts` ou `autodj`, sinon 403 ; 503 si le disque est illisible.

`GET /system/version.json`, admin seulement → `{version, recorded_at, services}` : la version de la station, `BUTTON_VERSION`, et pour chaque service `{service, image, version}`, triés par service. `version` y est celle que porte l'image, `org.opencontainers.image.version`, ou `null` pour une image qui ne la dit pas. L'interface n'a pas accès à Docker : la commande `station` relève ces versions après chaque installation, mise à jour ou restauration, dans `versions.json`, dans le dossier des données du moteur. `recorded_at`, l'heure de Paris à la minute, dit depuis quand elles tournent. Sans relevé, sur une station installée sans la commande `station` par exemple : `{version: null, recorded_at: null, services: []}`. Une station relancée à la main, par `docker compose up`, garde le relevé d'avant.

Les mises à jour, depuis la console (MAJ-07). La console ne touche jamais la machine ([décision 0004](decisions/0004-la-console-ne-pilote-jamais-docker.md)) : « Mettre à jour maintenant » écrit une demande dans le moteur, dans `RT_DATA/updates/`, et la commande `station` de la machine la lit, puis la ferme, par `radiotomate maintenance updates` : voir [deploiement.md](deploiement.md#depuis-la-console). Un moteur plus ancien n'a pas ces routes : il répond 404, et la page dit de le mettre à jour.

`GET /system/updates.json`, admin seulement → ce que montre **Réglages → Mises à jour** :

- `installed` : la version de la station, `BUTTON_VERSION`, comme la machine l'a dite, sinon comme `versions.json` la donne ; `recorded_at` et `services`, comme `GET /system/version.json`.
- `latest` : la plus haute version publiée, celle que `station update` installe sans option, lue sur GitHub, ou `null`. `check` : `{at, error, pending}`, l'heure de la lecture, ce qui n'a pas marché, en français, et si une lecture est en cours. Le moteur relit GitHub au bout de 30 minutes, 5 après un échec ; `?refresh=1` le relit, une fois la minute au plus. Une réponse attend GitHub 4 s au plus : sinon, la suivante a la version.
- `releases` : les versions qu'apporte la mise à jour, au-dessus de celle de la station, de la plus récente à la plus ancienne, dix au plus : `{version, published_at, url, notes, major, action}`. `notes` est le texte de la page de la version, en Markdown. `major` est vrai pour une version X.0.0 au-dessus de celle de la station, et `action` porte alors son paragraphe « Mise en service ».
- `major` : `{version, action, url}`, la première version majeure que passe la mise à jour, ou `null`. Elle ne part pas d'une demande.
- `host` : ce que la machine a dit d'elle, `{seen_at, requests, command, hold, nightly, time, zone}`, ou `null` quand elle n'a jamais rien dit, une station sans la commande `station`, ou d'avant ce bouton. `requests` dit si elle prend les demandes de la console ; `hold`, le texte de `HOLD` ; `command`, la version de sa commande `station` ; `nightly`, `time` et `zone`, ses mises à jour automatiques, `BUTTON_UPDATES` et leur heure. `history` : les dernières lignes de son `updates.log`, `{started_at, from, to, result, label, detail}`, la plus récente d'abord. `result` vaut `done`, `stopped`, `rolled_back`, `failed`, `rollback`, `rollback_failed` ou `other`, et `label` dit le résultat comme `updates.log`.
- `request` : la demande ouverte, `{id, state, requested_at, requested_by, from, target, waiting, started_at, seen_at, unseen}`, ou `null`. `state` vaut `pending` tant que la machine ne l'a pas lancée, puis `running`. `waiting` dit pourquoi elle attend, avec les mots de la machine ; `unseen`, que la machine ne l'a pas regardée depuis 3 minutes.
- `last` : la dernière demande close, `{id, result, detail, requested_at, requested_by, finished_at, from, to}`. `result` vaut `done`, `rolled_back` (la mise à jour a échoué, et la station est revenue seule à la version d'avant), `failed`, `refused`, `up_to_date`, `withdrawn` ou `interrupted` ; `detail` le dit, en français.
- `blocked` : `{code, message}`, pourquoi le bouton ne demande pas maintenant, ou `null`. `code` vaut `open`, `no_host`, `requests_off`, `host_silent` (rien de la machine depuis 2 heures), `hold`, `main`, `unknown_version`, `latest_unknown`, `up_to_date` ou `major`, et `message` le dit en français, avec quoi faire.

`POST /system/updates/request.json`, admin seulement, sans corps → `202`, et la même réponse : la demande, `pending`. La machine la prend dans la minute. Quand le bouton ne peut pas demander : `409 {error, code, message}`, avec le `code` de `blocked`.

`DELETE /system/updates/request.json`, admin seulement → la même réponse, la demande retirée : `last.result` vaut `withdrawn`. Une demande que la machine a lancée ne se retire plus : `409`, `code: "running"`. Sans demande : `409`, `code: "none"`.

### Comptes

`GET/POST /users.json`, `PUT/DELETE /users/{id}.json`, admin seulement. Un compte : `{id, username, notes, permissions}`. `PUT` accepte `notes`, `password`, `permissions`, `username`.

`GET /users/hosts.json`, droit `autodj` → `{hosts}` : les identifiants des comptes qui peuvent passer en direct, admins compris, sans le reste de leur fiche. C'est la liste où un programmateur choisit l'animateur d'une émission hebdomadaire, « Compte du plateau », ou d'un direct daté de l'Agenda. Un moteur plus ancien n'a pas la route : la console reprend `/users.json`, que seul un admin lit, et dit à un programmateur de mettre à jour le moteur.

Le jeton d'encodeur, un par compte :

- `GET /users/me/stream-token.json` → `{created_at}` pour le compte connecté, quel que soit son rôle. `created_at` est l'heure de Paris à la minute, ou `null` sans jeton.
- `POST /users/me/stream-token.json`, sans corps → `{token, created_at}`. Crée le jeton, ou le remplace : l'ancien est refusé dès la connexion suivante de l'encodeur. C'est la seule réponse qui porte le jeton, avec `Cache-Control: no-store`. Le moteur n'en garde qu'une empreinte SHA-256.
- `GET` et `POST /users/{id}/stream-token.json` : la même chose pour un autre compte, admin seulement. Compte inconnu → 404.

Un moteur plus ancien que la console n'a pas ces routes : il répond 404, et la console dit de le mettre à jour.

### Station

Les réglages de la station sont dans la table `settings` du moteur, sous des clés `station.*` : `name`, `short`, `tagline`, `locale`, `public_stream_url`, `now_url`, `status_url`, `harbor_host`, `harbor_port`, `harbor_mount` et `source_url`. Chaque valeur est une chaîne, ou `null` quand la station ne l'a pas réglée. `harbor_port` est un entier. Une station les change dans la console, Réglages → Station, sans reconstruire d'image.

- `GET /public/station.json`, sans session → ce qu'un auditeur voit : `{name, short, tagline, locale, public_stream_url, now_url, status_url, source_url}`, jamais le harbor. La réponse porte `Cache-Control: no-store`.
- `GET /station/harbor.json`, pour tout compte connecté → ce que vise l'encodeur : `{host, port, mount}`, rien d'autre. `host` vaut `null` tant qu'un admin ne l'a pas réglé. Sans réglage, `port` vaut 6800 et `mount` `/stream`, ceux du logiciel. Sans session : 401.
- `GET /station.json`, admin seulement → les onze réglages, plus `timezone`, le fuseau, en lecture seule. C'est la variable `TZ` des conteneurs ([ADR 0005](decisions/0005-le-fuseau-est-celui-des-conteneurs.md)).
- `PUT /station.json`, admin seulement → la même forme que `GET`. Seules les clés présentes changent, et une valeur vide ou `null` efface le réglage. Les autres clés sont ignorées. C'est tout ou rien : une valeur refusée répond 400 `validation_error` avec son `field`, et rien n'est écrit. `timezone` est refusé s'il diffère du fuseau en place.

Les règles d'une valeur : un nom de 80 caractères au plus, un nom court de 16 et une accroche de 120, sur une seule ligne ; une langue comme `fr` ou `fr-FR` ; une adresse complète, en `http://` ou `https://`, de 500 caractères au plus, sans identifiant ni mot de passe, puisqu'elle se lit sans session ; un hôte sans `http://`, ni chemin, ni port, ou une adresse IP, IPv6 sans crochets ; un port de 1 à 65535 ; un mount qui commence par `/`, comme `/stream`.

La console lit `GET /public/station.json` avant la connexion, puis pose chaque réglage sur sa marque, `brand.json` : un réglage `null` garde la valeur de `brand.json` (`console/src/api/station.ts`). Elle n'attend la réponse que 3 s. Face à un moteur sans la route (404), elle garde `brand.json` tel quel. Face à un moteur injoignable, en erreur ou trop lent, elle le garde aussi, mais relit les réglages toutes les 15 s, jusqu'à une réponse. Un moteur plus ancien que la console n'a pas `GET /station.json` : l'onglet Station dit alors de mettre à jour le moteur. Ouvert, l'onglet pose aussi sur la console les réglages qu'il vient de lire. La page d'un invité prend aussi le nom réglé : c'est `station` dans `GET /public/guest/{jeton}.json`.

La console ne prend aucune adresse en repli, et le `brand.json` de son image n'en donne aucune ([ADR 0007](decisions/0007-la-marque-est-une-configuration.md)). Sans flux public, ni réglé ni dans un `brand.json` monté par la station, le casque se cache et dit qu'un admin le règle dans Réglages → Station. Sans `now_url` ni `status_url`, il ne dit pas le titre en cours.

Le panneau « Passer en direct », ouvert à tout compte, lit `GET /station/harbor.json` à chaque ouverture. Sans hôte réglé, il cache les réglages de l'encodeur et dit qu'un admin le règle dans Réglages → Station. Face à un moteur sans la route (404), il dit de mettre à jour le moteur.

La politique de sécurité du contenu (CSP) de la console ne suit pas ces réglages. Les origines du flux et de `now.json` y viennent de `CSP_MEDIA_SRC` et `CSP_CONNECT_SRC`, deux variables de l'image de la console. Changer l'adresse du flux dans l'onglet Station ne les change pas : le navigateur signale alors l'écart dans sa console, sans rien bloquer tant que la CSP reste en `Report-Only`. Voir [les en-têtes de sécurité](deploiement.md#les-en-têtes-de-sécurité).

### Catalogue (service à part du moteur)

Le catalogue demande une session sur toutes ses routes, sauf `/health`, `/health/live` et `/tus-hook`, qu'appelle tusd. La recherche et la pré-écoute, `GET /library/media/{id}` avec requêtes Range, sont ouvertes à tous les rôles. Les routes `POST` demandent un admin. nginx vérifie la session devant `/library/` (`auth_request`) : sans session, il rend `401`, et `500` si le moteur ne répond pas. Le catalogue la vérifie aussi, par `/account.json`, car son port se joint sans nginx : `401 {error}` sans session, `502 {error}` si le moteur ne répond pas. Quand une pré-écoute échoue, la console redemande la même adresse en `HEAD` : l'élément audio ne donne pas le statut, et un `401` y veut dire que la session a expiré.

`GET /library/search?q=&limit=&kind=&grouping=&folder=&top=` est le service catalogue (`services/catalog`). Réponse : `{hits:[{id, path, title, artist, kind, grouping, folder, top, duration}], estimatedTotalHits}`. Une liste séparée par des virgules fait un OU : `grouping=matinale,jazz`. `top` est le dossier de premier niveau : `top=20-archives` donne toutes les banques d'archives.

`GET /inbox.json` (via `/library/inbox.json`) : `{destinations, quota:{used, limit}, disk:{total, used, free}, queue, rejected, progress}`. L’envoi reprend par tus sur `/tus/`, pas par Radiotomate.

`quota` : `used` compte les fichiers de `00-inbox`, `10-rotation` et `20-archives`, `limit` vient de `INBOX_QUOTA_BYTES`. `disk` est le disque sous la banque, comme le voit `df`, en octets. Il vaut `null` quand le catalogue ne le lit pas, et manque dans un catalogue plus ancien. La console montre la limite qu'un envoi rencontre en premier : le disque, ou le quota s'il laisse moins de place.

Un envoi, de la Banque ou d'un invité de l'Agenda, arrive d'abord dans le dossier de tusd, puis il est copié dans la banque. Le catalogue le refuse, « pas assez de place sur le disque », quand il ne tient pas sur le disque, quel que soit le quota. Au début de l'envoi, il doit y tenir deux fois si tusd est sur le même disque que la banque ; à son arrivée, une fois, pour la copie. Une copie coupée ne laisse rien dans la banque, et un envoi refusé quitte le dossier de tusd. Un envoi de la Banque qui ferait passer `used` au-dessus de `limit` est refusé, « quota dépassé ». Chaque envoi se juge seul : des envois lancés ensemble ne se comptent pas entre eux.

`destinations` : `[{id, label, group, folder}]`. D'abord `rotation`, puis une banque par dossier de `20-archives` (sauf ceux qui commencent par `.` ou `_`). `id` est le nom du dossier, et la métadonnée `destination` de l'envoi tus. `label` vient du fichier `.banque.json` du dossier (`{"nom": "…"}`), sinon du nom du dossier.

`POST /banks.json` (via `/library/banks.json`), corps JSON `{label, folder}` : crée `20-archives/<folder>` et `00-inbox/archives/<folder>`. `folder` : minuscules, chiffres et tirets, 40 caractères au plus. Réservé à un admin. Le dépôt de fichiers reste ouvert à un admin, ou à un droit sur les bacs ou l'auto-DJ. Réponse `201 {destination}`, `400` ou `409 {error}` en français. Un programmateur reçoit `403`.

`GET /volume.json` (via `/library/volume.json`) : `{name, host}`. `name` est le nom du volume Finder. `host` est vide quand le partage n'est pas publié. Droit de dépôt (admin, bacs ou auto-DJ).

`POST /volume-password.json` (via `/library/volume-password.json`), admin seulement, corps `{username, password}` ou `{username, clear: true}`. Pose ou retire le mot de passe du dossier d'un programmateur ou d'un admin. Le mot de passe n'est pas renvoyé. `503` si le partage n'est pas publié, `400` si le compte est un animateur.

### Code source (servi par nginx)

Le lien « Code source » du menu du compte mène au code de la version en service, que l'AGPL doit à chaque personne qui se sert de la console. Ce n'est pas une route du moteur : l'image de la console porte ce code, et son nginx le sert sous `/code-source/`, à une session seulement, comme `/library/` : sans session, `401`, et `500` si le moteur ne répond pas ([ADR 0018](decisions/0018-la-station-sert-son-code-source.md)).

- `GET /code-source/source.json` → `{version, commit, file}` : la version, `X.Y.Z` ou `main`, le commit, et le nom de l'archive, comme `button-1.0.0-source.tar.gz`. `scripts/version.py source` l'écrit à côté de l'archive.
- `GET /code-source/source.tar.gz` → l'archive, ce que `git archive` fait du commit, sous un nom qui ne change pas d'une version à l'autre : le Dockerfile le lui donne. Elle répond aussi sous son nom, `GET /code-source/{file}`. La version joint le même code à sa page, fait par la même commande, depuis le même commit.

Une image construite sans le code, par `docker compose build` par exemple, répond `404`. La console lit `source.json` une fois connectée, puis à chaque ouverture du menu du compte (`console/src/api/sourceCode.ts`) : une mise à jour de la station change l'archive sous une page restée ouverte. Sans réponse sûre, elle garde ce qu'elle savait. Le lien télécharge `source.tar.gz`, enregistré sous le nom `file` ; sans archive, il mène au dépôt de BUTTON. Le réglage `source_url` de la station passe devant les deux : une station qui sert une version modifiée y donne l'adresse de son code.

