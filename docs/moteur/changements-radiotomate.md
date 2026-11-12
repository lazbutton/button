# Radiotomate — ce qui a changé

28 septembre 2026, complété le 31 octobre 2026.

Ce texte décrit le moteur dans `engine/` par rapport à l’amont [Radiotomate](https://radiotomate.org/) de Martin Kirchgessner, commit `130030bb` (`https://git.sr.ht/~martink/radiotomate`). Licence inchangée : AGPL-3.0-or-later. Le `README.md` et le `CHANGELOG.md` du dossier restent ceux de l’amont.

Sur 127 fichiers de l’amont, 58 sont identiques et 69 ont été modifiés. Les modules nouveaux sont listés plus bas. `radio_data/` (base, YAML, sons de remplacement) est une donnée locale, pas une modification du logiciel.

L’amont programme les carts avec APScheduler et des formules cron. Ici, l’antenne est tenue par des horloges, un conducteur et des files Liquidsoap. La console (`console/`) parle au moteur en JSON. L’interface HTMX d’origine est toujours là.

## Horloges à la place du cron

APScheduler est retiré (`pyproject.toml`, migration v14). Le mode `TIMED` devient `CLOCK`. Les tables `apscheduler_*` sont supprimées. `max_duration` n’est plus un job cron : c’est une minuterie dans le processus (`scheduler/timers.py`). `GET /schedule/<id>` donne la prochaine coupure.

Une horloge est un motif de positions (`musique`, `jingle`, `son`, `pub`), enchaînées ou calées sur une minute. Une ancre est dure ou molle. Les jingles coupent l’auto-DJ, pas le direct, pas un relais, pas un cart déjà à l’antenne. Pendant un harbor, l’horloge se met en pause : elle ne saute rien et n’empile pas les ancres dues pour les lâcher après le direct.

Le tick d’une seconde venu de Liquidsoap ne recalcule l’horloge que si l’état a changé, à la minute, ou à moins de dix secondes de la fin du titre (`live.should_run_tick`).

La séparation des artistes et des titres est dans `scheduler/music_rules.py`.

La requête Beets d’une catégorie passe par `services/beets_query.py`. Beets coupe une requête à ses virgules, et une partie vide y prend toute la bibliothèque : `grouping:jazz,` ferait jouer n’importe quel titre. Les routes JSON des catégories et `testquery.json` refusent une telle requête, comme une requête que Beets ne sait pas lire. L’auto-DJ ignore la partie vide d’une catégorie enregistrée avant ce refus.

## Conducteur et vérité d’antenne

Le scheduler ne pousse plus un son au moment où le cron sonne. Il prévoit une file (`rundown_items`), envoie des commandes (`playout_commands`) et réconcilie ce qui a vraiment joué.

Les statuts d’une ligne vont de `planned` à `played`, en passant par `on_air`, `skipped`, `rescue` ou `failed`. Une commande est `pending`, `acknowledged` ou `expired`.

Liquidsoap 2.4.5 annote chaque push avec `radiotomate_queue`. Le journal d’antenne s’appuie sur cette annotation. Les transitions `fallback` restent en coupe (bug [savonet/liquidsoap#4179](https://github.com/savonet/liquidsoap/issues/4179)) : `current_source_id` seul marquait à tort un cart comme de l’auto-DJ. Le fondu de trois secondes est sur la file auto-DJ, avant le `fallback`.

`/queue/flush` accepte un corps optionnel `{"queues": […]}`, et rend, file par file, `item_ids` : les lignes du conducteur des titres qu’il a retirés, lues dans leur annotation `radiotomate_item_id`. L’URL de relais vient de `playout_process_config.relay_url`. Le script expose aussi `/health`, un gain ReplayGain, et des mesures de charge.

`DELETE /live`, `POST /schedule/<id>/now` et `POST /schedule/<id>/sounds/<id>/now` répondaient 200, que le playout ait fait l’ordre ou non. Ces routes d’ordres du scheduler, avec `POST /schedule/path/now` et `POST /queues/flush`, répondent maintenant 502 `{ok:false, error, detail}` quand il ne l’a pas fait : `playout_unavailable` s’il n’a pas répondu, `playout_rejected` s’il a répondu une erreur. Ces gestes passent par `gesture_gateway_for` : l’ordre part une fois, et ne repart que si la connexion a été refusée. Après un délai, le playout a pu le faire, et le renvoyer passerait deux titres. L’horloge, la boîte d’envoi et l’Agenda gardent leurs essais.

`POST /schedule/<id>/now` répondait aussi 200 quand le cart n’avait aucun son prêt, sans rien pousser. Il répond maintenant 409 `{ok:false, error:"cart_empty", detail}`. Un cart aléatoire dans ce cas levait une `IndexError` : `next_sound_random` rend maintenant `None`, comme les autres modes.

Une playlist simple (`playlist`) passée en entier reprend au début, comme une boucle : `Cart.next_sound_playlist` se replie sur `next_sound_playlist_loop`, et un son prêt jamais passé reste prioritaire. L’amont n’en tirait plus aucun son. L’horloge le faisait déjà de son côté ; `POST /schedule/<id>/now` et le son suivant affiché suivent maintenant la même règle.

`POST /schedule/<id>/now` sur une playlist (`playlist` ou `playlist_loop`) de la file `carts` lance un tour (`clock.CartRound`). L’ordre met deux sons en file, puis l’horloge les suivants (`_refill_active_cart`), chacun une fois au plus. À la fin du tour, l’antenne revient à l’horloge. Une playlist simple joue ses sons jamais passés, ou tous s’ils sont tous passés. Une boucle les joue tous, à partir du son suivant. Avant, l’horloge remettait la suite en file sans fin, jusqu’à l’Agenda. Une ancre, une ligne du pupitre ou un son lancé seul faisaient de même avec leur cart : une pause pub sur une playlist ne finissait plus. Ils ne jouent plus qu’un son, et un tour en cours continue après eux. `POST /queues/flush` arrête le tour. Un tour ne s’arrête faute de carts à l’antenne ou en file qu’après y être passé : un tick parti avec l’état d’avant le lancement ne le coupe pas.

`POST /schedule/<id>/now` sur un cart sans suite à l’horloge, aléatoire ou d’une autre file que `carts`, ne met plus qu’un son en file. Il en mettait deux, tirés au hasard pour un cart aléatoire.

Un cart aléatoire tire sans redite (`services/cart_draw.py`) : chaque son prêt passe une fois par tour, dans un ordre tiré au sort, et d’un tour à l’autre la moitié passée en dernier attend. L’horloge, la prévision du conducteur et `POST /schedule/<id>/now` tirent ainsi. Quand le tour n’a plus que des sons entendus à l’instant, ou prévus par le conducteur, le tour suivant s’ouvre avec le son le plus loin de son dernier passage et du prochain prévu (`_farthest`) : un son jamais dit à l’antenne, comme un fichier devenu illisible, ne bloque pas le cart. Les sons passés dans le tour sont notés quand le playout les dit à l’antenne (`POST /metadata_log`), dans la clé `cart_drawn` de la table `settings` : pas de migration. Le réglage `features.random_no_repeat`, à faux, rend le tirage de l’amont, `Cart.next_sound_random`, qui n’a pas changé.

Une ligne de coupure qui ne partira plus est close, `skipped`, avec sa raison : retenue pendant un direct ou un set daté (`_hold_due_anchors`), ou encore prévue une heure après son heure (`execution.close_past_anchor_lines`, à chaque tick). Elle restait `planned` pour toujours, et le tirage de son cart la comptait comme à venir. Une coupure molle qu’une coupure dure rattrape est « sauté » au conducteur, sans son de son cart, et l’antenne ne la joue plus après la coupure dure (`timing.hard_anchor_since`), si celle-ci est vraiment partie : sa clé est dans `fired_anchors`. La branche `soft-skip` de `_fire_due_soft_anchors` le voulait, mais ne s’exécutait jamais. Le conducteur la saute aussi quand la coupure dure ouvre le créneau suivant (`opening_anchor` de `build_rundown`), et la garde quand la coupure dure n’a rien à jouer. Le réglage `features.skip_overtaken_soft_anchors`, à faux, ne la saute plus, au conducteur comme à l’antenne.

Un titre Beets sans `rg_track_gain` est analysé à la prévision (`analyze_item_soon`), puis au push si le gain manque encore (`ensure_item_gain`). Rien n’est poussé sans gain.

Une ligne de l’horloge retirée au pupitre (`suppress_at`) ne part plus à l’antenne. Le retrait ne faisait que la masquer dans la file, et l’horloge la poussait quand même à son tour. `_load_pushable_sequential` laisse maintenant de côté les lignes qu’un retrait masque (`desk.removed_clock_ids`) : par leur identifiant, ou par leur heure pour un retrait posé par un moteur plus ancien. Quand le retrait expire, 30 s après l’heure de sa ligne, `expire_past_desk_items` la marque `skipped`. Sinon, plus rien ne la masquant, elle partirait en retard. Le réglage `features.skip_removed_lines`, à faux, rend le comportement d’avant.

Une ligne déjà envoyée au playout, de statut `reserved`, `pending_push`, `sent`, `accepted` ou `in_queue`, ne se retire ni ne se déplace plus au pupitre (`desk.item_is_sent`). Liquidsoap la joue dans l’ordre où il l’a reçue, et ne sait pas la rendre : retirée, elle passait quand même, et déplacée, elle gardait sa place. Le retrait (`suppress_at`, `replace_at`), `DELETE` et le réordre la refusent en 409. L’horloge garde deux titres d’avance (`TARGET_QUEUE_DEPTH`) : ce sont en général les deux lignes qui suivent le titre à l’antenne.

Une ligne mise à la suite au pupitre passe maintenant à l’antenne. La console disait « Mis à la suite. » et la montrait dans la file, mais l’horloge ne poussait aucune ligne `origin = "desk"` (`_load_pushable_sequential`), `realign_rundown` les laissait à leur heure, et `expire_past_desk_items` les effaçait passée leur heure de fin. L’exclusion datait de l’import initial, sans raison écrite. L’horloge pousse maintenant une ligne du pupitre à son tour, dans l’ordre de la file, devant la ligne de l’horloge prévue à la même heure, sans avancer le curseur du motif. Une musique part dans la file `autodj`. Un jingle part dans `jingles`, un son ou une pub dans `carts` : Liquidsoap joue ces files avant l’auto-DJ dès qu’elles ont un titre (`fallback` sans `track_sensitive`). La ligne attend donc qu’aucun titre prévu avant elle n’attende plus dans une file qu’elle doublerait, ce que dit la tête de chaque file (`radiotomate_item_id` de `next_autodj` et `next_jingle`), puis la fin du titre à l’antenne, comme un jingle de l’horloge (`clock._line_turn`). Pendant ce temps, l’horloge met en file la musique qui suit la ligne : elle passe après elle de toute façon, et la file de l’auto-DJ ne se vide pas, ce qui laisserait partir en retard les jingles de l’horloge restés « prévu ». Une ligne qui finirait après une coupure dure attend la coupure, et les suivantes avec elle (`clock._desk_would_overflow`).

Mise à la suite, une ligne se place après les lignes déjà envoyées (`desk._sent_end`) : Liquidsoap les joue d’abord. `realign_rundown` la traite comme une ligne de l’horloge. Une ligne envoyée ne se modifie plus (`PATCH`, 409), et `expire_past_desk_items` la garde tant qu’elle attend son tour, une heure au plus. Une ligne poussée que l’on efface, refusée par le playout par exemple, détache d’abord ses commandes, qui la désignent (`desk._detach_commands`), comme le fait la remise à zéro du conducteur. La ligne que pose « Jouer tout de suite » pour un titre de la banque entre `in_queue` : le titre est déjà parti, et l’horloge ne le pousse pas une seconde fois. Datée après le titre à l’antenne, elle passe pourtant tout de suite : elle ne décale pas les lignes suivantes (`desk.PLAYED_NOW`), et sa fin ne compte pas pour placer la ligne mise ensuite à la suite. Un remplacement (`replace_at`) masque ses lignes de l’horloge comme un retrait, et les ferme `replaced` quand il part (`desk.close_replaced`). Le réglage `features.desk_lines_air`, à faux, rend le comportement d’avant.

Les jingles du motif passent de nouveau après le démarrage. Un jingle séquentiel attendait une file de l’auto-DJ vide (`timing.can_push_sequential_jingle`), et `_fill_sequential_from_rundown` le sautait (`continue`) pour pousser la musique d’après. L’horloge gardant deux titres d’avance (`TARGET_QUEUE_DEPTH`), la file ne se vidait plus après le premier jingle : il restait `planned`, et la musique prévue après lui passait à sa place. Sur un banc avec le vrai Liquidsoap 2.4.5, six titres en cinq minutes, aucun jingle. Il suit maintenant la règle des lignes du pupitre (`clock._line_turn`) : il part quand plus aucun titre prévu avant lui n’attend dans la file de l’auto-DJ, à la fin du titre à l’antenne, ou derrière un jingle ou un cart à l’antenne, sans le couper. La musique d’après reste en file, et passe après lui. Un jingle qui attend fait attendre les lignes du pupitre qui le suivent dans les files `jingles` et `carts`, qui passeraient sinon avant lui. Un jingle dont le tour est passé, parce qu’une ligne du motif prévue après lui est passée à l’antenne, est fermé `skipped`, raison « tour passé » : sans cela, il partait en retard dès que la file de l’auto-DJ se vidait, après « Vider les files » ou le retour d’un direct. `reconcile_as_run` le ferme quand cette ligne passe à l’antenne, avant `realign_rundown` : avec le fondu de l’auto-DJ, la ligne commence avant l’heure du jingle, et le recalage la placerait devant lui. À chaque tick, `execution.close_passed_jingles` ferme ceux qu’un moteur plus ancien a laissés `planned`, d’après la dernière ligne du motif passée à l’antenne. Le réglage `features.motif_jingles_air`, à faux, rend le comportement d’avant.

Un vidage des files laissait au conducteur, en `in_queue`, les lignes des titres qu’il avait retirés de Liquidsoap : « Vider les files » (`POST /queues/flush`), le retour d’un direct, et l’Agenda, au début d’un set ou à l’arrêt d’un set encore en file. L’horloge ne pousse que des lignes `planned` : elles ne passaient jamais, et le pupitre les disait « Déjà partie ». `execution.close_flushed_items` les marque maintenant `skipped`, raison « file vidée », d’après les `item_ids` du playout. Le vidage ne retire jamais le titre qu’une file a chargé, à l’antenne ou le suivant : sa ligne reste. Un playout plus ancien ne rend que des comptes : toutes les lignes `sent`, `accepted` ou `in_queue` des files vidées se ferment alors, et le titre chargé, une fois à l’antenne, retrouve sa ligne par son identifiant. `agenda._drop_planned_blocks` n’efface plus une ligne envoyée au playout (`reserved_at`) : ses commandes la désignent.

Le conducteur prévoit maintenant l’ancre posée sur la première minute d’un créneau, comme une ancre à :00 dans un créneau qui commence à 22 h. `build_rundown` ne la voyait jamais venir : `_next_anchor` l’écarte du créneau d’avant, qui finit avant elle, puis du sien, où elle est déjà due quand la prévision y entre. L’antenne la jouait quand même, et tirait son son sans ligne prévue. Quand un titre déborde sur le début du créneau, ou finit pile dessus, la prévision pose maintenant l’ancre avec lui (`opening_anchor`) : dure, à sa minute, où elle coupe le titre ; molle, à la fin du titre, raison « glissement ». La ligne suit le titre dans le même morceau de prévision : le morceau suivant commence après le début du créneau, trop tard pour la voir.

La prévision du conducteur suit maintenant l’ordre d’un cart en playlist ou en boucle. `_next_preview_sound` choisissait un son jamais passé, sinon le premier du cart : il ne regardait ni le son passé en dernier, ni les lignes du cart déjà au conducteur. Or `ensure_forecast` allonge le conducteur par morceaux, chacun bâti sans rien savoir du précédent, et l’horloge pousse la ligne prévue telle quelle. Un cart de trois sons joué une fois par semaine passait A, B, C, A, puis A chaque semaine ; quand l’horloge tire elle-même (`Cart.next_sound`), elle donne A, B, C, A, B, C. Et un son encore `planned` pouvait être prévu de nouveau au morceau suivant. La prévision prend maintenant le son que `Cart.next_sound` donnera une fois passés les sons du cart que le conducteur tient déjà, envoyés au playout ou prévus (`cart_draw.next_in_order`, `CartOrder`) : les lignes que lit aussi le tirage sans redite. Sans ligne tenue, c’est `Cart.next_sound` lui-même. Une ligne déjà prévue n’est pas refaite, et le choix de l’horloge quand elle tire elle-même ne change pas.

L’antenne reprend maintenant la ligne prévue d’une ancre molle glissée hors de sa minute. `build_rundown` date une ancre molle de la fin du titre à cheval sur sa minute, raison « glissement » : une ancre de :20 est prévue à 10:22:16. `_planned_anchor_item` (`scheduler/clock.py`) ne reconnaissait une ligne qu’à l’heure et à la minute de l’ancre. La ligne glissée n’était donc pas trouvée : `_push_cart_to_queue` tirait un son du cart et enregistrait une ligne nouvelle, et la ligne prévue restait `planned`. Le conducteur montrait deux lignes pour une ancre, et un cart aléatoire de plusieurs sons jouait un autre son que celui annoncé : son tirage laisse leur tour aux sons prévus (`CartDraw.pick_now`). Une ligne est maintenant celle de l’occurrence quand elle porte la minute de l’ancre, par son heure ou par `details.minute`, et tombe dans l’heure qui suit cette occurrence, jusqu’à la suivante. La ligne datée de l’heure d’après n’est donc pas reprise, ni celle d’une heure ou d’un jour d’avant restée `planned` sans être passée : un direct qui retient une ancre laisse la sienne ainsi. Avant, celle d’un autre jour à la même heure passait devant celle du jour, pour une ancre dure aussi. Une ancre molle glissée suit donc maintenant la règle des autres lignes prévues, celle d’une ancre dure déjà : la ligne part telle quelle, même si son son a été désactivé depuis la prévision ; l’antenne, en tirant elle-même, prenait un son prêt. « Reconstruire le conducteur » (`reset_conducteur`) refait la prévision. Une ancre dure reste reprise à sa minute, et reprend en plus une ligne prévue quand elle était molle. Seul `_planned_anchor_item` change : le moment où une ancre est tirée reste l’affaire de `_fire_due_anchors` et de `_fire_due_soft_anchors`.

L’antenne joue aussi une ancre molle dont le titre à cheval finit après le changement d’heure. `_fire_due_soft_anchors` ne regardait que l’occurrence de l’heure en cours, sous la clé `(date, heure, minute)` : à 11:00:15, une ancre de :58 attendait 11:58, et celle de 10:58 n’était plus jamais tirée. `build_rundown` la prévoit pourtant à la fin du titre, 11:00:16, raison « glissement », et la ligne restait `planned`. Quand un titre finit, l’horloge pousse maintenant d’abord les lignes prévues des ancres molles de l’heure d’avant (`_soft_lines_astride_the_hour`) : une ligne qui porte la minute de l’ancre et tombe dans l’heure qui suit son occurrence, tant que cette heure n’est pas finie, comme pour `_planned_anchor_item`. La ligne dit l’occurrence : elle vaut aussi quand l’heure nouvelle ouvre un autre créneau ou un autre jour, comme le prévoit le conducteur. La position doit être encore molle, et à cette minute. Jamais sans sa ligne : une remise à zéro du conducteur vide `fired_anchors` et retire les lignes, et une ancre de l’heure d’avant déjà passée ne revient donc pas. `_hold_due_anchors` retient aussi ces occurrences pendant un direct ou un set de l’Agenda. Et `fired_anchors` garde maintenant les clés de l’heure d’avant (`_forget_fired_anchors`) : passé minuit, il oubliait celles de la veille, et une ancre de 23:58 retenue par un direct serait passée après lui.

Une prévision remplace aussi les lignes `failed` qu'elle a prévues elle-même, jamais envoyées (`sent_at` et `closed_at` vides) : une ligne « manquant », sans titre ni cart. `_coverage_rows` ne les compte pas comme prévision tenue, et une station sans rien à jouer refait donc sa prévision à chaque tick, et à chaque appel de `/autodj/conducteur.json`. `replace_forecast_items` n'effaçait que les statuts remplaçables : les lignes manquantes s'empilaient, 17 par seconde au tick, 6 heures de lignes par appel du Conducteur, gardées 7 jours par la rétention. Le scheduler et l'interface en lisaient toujours plus. Elles sont maintenant effacées avec la prévision qu'elles remplacent, même juste passées. Une ligne refusée par le playout, elle, a été envoyée (`closed_at`, par `outbox`) : elle reste.

Une horloge ne lance pas de relais. `Cart.next_sound()` appelle la méthode du mode du cart, et le mode `relay` n'a pas de `next_sound_relay` : une coupure dont le cart était un relais levait `AttributeError` quand l'horloge la tirait elle-même (`_push_cart_to_queue`), faute de ligne prévue, à chaque tick de sa minute, et le reste du tick, motif compris, ne passait pas. `next_sound` rend maintenant `None` pour un relais, même s'il garde des sons d'avant, comme un cart sans son prêt. L'horloge et la prévision passent le relais (`clock._push_cart_to_queue`, `rundown._resolve_cart`) : la position joue son secours, celui de la position puis celui de l'horloge, ou rien. La prévision plaçait les sons restés dans un cart passé en relais, et l'horloge les poussait. Sans secours qui ait un son, la ligne est « manquant », raison « bac en relais », au lieu de « cart introuvable », quand le cart qu'elle nomme, le premier de la position, est le relais. Quand l'horloge tire elle-même une coupure sans ligne prévue, et ne joue rien pour un relais, elle écrit une ligne « sauté », raison « bac en relais », une fois par occurrence (`clock._say_relay_passed`) : sinon le conducteur ne disait rien. La coupure n'entre pas dans `fired_anchors`, et ne rattrape donc aucune coupure molle, comme une coupure dure qui n'a rien à jouer. Une ligne prévue avant que son cart ne passe en relais ne part pas non plus : `_push_existing_rundown_item` relit le mode du cart d'une ligne de l'horloge, et la ferme « sauté », raison « bac en relais » ; la position essaie ensuite ses secours. Une ligne du pupitre part telle quelle. Les routes JSON des horloges refusent un cart en relais, pour une position, son secours ou celui de l'horloge (`domain.autodj.refuse_relay_cart`) : une horloge enregistrée avant, ou dont un cart passe en relais ensuite, tourne comme dit plus haut.

## API pour la console

L’interface HTMX reste. À côté, les mêmes objets ont une forme JSON, avec un jeton CSRF (`GET /csrf.json`, en-tête `X-CSRF-Token`) sur les écritures authentifiées par cookie. `POST /login` et `POST /login.json` en sont exemptés.

| Domaine | Chemins |
| --- | --- |
| Compte | `/account.json`, `/login.json` |
| Utilisateurs | `/users.json`, `/users/hosts.json`, `/users/…/stream-token.json` |
| Carts et sons | `/carts.json`, sons, rangs, lecture immédiate |
| Banque | `/media/bank.json` |
| Horloges | `/autodj/clocks.json`, `/slots.json`, `/categories.json` |
| Conducteur | `/autodj/conducteur.json` |
| Émissions | `/antenne/emissions.json` |
| Antenne | `/live.json`, `/antenne/state.json`, `/antenne/flush.json` |
| Agenda | `/agenda.json`, `/agenda/…`, et sans session `/public/guest/…` |
| Système | `/system/disk.json` |
| Station | `/station.json`, et sans session `/public/station.json` |
| Santé | `/health/live`, `/health/ready` |

Le détail de chaque route est dans [`docs/api.md`](../api.md).

`/antenne`, `/conducteur`, `/programmation`, `/sons` et `/reglages` renvoient la page d’accueil de la console quand son build est posé à côté du moteur (`interface.console_dist`). En production, le nginx de la console sert ces pages lui-même : la console est une application à part, le moteur sert les données.

`stream_form()` lit les sons envoyés en multipart, pour `POST /carts/<id>/sounds` et `POST /carts/<id>/sounds.json`. Un envoi mal formé y répondait 500 : sans `boundary` (`KeyError`), coupé avant la fin (`ParserError` de multipart), avec un champ de texte à la place d’un son (`TypeError` dans la route), ou avec une partie sans nom de fichier qui n’était pas du texte (`UnicodeDecodeError`). Depuis multipart 1.3.1, ce dernier cas est celui d’un son dont le nom finit par `\`, car ce nom ne se lit plus. Ces envois sont maintenant refusés en entier, en 400 : une partie au nom d’un champ de fichiers (`file_fields`) doit être un fichier. Un envoi refusé ou interrompu ne garde aucun des fichiers qu’il avait écrits.

## Agenda

L’Agenda (migration v17) ajoute des émissions à une date précise : un set enregistré, souvent déposé par un invité par un lien privé, ou un direct daté. Les tables `agenda_*` stockent de l’UTC naïf, alors que les tables historiques gardent l’heure locale du conteneur ; les conversions passent par `domain/agenda.py`. Le scheduler fait passer les sets à leur heure (`scheduler/agenda.py`). Les routes de l’invité sont publiques (`interface/public.py`), et le catalogue déclare les fichiers reçus par des routes internes protégées par jeton. Le réglage `agenda_enabled` coupe tout l’Agenda.

## Émissions, banque, comptes

Une émission (`emissions`, migrations v10 et v15) a un titre, un créneau hebdomadaire ou daté, et un `host_username`. Le créneau live sans encodeur est l’alerte `live_absent` (EF-01) : le filet est l’horloge du moment, pas un silence.

Un cart peut pointer un dossier de la banque (`bank_folder`, v12) et marquer ses sons comme pads d’identifiant (`ident_pads`, v16). Les jingles par défaut prennent le dossier `30-habillage/jingles`. Le scheduler rattache au cart les fichiers nouveaux de son dossier (`scheduler/bank_sync.py`), et note ceux qu’il ne prend pas, avec leur raison, dans un fichier `.refus.json` de ce dossier. L’interface les rend dans `skipped_files`.

Chaque personne a une page de compte. Les utilisateurs se créent et se modifient aussi en JSON.

Chaque compte a un jeton d’encodeur (v18, `services/stream_token.py`). L’encodeur l’envoie au harbor à la place du mot de passe du compte. `/can_stream` accepte encore ce mot de passe tant que le réglage `features.allow_account_password` n’est pas faux. Le moteur ne garde du jeton qu’une empreinte SHA-256.

Les échecs de connexion se comptent par adresse, jamais par compte (`domain/login_guard.py`, en mémoire). Au cinquième en quinze minutes, `/login` et `/login.json` refusent l’adresse en 429 pendant quinze minutes, puis le double à chaque nouveau blocage, vingt-quatre heures au plus. Derrière nginx, l’adresse est celle de l’en-tête `X-Real-IP`, que le moteur ne croit que venant de la boucle locale ou d’un réseau privé.

## Exploitation

Le scheduler surveille l’antenne (`scheduler/alerts.py`) : silence, playout injoignable, heartbeat perdu, sortie Icecast coupée, créneau live sans encodeur. Une alerte part une fois, puis une note de retour, vers un webhook JSON ou une tâche Vikunja. Le bloc YAML est `alerts:`.

`/metrics` est écrit dans `data/metrics.json`, et une ligne par heure dans `data/exports/metrics.jsonl`.

`scheduler/retention.py` purge ce qui est fini : conducteur joué, commandes acquittées, versions orphelines. Le journal `metadata_log` est exporté en JSONL avant suppression. Rien de futur n’est effacé.

`radiotomate update` copie la base dans `backups/`, à côté d’elle, avant la première migration due, et garde les cinq dernières copies. Si la copie échoue, aucune migration ne passe. Voir [`exploitation/sauvegarde.md`](../exploitation/sauvegarde.md#la-copie-avant-une-migration). Chaque version du schéma passe ensuite dans sa propre transaction, clés étrangères coupées puis vérifiées : celle qui échoue ne laisse rien. Sur une instance qui existe déjà, `radiotomate install` ne fait que la mettre à jour : si cela échoue, il ne supprime plus sa base ni sa configuration.

`/health/live` et `/health/ready` existent sur l’interface et le scheduler. L’installateur Podman ajoute les sondes correspondantes, et peut monter la banque (`MEDIA_HOST`, `MEDIA_ROOT`) dans les conteneurs.

`radiotomate interface --port` et `radiotomate scheduler --port` changent le port d’écoute, 6811 et 6822 par défaut. En démo, l’interface tient lieu de scheduler sur son propre port : deux bancs tournent sur une machine.

`radiotomate maintenance` regroupe les commandes d’exploitation d’une station, que lance la commande `station` (`commands/maintenance.py`). `maintenance next-live` dit le prochain direct, une émission hebdomadaire ou un direct de l’Agenda, comme la page Antenne de la console : `station status` l’affiche. Une émission hebdomadaire n’y compte pas un jour où l’Agenda l’annule, ou la remplace par une diffusion datée : le calcul passe à la suivante.

`beets/compat.py` corrige l’import de Beets 2.5 sous Python 3.14 : l’ioctl de taille de terminal demandait 4 octets, le noyau en écrit 8.

L’image du playout passe `apt-get upgrade` sur celle de Liquidsoap, que ses auteurs ne reconstruisent pas quand Debian publie un correctif. Liquidsoap garde la version de son tag.

## Marque et interface

`brand.json` et `brand.py` portent le nom affiché (`INTERFACE_NAME`), le logo et les libellés, ceux du logiciel : le `brand.json` du paquet ne donne aucune adresse. Le nom de la station, les adresses de son flux et de son direct, et le lien de son code source se règlent dans la console : des clés `station.*` de la table `settings` (`services/station.py`), sans migration. La console les pose sur son `brand.json`, qui reste le repli. L'adresse du direct se lit aussi par tout compte, pour « Passer en direct » : `GET /station/harbor.json`. Les pages HTMX gardent le nom de `brand.json`. `layout.jinja` est en `lang=fr`, avec `suite.css`. La feuille `sass/_suite.scss` est la charte noir et blanc du pupitre. Les pages HTMX d’origine (live, carts, auto-DJ, utilisateurs) restent servies par le même processus.

## Schéma, de v7 à v18

L’amont s’arrête à v6. Les versions suivantes :

| Version | Effet |
| --- | --- |
| v7 | Catégories musicales, horloges, positions, créneaux du jour et de la nuit |
| v8 | Versions de programmation, lignes de conducteur, commandes vers le playout |
| v9 | La catégorie Rotation cherche `path:/media/10-rotation` |
| v10 | Table des émissions |
| v11 | Les libellés de l’ancienne marque deviennent BUTTON (vidée depuis : toutes les bases l’ont passée) |
| v12 | `carts.bank_folder` |
| v13 | Les crons laissés par défaut passent en mode horloge |
| v14 | Tous les carts `TIMED` passent en `CLOCK`, tables APScheduler supprimées |
| v15 | `emissions.host_username` |
| v16 | `carts.ident_pads` |
| v17 | Agenda : diffusions datées, invités, fichiers des sets, jours annulés des émissions hebdo |
| v18 | `users.stream_token_hash` et `users.stream_token_created_at` : le jeton d’encodeur |

## Modules ajoutés

Horloges et antenne : `scheduler/clock.py`, `timing.py`, `music_rules.py`, `desk.py`, `execution.py`, `rundown.py`, `playout.py`, `antenne.py`, `timers.py`, `queue_cleaner.py`, `bank_sync.py`, `outbox.py`.

Exploitation : `alerts.py`, `metrics.py`, `retention.py`, `health.py`, `interface/health.py`, et `commands/maintenance.py`.

Métier : `domain/`, `services/` (carts, auto-DJ, requêtes Beets, émissions, banque, réglages de la station, jeton d’encodeur), `models/clock.py`, `emission.py`, `execution.py`, `music_category.py`.

Interface : `account.py`, `csrf.py`, `emissions.py`, `integrity.py`, `json_util.py`, `spa.py`, `system.py`.

Agenda : `models/agenda.py`, `domain/agenda.py`, `services/agenda.py`, `scheduler/agenda.py`, `interface/agenda.py`, `interface/public.py`. Banque : `services/media_bank.py`.

Fiches de la bibliothèque : `fiches/`, les règles de l’outil de catalogue de Hopper (texte normalisé, variantes d’un titre, règles, seconde et troisième passes, propositions), sans Quart, sans Beets, sans réseau.

Les tests nouveaux couvrent l’horloge, le conducteur, les alertes, le harbor, la rétention, le CSRF, les JSON d’admin, le tick filtré, l’Agenda et la banque. `liquidsoap --check` sur `playout/radiotomate.liq` fait partie de la vérification.

## Ce qui n’a pas bougé

Le choix d’un son dans un cart (playlist, boucle), à part une playlist simple passée en entier, le tirage sans redite d’un cart aléatoire et un relais, qui n’en donne plus aucun, les filtres Beets de l’auto-DJ, le harbor et les droits des comptes, à part le jeton d’encodeur, les sorties Icecast, PulseAudio et ALSA, et le rendu serveur HTMX. L’installateur Podman et les quadlets restent le chemin d’installation de l’amont, avec les sondes et le montage de banque en plus.
