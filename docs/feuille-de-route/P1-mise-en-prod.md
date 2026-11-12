# P1 · Mettre en production

Ce qu'il faut pour qu'une station tourne sur un VPS exposé à Internet, s'installe en une commande et se mette à jour sans casser l'antenne. Tant qu'une fiche P1 reste ouverte, une installation sur un VPS est un essai, pas une production.

Le format des fiches, les tailles et la façon de prendre une fiche sont dans le [README](README.md) de la feuille de route. Avant de commencer une fiche, lire [travailler-a-plusieurs.md](../travailler-a-plusieurs.md).

## Le tableau

| Fiche | Titre | Taille | Dépend de | État |
|---|---|---|---|---|
| [SEC-01](#sec-01--protéger-le-catalogue) | Protéger le catalogue | S | — | fait, `ed13ff2` |
| [SEC-02](#sec-02--cookie-de-session-sécurisé-par-défaut) | Cookie de session sécurisé par défaut | S | — | fait, `22ed07a` |
| [SEC-03](#sec-03--limiter-les-essais-de-connexion) | Limiter les essais de connexion | M | — | fait, `869ecd5` |
| [SEC-04](#sec-04--identifiants-dencodeur-dédiés) | Identifiants d'encodeur dédiés | M | — | fait, `ac86ab3` |
| [SEC-05](#sec-05--en-têtes-de-sécurité) | En-têtes de sécurité | S | — | fait, `5dbc61f` |
| [SEC-06](#sec-06--refuser-les-secrets-dexemple) | Refuser les secrets d'exemple | S | — | fait, `f1d6740` |
| [SEC-07](#sec-07--ports-fermés-sur-une-machine-exposée) | Ports fermés sur une machine exposée | S | — | fait, `a74aaed` |
| [GEN-01](#gen-01--réglages-de-la-station-dans-la-console) | Réglages de la station dans la console | L | — | fait, `98252bb` et `c2b39eb` |
| [GEN-02](#gen-02--sortir-les-données-dune-station-du-code) | Sortir les données d'une station du code | M | GEN-01 | fait, `922889f` |
| [GEN-03](#gen-03--garde-fou-contre-les-données-de-station) | Garde-fou contre les données de station | S | — | fait, `62a6f8a` |
| [TST-01](#tst-01--banc-reproductible-et-playwright) | Banc reproductible et Playwright | M | — | fait, `99b2cdf` |
| [TST-02](#tst-02--parcours-critiques) | Parcours critiques | M | TST-01 | fait, `7d8aa69` |
| [TST-03](#tst-03--parcours-en-ci-et-accessibilité) | Parcours en CI et accessibilité | S | TST-02 | fait, `2333eba` |
| [MAJ-01](#maj-01--versions-et-canal-stable) | Versions et canal stable | M | — | fait, `38e12a5` |
| [MAJ-02](#maj-02--copie-de-la-base-avant-chaque-migration) | Copie de la base avant chaque migration | S | — | fait, `26f0fcc` |
| [MAJ-03](#maj-03--contrôle-après-déploiement) | Contrôle après déploiement | S | SEC-01 | fait, `bd65070` |
| [MAJ-04](#maj-04--commande-de-mise-à-jour) | Commande de mise à jour | L | MAJ-01, MAJ-02, MAJ-03, INS-03 | fait, `5df65e5` |
| [MAJ-05](#maj-05--retour-arrière-automatique) | Retour arrière automatique | M | MAJ-04 | à faire |
| [INS-01](#ins-01--https-par-un-reverse-proxy) | HTTPS par un reverse proxy | M | SEC-01, SEC-02, SEC-05, SEC-07 | fait, `eaeb106` |
| [INS-02](#ins-02--installer-en-une-commande) | Installer en une commande | L | INS-01, GEN-01, MAJ-01, SEC-06 | fait, `f37f425` |
| [INS-03](#ins-03--commandes-dexploitation) | Commandes d'exploitation | M | INS-02 | fait, `a5b2eb7` |
| [INS-04](#ins-04--mesurer-une-station-sur-un-petit-vps) | Mesurer une station sur un petit VPS | S | INS-02 | à faire |
| [SAV-01](#sav-01--sauvegardes-hors-de-la-machine) | Sauvegardes hors de la machine | M | INS-03 | à faire |
| [SUR-01](#sur-01--alertes-sur-le-téléphone-et-par-e-mail) | Alertes sur le téléphone et par e-mail | M | — | à faire |
| [DOC-01](#doc-01--guide-dinstallation-sur-vps) | Guide d'installation sur VPS | M | INS-04, MAJ-05, SAV-01 | à faire |
| [LEG-01](#leg-01--dépendances-images-et-licences) | Dépendances, images et licences | S | — | fait, `512be6f` |
| [LEG-02](#leg-02--le-code-source-pour-chaque-utilisateur) | Le code source pour chaque utilisateur | S | MAJ-01 | fait, `ebc0ceb` |
| [FON-14](#fon-14--les-lignes-mises-à-la-suite-passent-à-lantenne) | Les lignes mises à la suite passent à l'antenne | M | — | fait, `d4a2dd9` |
| [FON-39](#fon-39--les-jingles-du-motif-passent-à-leur-tour) | Les jingles du motif passent à leur tour | M | FON-14 | fait, `7a497fd` |

En tout : 29 fiches, 12 de taille S, 14 de taille M et 3 de taille L. Au 12 novembre 2026, 24 sont faites. Il en reste 5 : 1 de taille S et 4 de taille M.

## L'ordre

Ce qui reste, relevé le 12 novembre 2026. Les fiches de deux files différentes peuvent avancer en même temps, une par agent. Dans une file, elles passent l'une après l'autre, parce qu'elles touchent les mêmes fichiers.

| File | Fiches, dans l'ordre | Fichier partagé |
|---|---|---|
| commande `station` | MAJ-05, SAV-01, SUR-01 | `deploy/station` |
| mesure | INS-04 | aucun |
| guide | DOC-01, en dernier | `docs/` |

- **MAJ-04 est fusionnée**, par la PR 141 : MAJ-05 passe en tête de sa file, puis SAV-01. Leurs « Accepté quand » demandent une machine jetable en x86-64 : la vraie installation de la CI (`.github/workflows/station.yml`) en est une, et son job `update` y fait maintenant une vraie mise à jour.
- **SUR-01** pose ses réglages à l'installation, qui est maintenant `station install` : elle est donc dans la file de la commande `station`. Elle peut y passer plus tôt : MAJ-05 se sert de ses alertes.
- **LEG-02 est fusionnée**, par la PR 146. Il reste à l'essayer sur une station d'essai : un animateur y télécharge le code de la version, et sans session la même adresse répond 401.
- **FON-14 et FON-39 sont fusionnées**, par les PR 139 et 142 : la file du scheduler n'a plus de fiche en P1. Leurs « Accepté quand » restent à vérifier sur une station de test, fondu allumé : leur banc tournait sans. Pour FON-39, c'est une heure d'antenne. FON-33 et FON-35 à FON-38, en P2, touchent les fichiers qu'elles viennent de changer : rejouer chaque défaut avant de le prendre.
- **INS-04 n'a aucun conflit.** Elle se mesure sur la version qui suit la 0.2.0 : celle-ci a encore le défaut d'une station vide, dont le conducteur s'empilait.
- **DOC-01 vient en dernier** : elle attend INS-04, MAJ-05 et SAV-01.

## Déjà fait

- La console relaie `/media/bank.json` en prod, et `console/src/api/nginxRoutes.test.ts` vérifie que chaque route appelée par la console est dans la liste de nginx.
- `scripts/verifier.sh` lance les vérifications de la CI en une commande.

## Les fiches

### SEC · Sécurité

#### SEC-01 · Protéger le catalogue

S · dépend de rien · conflits : `console/docker/nginx.conf.template`, `services/catalog/app.py`, `.github/workflows/services.yml`

- **Pourquoi** : la recherche et la lecture des fichiers de la banque répondent à n'importe qui. Sur une machine exposée, toute la médiathèque se télécharge sans compte.
- **Aujourd'hui** :
  - dans `nginx.conf.template`, le bloc `location /library/` n'a pas d'`auth_request`, alors que `/library/inbox.json` et `/tus/` en ont un ;
  - dans `services/catalog/app.py`, `/search` et `/media/…` ne demandent pas de session.
- **À faire** :
  1. `auth_request /_session;` sur le bloc `location /library/`.
  2. Dans le catalogue, une session valide pour toutes les routes, sauf `/health`, `/health/live` et `/tus-hook`, que tusd appelle sur le réseau interne. Reprendre la lecture de `/account.json` faite par `session_admin`, sans exiger le droit admin.
  3. Dans `console/src/api/nginxRoutes.test.ts`, un test qui vérifie que les blocs `/library/` et `/tus/` ont un `auth_request`.
- **Tests** : le test de nginx ; un test du catalogue, ajouté à `services.yml`, avec un faux moteur qui répond 401 puis 200.
- **Accepté quand** : sans cookie, `curl -i <console>/library/search?q=a` répond 401. Connecté, la recherche de la console et la pré-écoute marchent.

#### SEC-02 · Cookie de session sécurisé par défaut

S · dépend de rien · conflits : `deploy/scripts/init-radiotomate.sh`, `deploy/.env.example`, `deploy/compose.yml`

- **Pourquoi** : derrière HTTPS, un cookie de session sans l'attribut `Secure` part en clair dès qu'une adresse en `http://` est ouverte.
- **Aujourd'hui** : `engine/radiotomate/interface_app.py` lit `interface.cookie_secure`, faux par défaut. `init-radiotomate.sh` le force à faux à chaque démarrage. L'installateur de l'amont (`commands/install/installer.py`) le met à vrai hors développement.
- **À faire** :
  1. Une variable `RT_COOKIE_SECURE`, vraie par défaut, lue par `init-radiotomate.sh`.
  2. `false` documenté pour un accès en HTTP seul : banc local, réseau privé.
  3. Un avertissement dans le journal au démarrage quand elle est fausse, hors mode démo.
  4. `.env.example` et `docs/deploiement.md`.
- **Mise en service** : une station servie en HTTP pose `RT_COOKIE_SECURE=false` avant de passer à cette version, sinon plus personne ne se connecte. Le CHANGELOG le dit.
- **Tests** : dans `engine/tests/scheduler/`, avec `cookie_secure` vrai, l'en-tête `Set-Cookie` de la connexion porte `Secure`.
- **Accepté quand** : en HTTPS, le cookie de session porte `Secure`. Le banc en HTTP se connecte avec `RT_COOKIE_SECURE=false`.

#### SEC-03 · Limiter les essais de connexion

M · dépend de rien · conflits : `engine/radiotomate/interface/login.py`, `console/src/api/SessionGate.tsx`, `console/docker/nginx.conf.template`

- **Pourquoi** : rien ne freine qui essaie des mots de passe sur une console exposée.
- **Aujourd'hui** : `interface/login.py` sert `POST /login`, le formulaire des pages HTMX, et `POST /login.json`, pour la console, sans aucune limite.
- **Décidé** : on bloque l'adresse, jamais l'identifiant. Sinon, un inconnu bloquerait le compte d'un animateur juste avant son direct. Voir la décision [0013](../decisions/0013-bloquer-l-adresse-jamais-le-compte.md).
- **À faire** :
  1. Un module pur, `domain/login_guard.py`. Les échecs se comptent par adresse, sur 15 minutes. Au cinquième, l'adresse est bloquée 15 minutes, puis le double à chaque récidive, 24 heures au plus. En mémoire : un redémarrage remet à zéro.
  2. `/login.json` répond `429 {"error": "too_many_attempts", "retry_in": N}`, en secondes. `/login` affiche un message.
  3. nginx : `limit_req` sur des blocs exacts `= /login` et `= /login.json`, 5 par minute, rafale de 5. nginx pose l'adresse réelle du client, derrière un reverse proxy de confiance réglable (module `real_ip`), et la transmet au moteur. Le moteur ne croit cet en-tête que venant de nginx.
  4. Console : « Trop d'essais. Réessaie dans N minutes. » dans `SessionGate.tsx`.
- **Tests** : `engine/tests/scheduler/test_login_guard.py` pour le domaine, avec une horloge simulée ; le 429 dans un test des routes JSON ; le message dans un test de la console.
- **Accepté quand** : six mauvais mots de passe de suite depuis une adresse donnent un 429 avec `retry_in`, quel que soit l'identifiant tapé. Le bon mot de passe passe après le délai. Depuis une autre adresse, le même identifiant se connecte.

#### SEC-04 · Identifiants d'encodeur dédiés

M · dépend de rien · conflits : migration v18, `engine/radiotomate/models/user.py`, `scheduler/harbor.py`, `playout/radiotomate.liq`, `console/src/components/antenne/DirectDialog.tsx`, `console/src/api/types.ts`, `docs/api.md`

- **Pourquoi** : pour passer en direct, l'encodeur envoie le mot de passe du compte de l'animateur. Ce mot de passe dort dans la configuration de l'encodeur, et le harbor est ouvert à Internet.
- **Aujourd'hui** : le script Liquidsoap appelle `/can_stream` avec l'identifiant et le mot de passe reçus (`playout/radiotomate.liq`). `scheduler/harbor.py` les vérifie comme une connexion.
- **À faire** :
  1. Migration : `users.stream_token_hash` et `users.stream_token_created_at`.
  2. Un jeton d'encodeur par compte. L'animateur le crée ou le renouvelle depuis Mon compte, un admin pour un autre compte. Il s'affiche une seule fois, et il est stocké haché.
  3. `/can_stream` accepte l'identifiant et le jeton. Le mot de passe du compte reste accepté tant que le réglage `features.allow_account_password` est vrai : vrai sur une station existante, pour ne couper aucun encodeur ; faux sur une installation neuve.
  4. Console : le jeton dans le panneau du direct, avec « Renouveler ».
  5. `docs/api.md` et `docs/exploitation/passer-en-direct.md`.
- **Mise en service** : prévenir les animateurs avant de passer le réglage à faux. Chaque encodeur reçoit son jeton d'abord.
- **Tests** : la migration, montée et descente ; dans `engine/tests/scheduler/test_can_stream.py`, un jeton bon, mauvais, renouvelé, et le mot de passe refusé quand le réglage est faux.
- **Accepté quand** : un encodeur se branche avec son jeton. Avec le mot de passe du compte, il est refusé quand le réglage est faux. Renouveler le jeton coupe l'ancien.

#### SEC-05 · En-têtes de sécurité

S · dépend de rien · conflits : `console/docker/nginx.conf.template`

- **Pourquoi** : sans ces en-têtes, le navigateur laisse passer des attaques simples : une page de la console dans un cadre, un fichier lu comme un script, l'adresse qui fuit vers un autre site.
- **Aujourd'hui** : seul `/invitation` pose `Referrer-Policy` et `X-Robots-Tag`.
- **À faire** :
  1. `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, et `Permissions-Policy` sans micro ni caméra.
  2. Une `Content-Security-Policy`, rodée d'abord en `Report-Only`. Elle laisse passer le flux et `now.json` de la station, qui peuvent être sur un autre domaine : `media-src` et `connect-src` se lisent dans la configuration.
  3. `Strict-Transport-Security` vient du reverse proxy HTTPS (INS-01), pas de nginx.
- **Piège** : nginx n'hérite pas des `add_header` du bloc `server` dans un `location` qui en pose lui-même, comme `/assets/` et `/invitation`. Les poser dans un fichier inclus dans chaque bloc.
- **Tests** : `nginxRoutes.test.ts` vérifie leur présence dans chaque bloc.
- **Accepté quand** : `curl -I` sur `/`, sur un fichier de `/assets/` et sur `/invitation` montre les en-têtes. Les parcours de TST-02 passent avec la CSP appliquée.

#### SEC-06 · Refuser les secrets d'exemple

S · dépend de rien · conflits : `deploy/scripts/init-radiotomate.sh`, `deploy/compose.yml`

- **Pourquoi** : une station lancée avec `.env.example` copié tel quel a des mots de passe connus de tous.
- **Aujourd'hui** : cinq secrets valent `change-me` dans `deploy/.env.example` : `ICECAST_SOURCE_PASSWORD`, `ICECAST_ADMIN_PASSWORD`, `RT_NOWPLAYING_SECRET`, `MEILI_MASTER_KEY` et `RT_ADMIN_PASSWORD`. Rien ne refuse de démarrer avec.
- **À faire** :
  1. `radiotomate-init` reçoit les cinq. Il s'arrête si l'un est vide ou vaut `change-me`, ou si l'un des quatre secrets de machine fait moins de 24 caractères.
  2. Le message nomme chaque variable et donne la commande pour en générer une : `openssl rand -hex 24`.
  3. Le playout attend déjà la réussite de `radiotomate-init` (`depends_on`, `service_completed_successfully`) : l'antenne ne démarre donc pas.
  4. `deploy/local/` garde ses valeurs de test : ce banc ne passe pas par `radiotomate-init`.
- **Tests** : le contrôle lancé avec les valeurs d'exemple s'arrête et nomme les variables ; avec des valeurs fortes, il passe.
- **Accepté quand** : avec un `.env` copié sans changement, `docker compose up` ne met pas l'antenne en route, et le journal de `radiotomate-init` dit quoi changer.

#### SEC-07 · Ports fermés sur une machine exposée

S · dépend de rien · conflits : `deploy/compose.yml`, `deploy/.env.example`

- **Pourquoi** : Docker publie les ports sur toutes les interfaces et contourne le pare-feu ufw. Sur un VPS, la console, Icecast, nowplaying et le catalogue sont alors ouverts à Internet, en HTTP.
- **Aujourd'hui** : `deploy/compose.yml` publie `${CONSOLE_PORT:-30126}:80`, `${ICECAST_PORT:-18000}:8000`, `${NOWPLAYING_PORT:-6820}:6820` et `${CATALOG_PORT:-30127}:30127` sur toutes les interfaces. Seul le partage a une adresse d'écoute, `SMB_BIND`, à `127.0.0.1` par défaut. L'avertissement est dans `docs/deploiement.md`.
- **À faire** : une adresse d'écoute réglable pour chaque port publié, par exemple `BIND_ADDRESS`. Sa valeur par défaut garde le comportement actuel, pour ne casser aucune station. L'installation sur VPS (INS-02) pose `127.0.0.1`, et seul le reverse proxy (INS-01) joint alors ces ports.
- **Accepté quand** : avec `BIND_ADDRESS=127.0.0.1`, aucun de ces ports ne répond depuis une autre machine, et la station marche derrière le reverse proxy.

### GEN · Une station générique

#### GEN-01 · Réglages de la station dans la console

L, en deux commits : moteur, puis console · dépend de rien · conflits : `engine/radiotomate/interface_app.py`, `interface/public.py`, `console/src/lib/brand.ts`, `console/src/pages/ReglagesPage.tsx`, `console/src/api/types.ts`, `docs/api.md`, `nginx.conf.template`

- **Pourquoi** : le nom de la station, les adresses du flux et du direct, et le lien du code source sont écrits dans `brand.json`, au moment de construire l'image. Une autre station doit reconstruire la console pour les changer.
- **Aujourd'hui** : `console/src/lib/brand.ts` (`loadBrand()`) lit `console/public/brand.json`. Le moteur lit `engine/radiotomate/brand.json`, ou le fichier de la variable `BUTTON_BRAND` (`engine/radiotomate/brand.py`).
- **À faire** :
  1. Moteur : des clés `station.*` dans la table `settings` : `name`, `short`, `tagline`, `locale`, `public_stream_url`, `now_url`, `status_url`, `harbor_host`, `harbor_port`, `harbor_mount`, `source_url`. Le préfixe `station.` ne doit pas exister dans le YAML : voir [engine/AGENTS.md](../../engine/AGENTS.md#interrupteurs).
  2. Routes : `GET /public/station.json`, sans session, avec seulement ce qu'un auditeur peut voir ; `GET` et `PUT /station.json` pour les admins, avec le fuseau en lecture seule, qui est le `TZ` des conteneurs. `station\.json` entre dans la liste de nginx.
  3. Console : Réglages, onglet Station, réservé aux admins. `loadBrand()` prend les réglages du moteur, puis `brand.json` en repli.
  4. `docs/api.md`.
- **Tests** : `engine/tests/scheduler/test_station_json.py` ; la logique de repli dans un test de `console/src/api/`.
- **Accepté quand** : changer le nom ou l'adresse du flux dans la console change l'affichage sans reconstruire d'image. Face à un moteur sans ces routes, la console garde `brand.json`, et l'onglet affiche « Mets à jour le moteur ».

#### GEN-02 · Sortir les données d'une station du code

M · dépend de GEN-01 · conflits : les deux `brand.json`, `console/src/lib/`, `deploy/scripts/init-radiotomate.sh`, `deploy/compose.yml`, `deploy/station`, `deploy/tests/`, `.github/workflows/station.yml`, `scripts/verifier.sh`

- **Pourquoi** : le code contient encore les adresses et les noms de la station d'origine. Une autre station les verrait en repli, et ils n'ont rien à faire dans un logiciel publié. Or le dépôt est public, constaté le 11 novembre 2026 : ces données sont déjà lisibles par tous, et la fiche passe en tête de ce qui reste. Elles restent dans l'historique après la fiche : c'est PUB-01.
- **Aujourd'hui** :
  - `console/public/brand.json` et `engine/radiotomate/brand.json` donnent des adresses, un hôte et un compte du réseau de la station ;
  - des adresses en repli dans `console/src/lib/nowPlaying.ts`, `useMonitor.ts` et `monitorSource.ts`, des noms du réseau local dans `monitorPcm.ts`, l'adresse du direct dans `console/src/api/station.ts` (`harborAddress`), que montre « Passer en direct » ;
  - ce panneau, ouvert à tout compte, ne lit pas les réglages du harbor de GEN-01 : `GET /station.json` est réservé aux admins. Le faire suivre demande de choisir ce qu'un animateur peut lire ;
  - les mounts `hold.mp3`, `button.mp3` et `studio.wav`, écrits dans `init-radiotomate.sh`, dans la démo de `engine/radiotomate/scheduler_api.py` et dans la console (`monitorPcm.ts`, `monitorSource.ts`, `lib/MonitorContext.tsx`). Depuis INS-02, `deploy/station` écrit aussi le mount public (`MOUNT`), que citent ses tests bats (`deploy/tests/`) et la vraie installation de la CI (`.github/workflows/station.yml`) ;
  - les exemples `grouping:ntf1` dans `pages/CategoriesPage.tsx`, `mock/catalog.ts` et les gabarits `templates/autodj/` ;
  - la commande `radiotomate ntf-grille` (`commands/ntf.py`, `services/ntf_grille.py`) et son test ;
  - le garde-fou de GEN-03 laisse passer ces adresses par cinq exceptions, marquées « À retirer avec GEN-02 » (`exceptions_donnees`, `scripts/verifier.sh`) : deux pour chaque `brand.json`, une pour `console/src/lib/monitorPcm.ts`.
- **À faire** :
  1. Des `brand.json` neutres, pour une station d'exemple en `radio.example`. La marque d'une station se monte comme une configuration : [ADR 0007](../decisions/0007-la-marque-est-une-configuration.md).
  2. Plus aucune adresse en repli dans le code : sans réglage, la fonction se cache et dit quoi régler.
  3. Les noms des mounts en variables. Les valeurs par défaut sont neutres. `deploy/station` lit le mount public dans `.env`, et nulle part ailleurs.
  4. Des exemples neutres, comme `grouping:matinale`. `ntf-grille` devient une grille d'exemple neutre, ou disparaît.
  5. Les cinq exceptions du garde-fou sortent de `scripts/verifier.sh`. La phrase du [AGENTS.md](../../AGENTS.md) de la racine sur les deux `brand.json` aussi, comme celle de [console/AGENTS.md](../../console/AGENTS.md).
- **Mise en service** : une station existante pose ses noms de mount dans `.env` avant de passer à cette version, sinon l'adresse de son flux change.
- **Tests** : GEN-03 passe. Les tests qui citent des noms de la station passent à des noms neutres.
- **Accepté quand** : une installation neuve ne montre ni nom ni adresse de la station d'origine, et GEN-03 est vert sans ces cinq exceptions.

#### GEN-03 · Garde-fou contre les données de station

S · dépend de rien · conflits : `scripts/verifier.sh`, `.github/workflows/`, `.gitignore`

- **Pourquoi** : sans contrôle, une adresse ou un mot de passe revient au premier copier-coller.
- **À faire** :
  1. Une partie `donnees` dans `scripts/verifier.sh`, et un job de CI, qui cherchent dans les fichiers suivis : adresses IP privées, noms en `.ts.net`, clés privées, jetons (`ghp_`, `github_pat_`, `glpat-`).
  2. Des motifs propres à une station se mettent dans un fichier local, ignoré par git, jamais dans le dépôt : la liste des motifs d'une station est elle-même une donnée de station.
  3. Les exceptions sont écrites et commentées dans le script.
- **Accepté quand** : le contrôle échoue sur une adresse IP privée ajoutée dans un fichier, passe sur l'arbre après GEN-02, et tourne en CI.

### TST · Tests de bout en bout

#### TST-01 · Banc reproductible et Playwright

M · dépend de rien · conflits : `console/package.json`, `engine/radiotomate/commands/interface.py`, `commands/scheduler.py`, `scheduler_api.py`, `.gitignore`

- **Pourquoi** : les parcours de la console se vérifient aujourd'hui à la main. Un agent ne peut pas prouver qu'il n'a rien cassé à l'écran.
- **Aujourd'hui** : `npm test` couvre la logique pure de `console/src/api/`. Aucun test ne lance de navigateur sur la console. `engine/tests/interface/` teste en Playwright les pages HTMX de l'amont, hors CI. Les ports du moteur sont écrits en dur, ce qui interdit deux bancs sur une machine.
- **À faire** :
  1. `radiotomate interface --port` et `radiotomate scheduler --port`, avec les valeurs actuelles par défaut. La démo suit le port choisi.
  2. `@playwright/test` dans la console, `console/playwright.config.ts` et un dossier `console/e2e/`.
  3. Des données de démo semées par un script, `engine/tests/e2e/seed.py` : un compte de chaque rôle, des carts, des horloges. Le mot de passe de test est généré à chaque lancement, dans un fichier ignoré par git.
  4. De faux services pour le catalogue et tusd, dans `console/e2e/stubs/`.
  5. `scripts/e2e.sh` : moteur de démo, faux services, `vite preview`, puis Playwright, sur des ports libres.
- **Tests** : un premier parcours : se connecter, puis voir l'antenne.
- **Accepté quand** : `./scripts/e2e.sh` passe sur une machine neuve après `poetry install` et `npm install`, et deux lancements en même temps ne se gênent pas.

#### TST-02 · Parcours critiques

M · dépend de TST-01 · conflits : `console/e2e/`

- **Pourquoi** : l'antenne au quotidien passe par la barre du haut et le pupitre. Une régression là peut couper un direct.
- **À faire** : des parcours Playwright pour :
  - la barre du haut : état de l'antenne, écoute, menu du compte, lien « Code source » ;
  - le pupitre : Espace, Entrée et `/` ; la pré-écoute ; « Diffuser » ; déplacer une ligne au clavier et à la souris ; annuler ; le focus qui revient sur « Passer en direct » ;
  - les états simulés par `page.route` : session expirée, droit manquant, moteur injoignable, route absente ;
  - les trois rôles, le thème clair et le sombre, la largeur d'un téléphone.
- **Accepté quand** : les parcours passent, et chacun échoue quand on casse ce qu'il vérifie, essayé une fois à la main.

#### TST-03 · Parcours en CI et accessibilité

S · dépend de TST-02 · conflits : `.github/workflows/`, `scripts/verifier.sh`

- **À faire** :
  1. `.github/workflows/e2e.yml` sur chaque pull request qui touche `console/` ou `engine/`. En cas d'échec, les traces et les captures partent en artefacts.
  2. `@axe-core/playwright` fait échouer un parcours sur un défaut d'accessibilité grave ou critique.
  3. Une partie `e2e` dans `scripts/verifier.sh`.
- **Accepté quand** : une pull request qui casse un parcours est rouge, avec la trace en artefact.

### MAJ · Mettre à jour sans casser

#### MAJ-01 · Versions et canal stable

M · dépend de rien · conflits : `.github/workflows/`, `deploy/compose.yml`, `docs/deploiement.md`

- **Pourquoi** : les stations suivent `main`. Un commit vert mais mauvais part partout, et revenir en arrière demande de retrouver un tag daté.
- **Aujourd'hui** : la CI publie `main`, `AAAAMMJJ-sha7` et le SHA complet, depuis `main` seulement. `RT_TAG` épingle le moteur et le playout ; les cinq autres images suivent `:main`.
- **À faire** :
  1. Un tag `vX.Y.Z` déclenche les trois workflows, qui publient `X.Y.Z`, `X.Y` et `stable` pour les sept images.
  2. Dans `deploy/compose.yml`, une seule variable de version pour toutes les images, `stable` par défaut.
  3. Un workflow de version, avec des notes tirées de `CHANGELOG.md`.
  4. Le versionnage sémantique : un correctif est sans risque ; une version mineure peut migrer le schéma ; une version majeure demande une action, dite dans ses notes.
  5. `docs/deploiement.md`, parties « Mettre à jour » et « Revenir en arrière », et `docs/exploitation/le-flux-est-tombe.md`.
  6. La première version : `0.1.0`.
- **Mise en service** : une station qui suivait `main` passe à `stable`. Le dire dans les notes de la version.
- **Accepté quand** : pousser `v0.1.0` publie les sept images en `0.1.0`, `0.1` et `stable`, et une station sans variable de version tire `stable`.

#### MAJ-02 · Copie de la base avant chaque migration

S · dépend de rien · conflits : `engine/radiotomate/commands/update/__init__.py`

- **Pourquoi** : une migration ratée, ou une image plus ancienne qui ne sait pas lire le schéma récent, laisse l'antenne sans base utilisable.
- **Aujourd'hui** : `do_update()` applique les migrations à chaque démarrage, sans copie. La sauvegarde est à la main (`deploy/scripts/backup-radiotomate.sh`).
- **À faire** :
  1. Avant la première migration due, une copie par `sqlite3.Connection.backup()`, dans un dossier `backups/` à côté de la base : `avant-vNN-AAAAMMJJTHHMMSSZ.db`.
  2. Les cinq dernières copies sont gardées.
  3. Si la copie échoue, aucune migration, et le journal dit pourquoi.
  4. Rien quand aucune migration n'est due.
  5. `docs/exploitation/sauvegarde.md`.
- **Tests** : sur une base temporaire : la copie existe et se lit, la rotation garde cinq copies, et la migration est refusée si le dossier est en lecture seule.
- **Accepté quand** : passer une station à une version qui migre laisse une copie de la base d'avant, que `restore-radiotomate.sh` sait remettre.

#### MAJ-03 · Contrôle après déploiement

S · dépend de SEC-01 · conflits : aucun, fichier nouveau `deploy/scripts/smoke.sh`

- **Pourquoi** : après une installation ou une mise à jour, il faut savoir en une commande si l'antenne tourne, sans compte et sans regarder la console.
- **Aujourd'hui** : le playout, l'interface et le scheduler ont un healthcheck dans `deploy/compose.yml`. `/antenne/state.json` exige une session : un contrôle sans compte lit les `/health/ready`.
- **À faire** : `deploy/scripts/smoke.sh <adresse de la console> <adresse du flux public>`, lancé depuis le dossier de la station. Dans l'ordre :
  1. les trois services du moteur sont `healthy`, en attendant deux minutes au plus ;
  2. `<console>/` et `<console>/health/ready` répondent 200 ;
  3. le `/health/ready` du scheduler répond 200, joint par `docker compose exec` parce que le scheduler n'est pas publié ;
  4. `<console>/library/search?q=a` répond 401 sans cookie ;
  5. le flux public envoie de l'audio, quelques kilo-octets lus, et `now.json` répond.

  Au premier point qui échoue, le script s'arrête en erreur et le nomme.
- **Accepté quand** : le script passe sur une station saine. Sur le banc local, il échoue en nommant le service qu'on a arrêté.

#### MAJ-04 · Commande de mise à jour

L · dépend de MAJ-01, MAJ-02, MAJ-03, INS-03 · conflits : le script d'exploitation, `engine/radiotomate/commands/`, `interface/system.py`, `.github/workflows/`

- **Pourquoi** : mettre à jour doit tenir en une commande, au bon moment, avec une sauvegarde, et dire si tout va bien.
- **Aujourd'hui**, le 11 novembre 2026 :
  - `deploy/station` installe et exploite une station (INS-02, INS-03) : `install`, `status`, `logs`, `backup`, `restore`, `config`, `hold`, `unhold`, `cli` et `uninstall`. Il n'a pas encore `update`. Ses règles sont dans [deploy/AGENTS.md](../../deploy/AGENTS.md), partie « La commande station ».
  - `update` y trouve de quoi faire : le verrou des commandes qui changent la station (`lock_station`), la sauvegarde (`backup_station`), le contrôle (`smoke_ok`), le fichier `HOLD` (`hold_write`), la plus haute version publiée (`latest_version`), et les réglages `BUTTON_UPDATES` et `BUTTON_UPDATE_TIME` de `.env`, que `config` pose.
  - Depuis la 0.2.0, chaque version publiée joint `station`, `station.tar.gz` et `SHA256SUMS` (`.github/workflows/version.yml`, `scripts/version.py`), et `install` les télécharge puis compare les sommes : cette part du point 3 est faite.
  - Rien n'efface les archives de `backups/`. `docs/exploitation/sauvegarde.md` annonce qu'`update` gardera les cinq dernières.
  - Le groupe `radiotomate maintenance` existe, avec `next-live` (`engine/radiotomate/commands/maintenance.py`). `status` le lance par `docker compose exec`, et dit « inconnu » devant une image qui n'a pas la commande : `update` fait de même avec `window`.
  - Le calcul du prochain direct ne voit pas une émission annulée dans l'Agenda (FON-34, en P2) : la fenêtre refuserait une mise à jour pour un direct qui n'aura pas lieu.
  - Des messages de `deploy/station`, `docs/deploiement.md`, `deploy/.env.example` et `docs/exploitation/sauvegarde.md` disent `update` « à venir » : ils changent avec la fiche, comme les tests bats qui les citent (`deploy/tests/`).
- **Décidé**, le 11 novembre 2026 : `update` ne devine rien dans `.env` pour une variable dont le défaut change une station. C'est le cas d'`ICECAST_MOUNT`, venue avec GEN-02 : son défaut est `radio.mp3`, alors qu'une station installée avant diffuse sur `button.mp3`. Il s'arrête devant une version majeure, cite la « Mise en service » de ses notes, et ne passe qu'avec `--major`. Une majeure se reconnaît à son numéro : la version qui porte GEN-02 se publie donc en 1.0.0. La prochaine action demandée à une station ne sera pas un mount : un cas particulier par variable ne tiendrait pas.
- **À faire** :
  1. **Fenêtre** : `update` refuse si un direct, un créneau nommé ou une diffusion datée commence dans les 30 minutes, sauf `--force`. Le moteur répond par une commande nouvelle, `radiotomate maintenance window`, lancée par `docker compose exec`.
  2. **Sauvegarde** : `backup` d'INS-03, en gardant les cinq dernières.
  3. **Fichiers de la version** : chaque version publiée joint son `compose.yml`, son modèle de configuration du reverse proxy, le script d'exploitation et un `SHA256SUMS`. `update` les télécharge et vérifie les sommes. `.env` et `compose.override.yml` sont gardés ; une variable nouvelle s'ajoute avec sa valeur par défaut.
  4. `docker compose pull`, puis `up -d`. Les trois services du moteur sont recréés ensemble.
  5. Le contrôle de MAJ-03.
  6. Un journal, `updates.log`, dans le dossier de la station.
  7. `GET /system/version.json`, pour les admins : la version de chaque service.
- **Tests** : ShellCheck et `bats` pour le script ; sur une machine jetable, une mise à jour d'une version publiée vers la suivante. La vraie installation de la CI (`.github/workflows/station.yml`) peut la porter : une version publiée installée, puis `update` vers `main`.
- **Accepté quand** : sur une machine jetable, une mise à jour normale coupe l'antenne moins de 30 secondes, et `status` affiche la version installée et la dernière disponible.
- **Résultat**, le 11 novembre 2026, par la PR 141 :
  - `sudo station update` met une station à la plus haute version publiée, ou à `--version X.Y.Z`. La commande de la version visée fait la suite : une plus ancienne lui passe la main.
  - Elle s'arrête devant `HOLD`, une restauration pas finie, une version plus ancienne, une majeure sans `--major`, et un direct ou une diffusion de l'Agenda à l'antenne ou dans les 30 minutes, sauf `--force` (`radiotomate maintenance window`). Devant une image qui n'a pas cette commande, la fenêtre est « inconnue », et la mise à jour se fait en le disant.
  - La sauvegarde prend le script de la version visée : celui de la 0.2.0 demande `sqlite3`, que l'image du moteur n'a pas. `update` ne garde dans `backups/` que les cinq dernières archives (`backup_rotate`). `.env` ne reçoit que ce que la version demande de nouveau : une variable retirée exprès ne revient pas.
  - `updates.log` note chaque mise à jour, et `station status` dit la dernière. `GET /system/version.json` rend la version de chaque service, d'après `versions.json`, que `install`, `update` et `restore` relèvent : l'interface n'a pas accès à Docker.
  - Chaque version joint `CHANGELOG.md` à `station.tar.gz` : `update` y lit la « Mise en service » d'une majeure.
  - L'« Accepté quand » est porté par la CI. Le job `update` de `station.yml` installe la plus haute version publiée, la met à jour vers les fichiers de la branche et les images `main`, lit le flux chaque seconde, et échoue à 30 secondes de coupure. Il est passé sur la PR, par la fenêtre « inconnue » : les images `main` n'avaient pas encore la commande `window`.
  - Une station en 0.2.0 n'a pas `update` : elle prend d'abord la commande de la version publiée. `docs/deploiement.md` le dit, dans « Avec la commande station ».
  - Laissé à d'autres fiches : le retour arrière, qui se fait à la main avec la sauvegarde d'avant (MAJ-05) ; la mise à jour automatique la nuit (MAJ-06) ; la console, qui ne montre pas `/system/version.json` (MAJ-07) ; la fenêtre, qui tient pour vrai un direct annulé (FON-34). `next-live` lisait encore l'horloge du conteneur comme l'heure de Paris : corrigé depuis, par la PR 144.
  - Laissé sans fiche : une coupure de la connexion SSH en plein redémarrage arrête la mise à jour. La doc conseille `tmux` ou `screen`.

#### MAJ-05 · Retour arrière automatique

M · dépend de MAJ-04 · conflits : le script d'exploitation

- **Pourquoi** : une mise à jour ne doit jamais laisser l'antenne en panne, même la nuit sans personne.
- **Aujourd'hui** :
  - `restore` revient déjà seule à la station d'avant quand la station restaurée ne repart pas (`restore_undo`, `deploy/station`). `hold` pose `HOLD` avec sa date et sa raison (`hold_write`), et `status` l'affiche. Le retour arrière d'une mise à jour peut s'en inspirer.
  - Depuis MAJ-04, `update` existe (`update_station`). Il sauvegarde avant de toucher à la station, et note dans `updates.log` chaque mise à jour, faite, arrêtée ou échouée, avec la sauvegarde d'avant. Quand le redémarrage ou le contrôle échoue, il dit de revenir à la main, avec cette sauvegarde. Relancé après un échec au redémarrage, il dit de réparer par `install`.
  - Le job `update` de la CI (`.github/workflows/station.yml`) fait une vraie mise à jour sur une machine jetable : les trois cas des tests peuvent s'y ajouter.
- **À faire** : si le contrôle échoue après une mise à jour :
  1. retour aux images d'avant pour **tous** les services ;
  2. si le schéma a migré, restauration de la copie de la base d'avant, car l'ancienne version ne sait pas lire le schéma récent. Les minutes écoulées depuis la mise à jour sont perdues, et le journal le dit ;
  3. un fichier `HOLD`, qui bloque les mises à jour suivantes jusqu'à ce qu'une personne le retire ;
  4. une alerte « mise à jour annulée » (SUR-01).

  `rollback` fait la même chose à la main.
- **Tests** : sur une machine jetable, trois cas : une mise à jour normale, une image qui ne démarre pas, une migration qui échoue à mi-chemin.
- **Accepté quand** : les deux mises à jour cassées reviennent seules à l'état d'avant, base comprise, posent `HOLD` et alertent.

### INS · Installer

#### INS-01 · HTTPS par un reverse proxy

M · dépend de SEC-01, SEC-02, SEC-05, SEC-07 · conflits : `deploy/compose.yml`

- **Pourquoi** : sur Internet, la console et le flux passent en HTTPS, avec un certificat renouvelé sans personne.
- **D'abord, une sonde** : un flux Icecast relayé par Caddy passe-t-il sans mise en mémoire tampon (`flush_interval -1`) ? Les métadonnées ICY passent-elles ? Icecast voit-il l'adresse des auditeurs, pour les statistiques et le RGPD ? La réponse choisit entre Icecast derrière Caddy, sur le même domaine, ou Icecast sur son propre port avec son propre certificat. Elle s'écrit dans un ADR.
- **À faire** :
  1. Un service `caddy` derrière un profil Compose `vps`, et un `deploy/Caddyfile` modèle : un certificat Let's Encrypt automatique pour un domaine ; `/` vers la console ; le flux ; `/now.json` vers nowplaying ; l'option `tls internal` pour les essais et la CI.
  2. Caddy redirige `http://` vers `https://` et pose `Strict-Transport-Security`.
  3. Le harbor est publié sur son propre port. C'est le seul port ouvert avec 80 et 443, et il n'accepte que les identifiants d'encodeur (SEC-04).
- **Accepté quand** : depuis une autre machine, seuls 22, 80, 443 et le port du direct répondent. La console et le flux répondent en HTTPS avec un certificat valide.

#### INS-02 · Installer en une commande

L · dépend de INS-01, GEN-01, MAJ-01, SEC-06 · conflits : le script d'exploitation, fichier nouveau

- **Pourquoi** : installer une station doit tenir en une commande, sur un VPS neuf, sans connaître Docker.
- **Le modèle** : le script d'installation d'AzuraCast. Un seul script bash, `deploy/station` en nom provisoire, sert à installer, mettre à jour et exploiter.
- **À faire** : `install`
  1. **vérifie** : les droits root ; Debian 12 ou 13, ou Ubuntu 24.04 ; un processeur x86-64 ; Docker et Compose v2, ou propose de les installer depuis le dépôt officiel de Docker ; les ports 80 et 443 libres ; la place disque ; et que le domaine pointe sur cette machine **avant** de demander un certificat, sinon Let's Encrypt bloque le domaine après quelques échecs ;
  2. **demande**, avec des valeurs par défaut : le nom de la station, le domaine, l'e-mail, le fuseau, l'identifiant admin, et si les mises à jour sont automatiques ;
  3. **écrit** le dossier de la station : `compose.yml` et le modèle de Caddy de la version `stable` ; `.env` en droits 600, avec les secrets tirés par `openssl rand` ; `features.allow_account_password` à faux ; les dossiers de données ;
  4. **démarre** : `pull`, `up -d`, attente de la santé, puis MAJ-03 ;
  5. **affiche** l'adresse de la console et le mot de passe admin une seule fois, sans jamais l'écrire dans un journal ;
  6. pose la commande dans `/usr/local/bin`.

  Toutes les réponses existent en options (`--domain`, `--email`, `--timezone`…), pour la CI et les réinstallations. Relancer `install` répare sans rien écraser, `.env` compris. Tant que les images ne sont pas publiques, un jeton GHCR en lecture (`--github-token-file`) donne accès aux images.
- **Tests** : ShellCheck ; `bats` pour les questions, les fichiers écrits et la relance ; une installation complète sur une machine jetable.
- **Accepté quand** : sur une machine jetable neuve, une commande mène à une antenne qui joue en HTTPS en moins de 15 minutes, et relancer `install` ne change rien.

#### INS-03 · Commandes d'exploitation

M · dépend de INS-02 · conflits : le script d'exploitation

- **À faire**, dans le même script :
  - `status` : version installée et dernière disponible, santé des services, place disque, prochain direct, dernière sauvegarde, `HOLD` éventuel ;
  - `logs [service]` ;
  - `backup [archive]` : la base, `radiotomate.yaml`, `.env` et les données de Caddy ; les médias avec `--with-media` ;
  - `restore <archive>` ;
  - `config` : changer le domaine, l'e-mail, l'heure des mises à jour ;
  - `hold` et `unhold` : bloquer et débloquer les mises à jour ;
  - `cli` : les commandes du moteur ;
  - `uninstall` : garde les données, sauf `--purge`, après confirmation.
- **Accepté quand** : `backup` sur une machine jetable, puis `install` et `restore` sur une autre machine neuve, redonnent la même station : comptes, horloges, Agenda, réglages.

#### INS-04 · Mesurer une station sur un petit VPS

S · dépend de INS-02 · conflits : aucun

- **Aujourd'hui** : INS-02 est faite, la mesure peut se faire. Deux défauts d'une station vide, vus le 10 novembre 2026 sur un VPS de 2 vCPU en 0.2.0, fausseraient les chiffres : la banque de sons à root, et un conducteur qui s'empilait jusqu'à saturer le processeur. Ils sont corrigés sur `main`, pas dans la 0.2.0 : mesurer sur la version suivante. Ce qui reste du second est FON-32, en P2.
- **À faire** : mesurer la mémoire et le processeur au repos, puis avec 50 auditeurs simulés ; la taille des images ; le disque utilisé ; la bande passante par auditeur, environ 58 Mo par heure d'écoute à 128 kbit/s.
- **Résultat** : la taille minimale conseillée, écrite dans DOC-01. Si une station ne tient pas dans 4 Go de mémoire, la fiche P3 « moins de services » remonte.
- **Accepté quand** : les mesures et la taille conseillée sont dans la doc, avec la date et la version mesurée.

### SAV · Sauvegarder

#### SAV-01 · Sauvegardes hors de la machine

M · dépend de INS-03 · conflits : le script d'exploitation

- **Pourquoi** : une sauvegarde sur la machine disparaît avec elle.
- **Aujourd'hui** : `station backup` écrit son archive dans `backups/`, sur la machine. `backup_stage` (`deploy/station`) prépare le dossier de la sauvegarde, qu'un envoi hors de la machine peut reprendre tel quel, et `backup_pack` en fait l'archive. Depuis MAJ-04, `update` y écrit aussi la sienne, et n'y garde que les cinq dernières (`backup_rotate`).
- **À faire** :
  1. `backup --remote` avec restic, vers un stockage S3 ou SFTP réglé par `config`. Chaque nuit par un minuteur systemd, chiffré avant l'envoi, avec une rotation : 7 quotidiennes, 4 hebdomadaires, 6 mensuelles.
  2. La doc dit la règle : un autre fournisseur que celui du VPS, pour qu'une panne ou une erreur de compte ne touche pas les deux.
  3. Chaque mois, un test de restauration automatique : restaurer dans un dossier temporaire et vérifier la base.
  4. `restore --remote`.
- **Accepté quand** : après la destruction d'une machine jetable, une installation neuve suivie de `restore --remote` redonne la station.

### SUR · Surveiller

#### SUR-01 · Alertes sur le téléphone et par e-mail

M · dépend de rien · conflits : `engine/radiotomate/scheduler/alerts.py`, `deploy/scripts/init-radiotomate.sh`, `deploy/station`

- **Pourquoi** : sur un VPS, personne ne regarde l'antenne. Un silence ou un disque plein doit arriver sur un téléphone.
- **Aujourd'hui** : `scheduler/alerts.py` envoie les alertes vers un webhook JSON ou une tâche Vikunja, réglés dans le bloc `alerts:` du YAML. Depuis INS-02, l'installation est `station install` (`deploy/station`) : c'est là que se posent les réglages du point 1.
- **À faire** :
  1. L'e-mail par SMTP, et ntfy, une notification gratuite sur le téléphone, réglés à l'installation.
  2. Ils servent aux incidents d'antenne, aux mises à jour (faite, annulée, majeure en attente) et au disque presque plein, que `/system/disk.json` sait déjà mesurer.
  3. `docs/exploitation/` dit comment s'abonner.
- **Tests** : un faux serveur SMTP et un faux ntfy.
- **Accepté quand** : sur le banc, un silence envoie une alerte ntfy et un e-mail, puis une note quand le son revient.

### DOC · Documenter

#### DOC-01 · Guide d'installation sur VPS

M · dépend de INS-04, MAJ-05, SAV-01 · conflits : `docs/`

- **Aujourd'hui** : `docs/deploiement.md` porte déjà « Installer sur un VPS », avec « Exploiter la station », puis « Mettre à jour » et « Revenir en arrière ». `docs/exploitation/sauvegarde.md` porte la sauvegarde et la restauration. Les trois pages de la fiche se taillent dans ces parties, une fois `rollback` et `backup --remote` écrites : `update` l'est, depuis MAJ-04.
- **À faire** :
  1. `docs/installer.md` remplace la partie « Installer » de `docs/deploiement.md` : choisir un VPS, avec la taille mesurée par INS-04, un processeur x86-64 et le trafic compté ; le DNS ; l'installation ; le premier réglage dans la console ; brancher un encodeur ; la sécurité de la machine, c'est-à-dire SSH par clé, `unattended-upgrades` et le pare-feu du fournisseur.
  2. `docs/mettre-a-jour.md` et `docs/sauvegarder.md`.
  3. `docs/exploitation/le-flux-est-tombe.md` adapté au VPS.
- **Accepté quand** : une personne qui n'a pas écrit le code installe une station sur une machine jetable avec la doc seule.

### LEG · Licences

#### LEG-01 · Dépendances, images et licences

S · dépend de rien · conflits : `.github/`

- **Aujourd'hui** : Dependabot suit les actions GitHub, npm pour la console et pip pour le catalogue. Le moteur et les images Docker n'en ont pas.
- **À faire** :
  1. Dependabot, ou Renovate, pour Poetry et pour les images de base.
  2. Trivy sur les images publiées, en échec sur toute faille critique.
  3. Un contrôle des licences des dépendances npm et Python en CI, en échec sur une licence incompatible avec l'AGPL.
- **Accepté quand** : la CI échoue sur une faille critique d'une image, ou sur une dépendance de licence incompatible.

#### LEG-02 · Le code source pour chaque utilisateur

S · dépend de MAJ-01 · conflits : `console/src/lib/brand.ts`, `.github/workflows/`

- **Pourquoi** : l'AGPL oblige à proposer le code source de la version en service à chaque personne qui utilise la console à distance, animateurs compris.
- **Aujourd'hui** : le lien « Code source » du menu du compte (`components/topbar/AccountMenu.tsx`) mène à `DEFAULT_SOURCE_URL` (`console/src/lib/brand.ts`), ou à `suite.sourceUrl` de `brand.json`. Le dépôt est public, constaté le 11 novembre 2026, et GitHub joint à la page de chaque version l'archive de son code : le point 1 tient tant que le dépôt reste public. Le lien mène à la racine du dépôt, pas au code de la version en service.
- **À faire** :
  1. Chaque version publiée joint une archive de son code source.
  2. Le lien mène au code de la version en service, joignable par toute personne qui a un compte, même si le dépôt n'est pas public.
  3. Le réglage `source_url` de GEN-01 le change par station, pour une version modifiée.
- **Accepté quand** : depuis un compte d'animateur, le lien « Code source » ouvre ou télécharge le code de la version en service.
- **Résultat**, le 12 novembre 2026, par la PR 146 :
  - Tranché avec l'utilisateur : la station sert elle-même l'archive du code de sa version ([décision 0018](../decisions/0018-la-station-sert-son-code-source.md)). Un lien vers le tag, ou vers une archive de GitHub, ne tiendrait plus si le dépôt cessait d'être public.
  - Chaque version joint `button-X.Y.Z-source.tar.gz` (`scripts/version.py source`, `.github/workflows/version.yml`). L'image de la console l'embarque, et nginx la sert sous `/code-source/`, à une session seulement.
  - Le lien « Code source » du menu du compte télécharge cette archive, pour chaque compte, animateurs compris. Sans archive, il mène au dépôt, comme avant. Le réglage `source_url` de Réglages → Station passe devant, pour une version modifiée.
  - Vérifié après la fusion : sur `main`, le job qui construit l'image de la console avec son archive passe.
  - Pas vérifié : la page d'une version, qui ne joindra l'archive qu'au prochain tag ; et une vraie station. Sur une station d'essai en `main`, un animateur doit télécharger l'archive, et sans session la même adresse doit répondre 401.
  - Limites connues : une station qui suit `main` a l'archive du commit de son image de la console, qui ne se refait que quand `console/` change ; une version publiée a l'archive exacte de son tag.
  - Laissé à une autre fiche : un invité de l'Agenda n'a ni lien ni session. C'est LEG-03, en P2.

### FON · Fonctions

#### FON-14 · Les lignes mises à la suite passent à l'antenne

M · dépend de rien · conflits : `engine/radiotomate/scheduler/clock.py`, `engine/radiotomate/scheduler/execution.py`, `engine/radiotomate/scheduler/desk.py`

- **Pourquoi** : au pupitre, « Mettre à la suite » répond « Mis à la suite. » et montre la ligne dans la file, mais le scheduler ne la passe jamais.
- **Aujourd'hui** :
  - `insert_desk_item` (`engine/radiotomate/scheduler/desk.py`) crée une ligne `origin = "desk"`, datée de la fin du titre à l'antenne, sans rien envoyer au playout.
  - Le scheduler ne pousse que par `_load_pushable_sequential` et `_planned_anchor_item` (`engine/radiotomate/scheduler/clock.py`), qui excluent tous deux `origin = "desk"`. `realign_rundown` (`execution.py`) laisse aussi ces lignes à leur heure. L'exclusion date de l'import initial, sans raison écrite, et aucun test ne l'attend.
  - Seul « Jouer tout de suite » (`POST /autodj/conducteur/now.json`) fait passer une ligne du pupitre.
  - La ligne reste donc dans la file jusqu'à son heure de fin, puis en sort, et `expire_past_desk_items` l'efface : un échec silencieux. Le moteur de démo ne joue que sa propre liste, et les parcours de la console ne peuvent pas le voir.
  - Constaté en lisant le code, pas encore sur une station en service.
- **À trancher avant de coder** :
  - Quand la ligne passe-t-elle ? Proposition : à sa place dans la file, comme une ligne de l'horloge, dans la file du playout de son type (`desk_queue_for` : `autodj`, `carts` ou `jingles`).
  - La ligne de l'horloge qu'elle précède attend-elle ? Proposition : oui, et les suivantes glissent, comme le fait déjà `realign_rundown`.
  - Une ancre dure garde son heure. Proposition : une ligne du pupitre ne la retarde jamais, comme une ligne de l'horloge (`track_would_overflow_anchor`).
  - L'interrupteur de l'[ADR 0009](../decisions/0009-interrupteurs.md). Proposition : `features.desk_lines_air`, absent = la ligne passe.
- **À faire** :
  1. Sur une station de test, avec le scheduler et Liquidsoap réels, mettre une ligne à la suite et vérifier qu'elle ne passe pas. Si elle passe, noter par où, et fermer la fiche.
  2. Le scheduler pousse les lignes du pupitre à leur tour, selon les règles tranchées : chacune dans sa file, par son son si elle vient d'un cart, par son chemin si elle vient de la banque.
  3. Le conducteur suit la ligne comme une autre, envoyée puis à l'antenne puis jouée. `expire_past_desk_items` n'efface plus une ligne déjà envoyée, qui attend son tour.
  4. L'interrupteur, avec un test fonction coupée et un test fonction allumée.
- **Mise en service** : à la mise à jour, les lignes du pupitre encore à venir passeront. Pour revenir en arrière sans redéployer : couper l'interrupteur.
- **Tests** : dans `engine/tests/scheduler/`, une ligne mise à la suite est poussée une fois, à son tour, dans la bonne file ; une ligne retirée ne l'est pas ; une ancre n'est pas retardée ; l'interrupteur coupé garde le comportement d'avant.
- **Accepté quand** : sur une station de test, une ligne mise à la suite au pupitre passe à l'antenne après le titre en cours, sans autre geste, et le conducteur la marque jouée.
- **Résultat**, le 11 novembre 2026, par la PR 139 :
  - Le défaut a été constaté avant d'être corrigé : sur le banc de tests du moteur, puis avec le scheduler et Liquidsoap 2.4.5 réels, une ligne mise à la suite restait « prévu ».
  - Les quatre propositions sont retenues telles quelles. La ligne se place après les titres déjà envoyés au playout (`_sent_end`, `desk.py`), là où la console la montre. Une musique part dans la file `autodj`, à son tour. Un son ou une pub part dans `carts`, un jingle dans `jingles`, à la fin du titre qui les précède (`_desk_turn`, `clock.py`). Une ligne qui finirait après une coupure dure attend cette coupure (`_desk_would_overflow`). L'interrupteur est `features.desk_lines_air` : absent, les lignes passent.
  - Un écart avec la seconde proposition : pendant qu'un son ou un jingle du pupitre attend la fin du titre qui le précède, l'horloge met déjà la musique suivante dans la file `autodj`. Cette musique passe quand même après la ligne, car `carts` et `jingles` passent avant l'auto-DJ.
  - Limites connues, laissées : un son mis à la suite derrière un jingle à l'antenne lui coupe ses 3 dernières secondes ; pendant un tour de « Diffuser maintenant » sur une playlist, un son mis à la suite passe au milieu du tour ; attendre une coupure dure peut laisser un blanc avant elle.
  - L'« Accepté quand » reste à vérifier sur une station de test. Le banc tournait sans fondu : sur un Mac ARM, le fondu de Liquidsoap se fige après une ou deux transitions.
  - Vu en passant : les jingles du motif ne passent plus après le démarrage. C'est FON-39.

#### FON-39 · Les jingles du motif passent à leur tour

M · dépend de FON-14 · conflits : `engine/radiotomate/scheduler/clock.py`, `engine/radiotomate/scheduler/timing.py`, `engine/tests/scheduler/test_clock.py`

- **Pourquoi** : une horloge dont le motif alterne jingles et musiques ne passe plus de jingle après son démarrage. L'antenne enchaîne les titres sans habillage, et le conducteur garde ses jingles « prévu ».
- **Aujourd'hui** :
  - `_fill_sequential_from_rundown` (`engine/radiotomate/scheduler/clock.py`) prend les lignes prévues dans l'ordre. Devant un jingle qui ne peut pas partir, elle passe à la ligne suivante : la musique prévue après lui part avant lui.
  - Un jingle du motif ne part que si la file `autodj` est vide, à 3 s au plus de la fin du titre en cours (`can_push_sequential_jingle`, `engine/radiotomate/scheduler/timing.py`). Or l'horloge tient deux titres d'avance dans cette file (`TARGET_QUEUE_DEPTH`) : après le premier tick, elle n'est plus vide tant qu'il reste de la musique à envoyer.
  - Un jingle sauté reste « prévu », dans le passé, et `_load_pushable_sequential` n'a pas de borne de temps. Ces jingles partiraient donc en retard dès que la file `autodj` se vide, après « Vider les files » ou au retour d'un direct : lu dans le code, pas rejoué.
  - Les tests ne le voient pas : `engine/tests/scheduler/test_clock.py` n'attend un jingle du motif qu'au premier tick, files vides (`test_motif_jingle_then_three_music`, `test_night_uses_clock_not_random_pick`).
  - Relevé le 11 novembre 2026, en livrant FON-14. Sur le banc de tests du moteur, puis avec le scheduler et Liquidsoap 2.4.5 réels, sans fondu : six titres en cinq minutes, aucun jingle. Relu dans le code de `main` le même jour. La règle date de l'import initial : la 0.1.0 et la 0.2.0 l'ont. Pas vu sur une station.
- **À trancher avant de coder** :
  - Quand le jingle part-il ? Soit il retient la musique prévue après lui : la file `autodj` se vide à la fin du titre en cours, et il passe. L'auto-DJ n'a alors plus de titre d'avance, et un tick en retard laisserait un blanc. Soit il part à la fin du titre qui le précède, sans attendre une file vide, comme une ligne du pupitre depuis FON-14 (`_desk_turn`).
  - Que deviennent les jingles déjà sautés ? Proposition : un jingle dont l'heure est passée ne part plus, et le conducteur le dit « sauté ».
  - L'interrupteur de l'[ADR 0009](../decisions/0009-interrupteurs.md). Proposition : absent, les jingles passent, comme pour `features.desk_lines_air`.
- **À faire** :
  1. Un test qui montre le défaut : sur deux tours du motif, le second jingle ne part pas.
  2. Le correctif, selon ce qui est tranché, derrière l'interrupteur, avec un test fonction coupée et un test fonction allumée.
  3. `docs/moteur/changements-radiotomate.md` le dit.
- **Mise en service** : à la mise à jour, les jingles du motif passent de nouveau. Pour revenir en arrière sans redéployer : couper l'interrupteur.
- **Tests** : dans `engine/tests/scheduler/`, sur trois tours du motif, chaque jingle part une fois, à sa place ; un jingle dont l'heure est passée ne part pas en retard ; l'interrupteur coupé garde le comportement d'avant. Puis le banc de la PR 139, avec le scheduler et Liquidsoap réels.
- **Accepté quand** : sur une station de test, une horloge au motif « jingle, musique, musique, musique » passe un jingle tous les trois titres, pendant une heure.
- **Résultat**, le 12 novembre 2026, par la PR 142 :
  - Un test montre le défaut sur le conducteur de nuit du banc (`engine/tests/scheduler/test_motif_jingles.py`). Avant : après le premier jingle, plus aucun ne part, et le suivant part neuf minutes en retard après « Vider les files ». Après : chaque jingle à sa place, sur trois tours du motif.
  - Tranché par l'utilisateur. Le jingle ne retient pas la musique qui le suit : il part à la fin du titre qui le précède, par la règle des lignes du pupitre (`_line_turn`, l'ancien `_desk_turn`, `clock.py`). L'interrupteur est `features.motif_jingles_air` : absent, les jingles passent.
  - Un écart avec la fiche. Un jingle n'est pas sauté quand son heure est passée, mais quand la musique prévue après lui est passée à l'antenne : il est fermé, raison « tour passé », et ne part jamais en retard (`reconcile_as_run` et `close_passed_jingles`, `execution.py`). C'est l'ordre du motif qui compte : après un direct imprévu, l'horloge rejoue la suite en retard, et l'heure y fermerait des jingles encore à leur place.
  - À la mise à jour d'une station, les jingles restés « prévu » depuis son démarrage sont fermés au premier tick.
  - Sur le banc de FON-14, avec Liquidsoap 2.4.5 et sans fondu, les trois jingles du relevé passent, chacun à sa place, sans blanc.
  - L'« Accepté quand » reste à vérifier : une heure sur une station de test, avec le fondu.
  - Limites connues, laissées : le jingle coupe les deux dernières secondes du titre qui le précède, qui reprennent après lui, comme pour une ligne du pupitre, mais maintenant à chaque jingle ; derrière un son de bac à l'antenne, il attend la fin de ce son ; il ne vérifie pas qu'il finirait avant une coupure dure.
  - La PR corrige aussi deux parcours de `telephone.spec.ts`, qui visaient la première ligne de la file. Ce qui les faisait rougir reste : TST-08, en P2.
