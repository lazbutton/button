# Automate — phase 0

Projet de travail de la plateforme (une radio, puis plusieurs), à part du dépôt de l’association.

Le plan est dans [`docs/plan-phase-0.md`](docs/plan-phase-0.md). La phase 0 va du 28 septembre au 20 décembre 2026. La première radio bêta est prévue le 7 décembre.

## Où est le code, pour l’instant

L’accord écrit avec l’association n’est pas signé. Tant qu’il ne l’est pas, on ne copie pas `radiotomate/` hors de `RC_WEB_RADIO` (lot L0 du plan). Ce dossier est le poste de travail : le plan, et le lancement des trois dépôts déjà sur la machine.

| Rôle | Dossier |
|---|---|
| Moteur et Liquidsoap | `../RC_WEB_RADIO/radiotomate` |
| Console | `../ntr-console` |
| Exploitation Nasgul | `../ntr-ops` |

Ouvre [`automate.code-workspace`](automate.code-workspace) dans Cursor : les quatre dossiers sont dans la même fenêtre.

BUTTON en prod tourne sur Nasgul. Le public passe par un VPS-1 2027 OVHcloud (`radio.lazbutton.xyz`) : 4 Go de RAM et 40 Go de disque, assez pour Icecast et HTTPS, pas pour héberger les stations. Le script ci-dessous ne parle qu’au Mac.

## Lancer le banc

Prérequis : Poetry dans le dépôt Radiotomate (`poetry install` déjà fait), Node dans `ntr-console` (`npm install` déjà fait).

```bash
./scripts/dev.sh
```

- Interface démo : http://127.0.0.1:6811
- Console : http://127.0.0.1:5175 (elle parle à l’interface)

`Ctrl-C` arrête les deux. Les dossiers se changent avec `RADIOTOMATE_DIR` et `CONSOLE_DIR` si les clones ne sont pas à côté de ce projet.

Le compte local de démo se crée une fois, dans `radiotomate/` :

```bash
export PATH="/opt/homebrew/bin:$PATH"
poetry run radiotomate -c radio_data/radiotomate.yaml users add lazbutton --admin
```
