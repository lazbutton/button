# P1 · Mettre en production

Ce qu'il faut pour qu'une station tourne sur un VPS exposé à Internet, s'installe en une commande et se mette à jour sans casser l'antenne. Tant qu'une fiche P1 reste ouverte, une installation sur un VPS est un essai, pas une production.

Le format des fiches, les tailles et la façon de prendre une fiche sont dans le [README](README.md) de la feuille de route. Avant de commencer une fiche, lire [travailler-a-plusieurs.md](../travailler-a-plusieurs.md).

## Le tableau

| Fiche | Titre | Taille | Dépend de | État |
|---|---|---|---|---|
| [SEC-01](#sec-01--protéger-le-catalogue) | Protéger le catalogue | S | — | à faire |
| [SEC-02](#sec-02--cookie-de-session-sécurisé-par-défaut) | Cookie de session sécurisé par défaut | S | — | à faire |
| [SEC-03](#sec-03--limiter-les-essais-de-connexion) | Limiter les essais de connexion | M | — | à faire |
| [SEC-04](#sec-04--identifiants-dencodeur-dédiés) | Identifiants d'encodeur dédiés | M | — | à faire |
| [SEC-05](#sec-05--en-têtes-de-sécurité) | En-têtes de sécurité | S | — | à faire |
| [SEC-06](#sec-06--refuser-les-secrets-dexemple) | Refuser les secrets d'exemple | S | — | à faire |
| [SEC-07](#sec-07--ports-fermés-sur-une-machine-exposée) | Ports fermés sur une machine exposée | S | — | à faire |
| [GEN-01](#gen-01--réglages-de-la-station-dans-la-console) | Réglages de la station dans la console | L | — | à faire |
| [GEN-02](#gen-02--sortir-les-données-dune-station-du-code) | Sortir les données d'une station du code | M | GEN-01 | à faire |
| [GEN-03](#gen-03--garde-fou-contre-les-données-de-station) | Garde-fou contre les données de station | S | — | à faire |
| [TST-01](#tst-01--banc-reproductible-et-playwright) | Banc reproductible et Playwright | M | — | à faire |
| [TST-02](#tst-02--parcours-critiques) | Parcours critiques | M | TST-01 | à faire |
| [TST-03](#tst-03--parcours-en-ci-et-accessibilité) | Parcours en CI et accessibilité | S | TST-02 | à faire |
| [MAJ-01](#maj-01--versions-et-canal-stable) | Versions et canal stable | M | — | à faire |
| [MAJ-02](#maj-02--copie-de-la-base-avant-chaque-migration) | Copie de la base avant chaque migration | S | — | à faire |
| [MAJ-03](#maj-03--contrôle-après-déploiement) | Contrôle après déploiement | S | SEC-01 | à faire |
| [MAJ-04](#maj-04--commande-de-mise-à-jour) | Commande de mise à jour | L | MAJ-01, MAJ-02, MAJ-03, INS-03 | à faire |
| [MAJ-05](#maj-05--retour-arrière-automatique) | Retour arrière automatique | M | MAJ-04 | à faire |
| [INS-01](#ins-01--https-par-un-reverse-proxy) | HTTPS par un reverse proxy | M | SEC-01, SEC-02, SEC-05, SEC-07 | à faire |
| [INS-02](#ins-02--installer-en-une-commande) | Installer en une commande | L | INS-01, GEN-01, MAJ-01, SEC-06 | à faire |
| [INS-03](#ins-03--commandes-dexploitation) | Commandes d'exploitation | M | INS-02 | à faire |
| [INS-04](#ins-04--mesurer-une-station-sur-un-petit-vps) | Mesurer une station sur un petit VPS | S | INS-02 | à faire |
| [SAV-01](#sav-01--sauvegardes-hors-de-la-machine) | Sauvegardes hors de la machine | M | INS-03 | à faire |
| [SUR-01](#sur-01--alertes-sur-le-téléphone-et-par-e-mail) | Alertes sur le téléphone et par e-mail | M | — | à faire |
| [DOC-01](#doc-01--guide-dinstallation-sur-vps) | Guide d'installation sur VPS | M | INS-04, MAJ-05, SAV-01 | à faire |
| [LEG-01](#leg-01--dépendances-images-et-licences) | Dépendances, images et licences | S | — | à faire |
| [LEG-02](#leg-02--le-code-source-pour-chaque-utilisateur) | Le code source pour chaque utilisateur | S | MAJ-01 | à faire |

En tout : 27 fiches, 12 de taille S, 12 de taille M et 3 de taille L.

## L'ordre

Les fiches d'une même vague peuvent avancer en même temps, une par agent, à condition que leurs **conflits** ne se recoupent pas. Dans une file, les fiches passent l'une après l'autre, parce qu'elles touchent les mêmes fichiers.

**Vague 1, sans dépendance :**

| File | Fiches, dans l'ordre | Fichier partagé |
|---|---|---|
| nginx | SEC-01, SEC-05, SEC-03 | `console/docker/nginx.conf.template` |
| démarrage | SEC-02, SEC-06, SEC-07 | `deploy/scripts/init-radiotomate.sh`, `deploy/compose.yml` |
| migrations | MAJ-02 | `engine/radiotomate/commands/update/__init__.py` |
| banc | TST-01 | `console/package.json`, `engine/radiotomate/commands/` |
| garde-fou | GEN-03 | `scripts/verifier.sh` |
| CI | LEG-01 | `.github/` |
| alertes | SUR-01 | `engine/radiotomate/scheduler/alerts.py` |

**Vague 2, dès qu'une file se libère :** SEC-04, GEN-01, TST-02, MAJ-01, MAJ-03, LEG-02. SEC-04 et GEN-01 n'attendent rien, mais elles touchent les mêmes fichiers : `console/src/api/types.ts` et `docs/api.md`. Fusionner l'une, puis rebaser l'autre. SEC-04 prend la migration v18.

**Vague 3 :** GEN-02, TST-03, INS-01.

**Vague 4 et suivantes, une à la fois :** INS-02, puis INS-03 et INS-04, puis MAJ-04 et SAV-01, puis MAJ-05, puis DOC-01. Elles écrivent toutes le même script d'exploitation.

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
- **À trancher avant de coder** : un blocage par identifiant seul permet à un inconnu de bloquer le compte d'un animateur juste avant son direct. Proposition : bloquer par adresse IP et par couple adresse et identifiant ; pour l'identifiant seul, un seuil plus haut, par exemple 20 échecs, et un blocage court.
- **À faire** :
  1. Un module pur, `domain/login_guard.py`. Les échecs comptent sur 15 minutes. Au cinquième, blocage de 15 minutes, doublé à chaque récidive, 24 heures au plus. En mémoire : un redémarrage remet à zéro.
  2. `/login.json` répond `429 {"error": "too_many_attempts", "retry_in": N}`, en secondes. `/login` affiche un message.
  3. nginx : `limit_req` sur des blocs exacts `= /login` et `= /login.json`, 5 par minute, rafale de 5. nginx pose l'adresse réelle du client, derrière un reverse proxy de confiance réglable (module `real_ip`), et la transmet au moteur. Le moteur ne croit cet en-tête que venant de nginx.
  4. Console : « Trop d'essais. Réessaie dans N minutes. » dans `SessionGate.tsx`.
- **Tests** : `engine/tests/scheduler/test_login_guard.py` pour le domaine, avec une horloge simulée ; le 429 dans un test des routes JSON ; le message dans un test de la console.
- **Accepté quand** : six mauvais mots de passe de suite donnent un 429 avec `retry_in`. Le bon mot de passe passe après le délai. Une autre adresse n'est pas bloquée.

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

M · dépend de GEN-01 · conflits : les deux `brand.json`, `console/src/lib/`, `deploy/scripts/init-radiotomate.sh`, `deploy/compose.yml`

- **Pourquoi** : le code contient encore les adresses et les noms de la station d'origine. Une autre station les verrait en repli, et ils n'ont rien à faire dans un logiciel publié.
- **Aujourd'hui** :
  - `console/public/brand.json` et `engine/radiotomate/brand.json` donnent des adresses, un hôte et un compte du réseau de la station ;
  - des adresses en repli dans `console/src/lib/nowPlaying.ts`, `useMonitor.ts` et `monitorSource.ts`, des noms du réseau local dans `monitorPcm.ts`, une adresse dans `components/antenne/DirectDialog.tsx` ;
  - les mounts `hold.mp3`, `button.mp3` et `studio.wav`, écrits dans `init-radiotomate.sh`, dans la démo de `engine/radiotomate/scheduler_api.py` et dans la console (`monitorPcm.ts`, `monitorSource.ts`, `lib/MonitorContext.tsx`) ;
  - les exemples `grouping:ntf1` dans `pages/CategoriesPage.tsx`, `mock/catalog.ts` et les gabarits `templates/autodj/` ;
  - la commande `radiotomate ntf-grille` (`commands/ntf.py`, `services/ntf_grille.py`) et son test.
- **À faire** :
  1. Des `brand.json` neutres, pour une station d'exemple en `radio.example`. La marque d'une station se monte comme une configuration : [ADR 0007](../decisions/0007-la-marque-est-une-configuration.md).
  2. Plus aucune adresse en repli dans le code : sans réglage, la fonction se cache et dit quoi régler.
  3. Les noms des mounts en variables. Les valeurs par défaut sont neutres.
  4. Des exemples neutres, comme `grouping:matinale`. `ntf-grille` devient une grille d'exemple neutre, ou disparaît.
- **Mise en service** : une station existante pose ses noms de mount dans `.env` avant de passer à cette version, sinon l'adresse de son flux change.
- **Tests** : GEN-03 passe. Les tests qui citent des noms de la station passent à des noms neutres.
- **Accepté quand** : une installation neuve ne montre ni nom ni adresse de la station d'origine, et GEN-03 est vert.

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
- **À faire** :
  1. **Fenêtre** : `update` refuse si un direct, un créneau nommé ou une diffusion datée commence dans les 30 minutes, sauf `--force`. Le moteur répond par une commande nouvelle, `radiotomate maintenance window`, lancée par `docker compose exec`.
  2. **Sauvegarde** : `backup` d'INS-03, en gardant les cinq dernières.
  3. **Fichiers de la version** : chaque version publiée joint son `compose.yml`, son modèle de configuration du reverse proxy, le script d'exploitation et un `SHA256SUMS`. `update` les télécharge et vérifie les sommes. `.env` et `compose.override.yml` sont gardés ; une variable nouvelle s'ajoute avec sa valeur par défaut.
  4. `docker compose pull`, puis `up -d`. Les trois services du moteur sont recréés ensemble.
  5. Le contrôle de MAJ-03.
  6. Un journal, `updates.log`, dans le dossier de la station.
  7. `GET /system/version.json`, pour les admins : la version de chaque service.
- **Tests** : ShellCheck et `bats` pour le script ; sur une machine jetable, une mise à jour de `0.1.0` vers `0.1.1`.
- **Accepté quand** : sur une machine jetable, une mise à jour normale coupe l'antenne moins de 30 secondes, et `status` affiche la version installée et la dernière disponible.

#### MAJ-05 · Retour arrière automatique

M · dépend de MAJ-04 · conflits : le script d'exploitation

- **Pourquoi** : une mise à jour ne doit jamais laisser l'antenne en panne, même la nuit sans personne.
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

- **À faire** : mesurer la mémoire et le processeur au repos, puis avec 50 auditeurs simulés ; la taille des images ; le disque utilisé ; la bande passante par auditeur, environ 58 Mo par heure d'écoute à 128 kbit/s.
- **Résultat** : la taille minimale conseillée, écrite dans DOC-01. Si une station ne tient pas dans 4 Go de mémoire, la fiche P3 « moins de services » remonte.
- **Accepté quand** : les mesures et la taille conseillée sont dans la doc, avec la date et la version mesurée.

### SAV · Sauvegarder

#### SAV-01 · Sauvegardes hors de la machine

M · dépend de INS-03 · conflits : le script d'exploitation

- **Pourquoi** : une sauvegarde sur la machine disparaît avec elle.
- **À faire** :
  1. `backup --remote` avec restic, vers un stockage S3 ou SFTP réglé par `config`. Chaque nuit par un minuteur systemd, chiffré avant l'envoi, avec une rotation : 7 quotidiennes, 4 hebdomadaires, 6 mensuelles.
  2. La doc dit la règle : un autre fournisseur que celui du VPS, pour qu'une panne ou une erreur de compte ne touche pas les deux.
  3. Chaque mois, un test de restauration automatique : restaurer dans un dossier temporaire et vérifier la base.
  4. `restore --remote`.
- **Accepté quand** : après la destruction d'une machine jetable, une installation neuve suivie de `restore --remote` redonne la station.

### SUR · Surveiller

#### SUR-01 · Alertes sur le téléphone et par e-mail

M · dépend de rien · conflits : `engine/radiotomate/scheduler/alerts.py`, `deploy/scripts/init-radiotomate.sh`

- **Pourquoi** : sur un VPS, personne ne regarde l'antenne. Un silence ou un disque plein doit arriver sur un téléphone.
- **Aujourd'hui** : `scheduler/alerts.py` envoie les alertes vers un webhook JSON ou une tâche Vikunja, réglés dans le bloc `alerts:` du YAML.
- **À faire** :
  1. L'e-mail par SMTP, et ntfy, une notification gratuite sur le téléphone, réglés à l'installation.
  2. Ils servent aux incidents d'antenne, aux mises à jour (faite, annulée, majeure en attente) et au disque presque plein, que `/system/disk.json` sait déjà mesurer.
  3. `docs/exploitation/` dit comment s'abonner.
- **Tests** : un faux serveur SMTP et un faux ntfy.
- **Accepté quand** : sur le banc, un silence envoie une alerte ntfy et un e-mail, puis une note quand le son revient.

### DOC · Documenter

#### DOC-01 · Guide d'installation sur VPS

M · dépend de INS-04, MAJ-05, SAV-01 · conflits : `docs/`

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
- **Aujourd'hui** : le lien « Code source » du menu du compte (`components/topbar/AccountMenu.tsx`) mène à `DEFAULT_SOURCE_URL` (`console/src/lib/brand.ts`), ou à `suite.sourceUrl` de `brand.json`.
- **À faire** :
  1. Chaque version publiée joint une archive de son code source.
  2. Le lien mène au code de la version en service, joignable par toute personne qui a un compte, même si le dépôt n'est pas public.
  3. Le réglage `source_url` de GEN-01 le change par station, pour une version modifiée.
- **Accepté quand** : depuis un compte d'animateur, le lien « Code source » ouvre ou télécharge le code de la version en service.
