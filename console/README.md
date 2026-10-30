# Console

L'application web de la station : antenne, conducteur, programmation, sons et
réglages. Vite, React 19 et Radix UI. Elle ne produit pas de son : elle envoie
des ordres au moteur en JSON et lit son état.

## Développer

Il faut Node 22. Le moteur doit répondre sur `:6811` : le plus simple est
[`scripts/dev.sh`](../scripts/dev.sh), qui lance le moteur en mode démo et la
console ensemble.

```bash
cd console
npm install
npm run dev          # http://127.0.0.1:5175/
npm test             # tests unitaires (node --test), dont la liste des routes de nginx
npm run build        # vérification des types puis build de production
```

En dev, Vite relaie les appels :

| Chemin | Vers | Variable pour changer la cible |
|---|---|---|
| `/api` | le moteur (`:6811`) | `AUTOMATE_PROXY` |
| `/library` | le catalogue (`:30127`) | `CATALOG_PROXY` |
| `/tus/` | l'envoi reprenable (`:8080`) | `TUSD_PROXY` |

## Organisation du code

| Dossier | Contenu |
|---|---|
| `src/pages/` | Une page par section : Antenne, Conducteur, Programmation, Sons, Réglages |
| `src/components/` | Composants d'écran (pupitre, conducteur, carts, horloges…) |
| `src/api/` | Client du moteur, rôles, session, formes des réponses (`types.ts`) |
| `src/lib/` | Écoute, vumètres, horloge de lecture locale |
| `src/layout/`, `src/ui/` | Coque de l'application et composants d'interface partagés |
| `public/brand.json` | Libellés et adresses affichés par la console |

Les rôles (Animateur, Programmateur, Admin) se traduisent en droits du moteur
au moment d'écrire un compte : voir [`docs/api.md`](../docs/api.md).

Les règles de l'interface et les pièges du code sont dans [`AGENTS.md`](AGENTS.md).

## Image Docker

`ghcr.io/lazbutton/button-console`, publiée par la CI à chaque changement de
`console/` sur `main`. nginx sert l'application et relaie l'API :

| Variable | Rôle | Défaut |
|---|---|---|
| `BUTTON_BACKEND` | Adresse du moteur | `http://127.0.0.1:6811` |
| `CATALOG_UPSTREAM` | Adresse du catalogue | `http://catalog:30127` |
| `TUSD_UPSTREAM` | Adresse de tusd | `http://tusd:8080` |

`AUTOMATE_BACKEND` reste accepté à la place de `BUTTON_BACKEND`.
