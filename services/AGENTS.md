# Consignes pour les services

À lire avec le [AGENTS.md](../AGENTS.md) de la racine. Les trois services qui entourent le moteur sont décrits dans [README.md](README.md).

## Lancer et vérifier

```bash
cd services/catalog
pip install -r requirements.txt          # dans un venv, une fois
../../scripts/verifier.sh services       # les neuf tests, comme la CI
```

Pour essayer Icecast et nowplaying seuls : [deploy/local/](../deploy/local/README.md).

## Le catalogue

- `catalog/app.py` est un serveur de la bibliothèque standard (`http.server`), sans framework. Les routes sont des `if path == …` dans `CatalogHandler`. Il dépend seulement de `mutagen` et de `watchdog`, et parle à Meilisearch en HTTP.
- `inbox_api.py` range les envois du navigateur. `agenda_api.py` reçoit les sets des invités de l'Agenda. `volume_api.py` gère les mots de passe du dossier partagé.
- Le catalogue demande au moteur qui est connecté : `account_permissions` lit `/account.json` avec le cookie du navigateur. Il ne stocke aucun compte.
- Toutes les routes demandent une session, sauf `/health`, `/health/live` et `/tus-hook`, qu'appelle tusd. Le contrôle est en tête de `do_GET` : tous les rôles cherchent et pré-écoutent. Les routes `POST` demandent un admin (`session_admin`). nginx demande aussi la session devant `/library/`, mais le port du catalogue se joint sans lui : ne pas compter sur nginx seul.
- tusd 2.8 envoie ses hooks sur `POST /tus-hook`, sans en-tête `Hook-Name`. Le corps est `{"Type", "Event": {"Upload", "HTTPRequest"}}` : lire le type avec `hook_event` (`agenda_api.py`).
- Pour un dépôt d'invité, le catalogue appelle les routes internes du moteur (`/internal/agenda/…`) avec l'en-tête `X-Auth-Token`. Le jeton de l'invité ne voyage qu'en en-tête, jamais dans une adresse.
- L'image se construit depuis la racine du dépôt : elle embarque aussi `deploy/scripts/setup-media-tree.sh`.

## Tests

- Chaque test est un script `unittest` lancé seul : `python test_inbox_api.py`. Les faux services, comme un faux moteur, sont des `BaseHTTPRequestHandler` dans le test.
- La CI lance neuf fichiers, listés dans `.github/workflows/services.yml` sous la forme `- run: python test_xxx.py`. `scripts/verifier.sh` lit cette liste : un fichier de test nouveau s'y ajoute, sinon personne ne le lance.

## nowplaying et Icecast

- `nowplaying/nowplaying.py` reçoit les métadonnées du moteur (`POST /hook`, jeton `RT_NOWPLAYING_SECRET`) et publie `now.json`.
- `icecast/icecast.xml` se règle au démarrage par `docker-entrypoint.sh`, qui y recopie les mots de passe et l'e-mail tels quels. Son test, `catalog/test_icecast_config.py`, lance le script avec un faux `icecast2`. Une modification demande de reconstruire l'image.
- Le mount public d'une station ne se remplace jamais par un essai. On essaie sur un autre mount, ou sur le banc local.
