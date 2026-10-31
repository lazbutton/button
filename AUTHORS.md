# Auteurs et ressources

## Auteurs

- **lazbutton** : BUTTON, c'est-à-dire la console, les services, le déploiement et les changements du moteur par rapport à Radiotomate.
- **Martin Kirchgessner** : [Radiotomate](https://git.sr.ht/~martink/radiotomate), dont dérive le moteur (`engine/`). Voir aussi [`engine/AUTHORS`](engine/AUTHORS).

## Ressources incluses

Dans `engine/radiotomate/static/`, livrées avec l'interface d'origine de Radiotomate :

| Ressource | Projet | Licence |
|---|---|---|
| `htmx.min.js`, `htmx-sse.js` | [htmx](https://htmx.org/) | voir le projet |
| `alpinejs-3.13.0.min.js` | [Alpine.js](https://alpinejs.dev/) | voir le projet |
| `sweetalert2-11.7.31.js` | [SweetAlert2](https://sweetalert2.github.io/) | MIT |
| `Sortable.min.js` | [SortableJS](https://sortablejs.github.io/Sortable/) | MIT |
| `AtkinsonHyperlegible/` | [Atkinson Hyperlegible](https://www.brailleinstitute.org/freefont/), Braille Institute | voir le projet |

Le son de démarrage (`engine/radiotomate/commands/install/default_start_sound.wav`) est « inception sound 3 » de mikobuntu, sous [Creative Commons 0](https://freesound.org/people/mikobuntu/sounds/361118/).

Les dépendances installées par Poetry, pip et npm gardent leurs propres licences. La CI vérifie que celles qui sont livrées sont compatibles avec l'AGPL : la liste des licences acceptées, et pourquoi, est dans [`scripts/licences.toml`](scripts/licences.toml).
