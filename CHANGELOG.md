# Journal des changements

Les versions publiées sont listées ici, de la plus récente à la plus ancienne. Les images Docker portent aussi un tag daté (`AAAAMMJJ-sha7`) à chaque publication depuis `main`.

## Non publié

Première version publique en préparation.

- Moteur, console, services et déploiement réunis dans un seul dépôt.
- Moteur : fork de Radiotomate avec horloges, conducteur et réconciliation de l'antenne, API JSON pour la console, alertes, métriques et rétention. Schéma de base en v17.
- Console : antenne, conducteur, programmation, sons et réglages, avec des rôles (Animateur, Programmateur, Admin).
- Dépôt de musique par le navigateur, envoi reprenable.
- Déploiement par Docker Compose, images publiées par la CI.
- Agenda : émissions à une date précise, sets déposés par des invités grâce à un lien privé, directs datés.
- Dossier partagé de la banque, à ouvrir depuis le Finder (profil Compose `share`).
- Pour contribuer : `scripts/verifier.sh` lance les vérifications de la CI en une commande. Les consignes des agents de code (`AGENTS.md`), les décisions d'architecture, un glossaire et la feuille de route, avec les priorités de mise en production, sont dans `docs/`.
- Corrigé : en prod, nginx ne relayait pas `/media/bank.json`. Rattacher un dossier de la banque à un cart ne marchait qu'en dev. Un test de la console vérifie maintenant que chaque route qu'elle appelle passe nginx.
- Corrigé : modifier seulement un fichier Markdown du moteur, de la console ou des services, un `AGENTS.md` par exemple, reconstruisait les images. Une station qui suit `main` les redéployait, avec une coupure d'antenne quand le moteur ou Icecast redémarrait. La CI ignore maintenant ces fichiers.
- Corrigé : la recherche dans la banque et la lecture de ses fichiers répondaient à n'importe qui. Sur une machine exposée, toute la médiathèque se téléchargeait sans compte. nginx et le catalogue demandent maintenant une session, sauf pour les sondes et le hook de tusd.
- Le cookie de session porte maintenant l'attribut `Secure` : derrière HTTPS, il ne part plus en clair vers une adresse en `http://`. Une station servie en HTTP seul pose `RT_COOKIE_SECURE=false` dans `deploy/.env` avant de passer à cette version, sinon plus personne ne s'y connecte : voir [docs/deploiement.md](docs/deploiement.md#le-cookie-de-session).
- Corrigé : une pré-écoute coupée en cours de lecture, par une session expirée ou une coupure réseau, s'arrêtait sans message, et le casque d'antenne restait muet. La console rend maintenant le casque et dit pourquoi la pré-écoute s'est arrêtée.

Le détail des changements du moteur par rapport à l'amont : [docs/moteur/changements-radiotomate.md](docs/moteur/changements-radiotomate.md). L'historique de Radiotomate lui-même : [engine/CHANGELOG.md](engine/CHANGELOG.md).
