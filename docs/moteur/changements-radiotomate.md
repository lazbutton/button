# Radiotomate — ce qui a changé

28 septembre 2026, complété le 31 octobre 2026.

Ce texte décrit le moteur dans `engine/` par rapport à l’amont [Radiotomate](https://radiotomate.org/) de Martin Kirchgessner, commit `130030bb` (`https://git.sr.ht/~martink/radiotomate`). Licence inchangée : AGPL-3.0-or-later. Le `README.md` et le `CHANGELOG.md` du dossier restent ceux de l’amont.

Sur 127 fichiers de l’amont, 58 sont identiques et 69 ont été modifiés. Les modules nouveaux sont listés plus bas. `radio_data/` (base, YAML, sons de remplacement) est une donnée locale, pas une modification du logiciel.

L’amont programme les carts avec APScheduler et des formules cron. Ici, l’antenne est tenue par des horloges, un conducteur et des files Liquidsoap. La console (`console/`) parle au moteur en JSON. L’interface HTMX d’origine est toujours là.

## Horloges à la place du cron

APScheduler est retiré (`pyproject.toml`, migration v14). Le mode `TIMED` devient `CLOCK`. Les tables `apscheduler_*` sont supprimées. `max_duration` n’est plus un job cron : c’est une minuterie dans le processus (`scheduler/timers.py`). `GET /schedule/<id>` donne la prochaine coupure.

Une horloge est un motif de positions (`musique`, `jingle`, `son`, `pub`), enchaînées ou calées sur une minute. Une ancre est dure ou molle. Les jingles coupent l’auto-DJ, pas le direct, pas un relais, pas un cart déjà à l’antenne. Pendant un harbor, l’horloge se met en pause : elle ne saute rien et n’empile pas les ancres dues pour les lâcher après le direct.

Le tick d’une seconde venu de Liquidsoap ne recalcule l’horloge que si l’état a changé, à la minute, ou à moins de dix secondes de la fin du titre (`live.should_run_tick`).

Deux grilles prêtes : `Jour habillé` (jingle et trois titres, ancre dure à l’heure, de 7 h à minuit) et `Nuit nappe` (virgule et six titres, ancre molle, de minuit à 7 h). La commande `radiotomate ntf-grille` les pose et crée des sons de remplacement dans la banque.

La séparation des artistes et des titres est dans `scheduler/music_rules.py`.

## Conducteur et vérité d’antenne

Le scheduler ne pousse plus un son au moment où le cron sonne. Il prévoit une file (`rundown_items`), envoie des commandes (`playout_commands`) et réconcilie ce qui a vraiment joué.

Les statuts d’une ligne vont de `planned` à `played`, en passant par `on_air`, `skipped`, `rescue` ou `failed`. Une commande est `pending`, `acknowledged` ou `expired`.

Liquidsoap 2.4.5 annote chaque push avec `radiotomate_queue`. Le journal d’antenne s’appuie sur cette annotation. Les transitions `fallback` restent en coupe (bug [savonet/liquidsoap#4179](https://github.com/savonet/liquidsoap/issues/4179)) : `current_source_id` seul marquait à tort un cart comme de l’auto-DJ. Le fondu de trois secondes est sur la file auto-DJ, avant le `fallback`.

`/queue/flush` accepte un corps optionnel `{"queues": […]}`. L’URL de relais vient de `playout_process_config.relay_url`. Le script expose aussi `/health`, un gain ReplayGain, et des mesures de charge.

`DELETE /live`, `POST /schedule/<id>/now` et `POST /schedule/<id>/sounds/<id>/now` répondaient 200, que le playout ait fait l’ordre ou non. Ces routes d’ordres du scheduler, avec `POST /schedule/path/now` et `POST /queues/flush`, répondent maintenant 502 `{ok:false, error, detail}` quand il ne l’a pas fait : `playout_unavailable` s’il n’a pas répondu, `playout_rejected` s’il a répondu une erreur. Ces gestes passent par `gesture_gateway_for` : l’ordre part une fois, et ne repart que si la connexion a été refusée. Après un délai, le playout a pu le faire, et le renvoyer passerait deux titres. L’horloge, la boîte d’envoi et l’Agenda gardent leurs essais.

`POST /schedule/<id>/now` répondait aussi 200 quand le cart n’avait aucun son prêt, sans rien pousser. Il répond maintenant 409 `{ok:false, error:"cart_empty", detail}`. Un cart aléatoire dans ce cas levait une `IndexError` : `next_sound_random` rend maintenant `None`, comme les autres modes.

Une playlist simple (`playlist`) passée en entier reprend au début, comme une boucle : `Cart.next_sound_playlist` se replie sur `next_sound_playlist_loop`, et un son prêt jamais passé reste prioritaire. L’amont n’en tirait plus aucun son. L’horloge le faisait déjà de son côté ; `POST /schedule/<id>/now` et le son suivant affiché suivent maintenant la même règle.

`POST /schedule/<id>/now` sur une playlist (`playlist` ou `playlist_loop`) de la file `carts` lance un tour (`clock.CartRound`). L’ordre met deux sons en file, puis l’horloge les suivants (`_refill_active_cart`), chacun une fois au plus. À la fin du tour, l’antenne revient à l’horloge. Une playlist simple joue ses sons jamais passés, ou tous s’ils sont tous passés. Une boucle les joue tous, à partir du son suivant. Avant, l’horloge remettait la suite en file sans fin, jusqu’à l’Agenda. Une ancre, une ligne du pupitre ou un son lancé seul faisaient de même avec leur cart : une pause pub sur une playlist ne finissait plus. Ils ne jouent plus qu’un son, et un tour en cours continue après eux. `POST /queues/flush` arrête le tour. Un tour ne s’arrête faute de carts à l’antenne ou en file qu’après y être passé : un tick parti avec l’état d’avant le lancement ne le coupe pas.

`POST /schedule/<id>/now` sur un cart sans suite à l’horloge, aléatoire ou d’une autre file que `carts`, ne met plus qu’un son en file. Il en mettait deux, tirés au hasard pour un cart aléatoire.

Un titre Beets sans `rg_track_gain` est analysé à la prévision (`analyze_item_soon`), puis au push si le gain manque encore (`ensure_item_gain`). Rien n’est poussé sans gain.

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

Un cart peut pointer un dossier de la banque (`bank_folder`, v12) et marquer ses sons comme pads d’identifiant (`ident_pads`, v16). Les jingles par défaut prennent le dossier `30-habillage/jingles`.

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

`beets/compat.py` corrige l’import de Beets 2.5 sous Python 3.14 : l’ioctl de taille de terminal demandait 4 octets, le noyau en écrit 8.

L’image du playout passe `apt-get upgrade` sur celle de Liquidsoap, que ses auteurs ne reconstruisent pas quand Debian publie un correctif. Liquidsoap garde la version de son tag.

## Marque et interface

`brand.json` et `brand.py` portent le nom affiché (`INTERFACE_NAME`), le logo et les libellés. Le nom de la station, les adresses de son flux et de son direct, et le lien de son code source se règlent aussi dans la console : des clés `station.*` de la table `settings` (`services/station.py`), sans migration. La console les pose sur son `brand.json`, qui reste le repli. Les pages HTMX gardent le nom de `brand.json`. `layout.jinja` est en `lang=fr`, avec `suite.css`. La feuille `sass/_suite.scss` est la charte noir et blanc du pupitre. Les pages HTMX d’origine (live, carts, auto-DJ, utilisateurs) restent servies par le même processus.

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

Exploitation : `alerts.py`, `metrics.py`, `retention.py`, `health.py`, et `interface/health.py`.

Métier : `domain/`, `services/` (carts, auto-DJ, émissions, banque, grille NTF, jeton d’encodeur), `models/clock.py`, `emission.py`, `execution.py`, `music_category.py`.

Interface : `account.py`, `csrf.py`, `emissions.py`, `integrity.py`, `json_util.py`, `spa.py`, `system.py`.

Agenda : `models/agenda.py`, `domain/agenda.py`, `services/agenda.py`, `scheduler/agenda.py`, `interface/agenda.py`, `interface/public.py`. Banque : `services/media_bank.py`.

Les tests nouveaux couvrent l’horloge, le conducteur, les alertes, le harbor, la rétention, la grille NTF, le CSRF, les JSON d’admin, le tick filtré, l’Agenda et la banque. `liquidsoap --check` sur `playout/radiotomate.liq` fait partie de la vérification.

## Ce qui n’a pas bougé

Le choix d’un son dans un cart (playlist, boucle, aléatoire, relais), à part une playlist simple passée en entier, les filtres Beets de l’auto-DJ, le harbor et les droits des comptes, à part le jeton d’encodeur, les sorties Icecast, PulseAudio et ALSA, et le rendu serveur HTMX. L’installateur Podman et les quadlets restent le chemin d’installation de l’amont, avec les sondes et le montage de banque en plus.
