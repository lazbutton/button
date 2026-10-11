# Contribuer à BUTTON

*English: issues and pull requests in English are welcome. The user interface and the documentation are in French; please keep new interface text in French.*

Merci de votre intérêt ! Signalements, corrections, documentation, traductions : tout aide.

## Signaler un problème

Ouvrir une [issue](https://github.com/lazbutton/button/issues/new/choose) avec ce qui s'est passé, ce qui était attendu, et comment le reproduire. Indiquer la version : le tag de l'image (`AAAAMMJJ-sha7`) ou le commit.

Une faille de sécurité ne se signale pas en public : voir [SECURITY.md](SECURITY.md).

## Proposer un changement

1. Pour un changement important, ouvrir d'abord une issue pour en discuter.
2. Créer une branche depuis `main`.
3. Installer le banc local : [docs/developpement.md](docs/developpement.md).
4. Faire passer les vérifications de la partie touchée (tests, `ruff`, `npm test`, `npm run build`…).
5. Ouvrir une pull request qui dit ce qui change, pourquoi, et comment le vérifier.

## Règles du projet

- **L'API JSON entre le moteur et la console est un contrat.** Une route ne change de forme qu'avec la console, dans la même pull request, et [docs/api.md](docs/api.md) suit.
- **Le moteur est un fork mince de Radiotomate.** Les changements y restent minimaux et rétro-compatibles ; le script Liquidsoap s'amende, il ne se réécrit pas. Voir [engine/FORK.md](engine/FORK.md).
- **Le schéma de la base avance par migrations** (`vN.py`, avec `upgrade` et `downgrade`). On ne modifie jamais une migration déjà publiée.
- **L'interface est en français**, utilisable au clavier et sur téléphone, en thème clair et sombre.
- **Un commit par sujet.** Le message dit ce qui change, puis pourquoi.

## Licence des contributions

BUTTON est sous [AGPL-3.0-or-later](LICENSE). En proposant une contribution, vous acceptez qu'elle soit publiée sous cette même licence.
