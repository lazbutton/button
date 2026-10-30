# Consignes pour la console

À lire avec le [AGENTS.md](../AGENTS.md) de la racine. La console est une application React 19 (Vite 7, TypeScript 5.9, Radix Themes). En prod, nginx la sert et relaie l'API du moteur.

## Lancer et vérifier

```bash
cd console
npm install                       # une fois par worktree
npm run dev                       # http://127.0.0.1:5175, moteur attendu sur :6811
../scripts/verifier.sh console    # npm test, puis tsc et vite build, comme la CI
```

En dev, Vite relaie `/api` vers le moteur, `/library` vers le catalogue et `/tus` vers tusd (`vite.config.ts`). Les variables `AUTOMATE_PROXY`, `CATALOG_PROXY` et `TUSD_PROXY` changent ces adresses. Une deuxième console peut partager le même moteur : `npx vite --port 5176 --strictPort`.

## Où est quoi

| Chemin | Rôle |
|---|---|
| `src/App.tsx` | Les routes. Chaque écran a sa route, et aucune route ne redirige |
| `src/pages/` | Une page par écran |
| `src/components/<domaine>/` | Les composants d'un domaine : `agenda`, `antenne`, `banque`, `carts`, `programmation`, `topbar` |
| `src/ui/` | Les briques communes : `DataState`, `EmptyState`, `ConfirmDialog`, `FormField`, `Panel`, `AppToast`… |
| `src/api/client.ts` | Le seul chemin vers le moteur : `apiGet`, `apiPostJson`, `apiPut`, `apiPatch`, `apiDeleteJson`, `apiUpload`… |
| `src/api/<domaine>.ts` | Les appels et la logique pure d'un domaine, testée à côté (`*.test.ts`) |
| `src/api/types.ts` | La forme des réponses du moteur |
| `src/lib/` | Hooks et contexte : marque (`brand.ts`), écoute (`useMonitor.ts`), heure de Paris (`parisClock.ts`) |
| `src/styles/tokens.css` | Les couleurs et tailles, en clair et en sombre |
| `docker/nginx.conf.template` | Le nginx de prod, avec la liste des routes du moteur |
| `e2e/` | Les parcours Playwright, avec le faux catalogue et le faux tusd (`stubs/`) |

## Les règles de l'interface

- En français, en thème clair et sombre. Les couleurs viennent de `tokens.css`, jamais en dur.
- Sur téléphone : colonnes empilées, cibles de 40 px au moins.
- Au clavier : tout se fait sans souris, le focus se voit, les contrastes suffisent.
- **Jamais d'échec silencieux.** Session expirée, droit manquant, moteur injoignable : chaque cas a son message. `client.ts` lève `ApiAuthError`, `ApiForbiddenError`, `ApiUnavailableError` ou `ApiRequestError`. Les états de chargement et d'erreur passent par `src/ui/DataState.tsx`.
- **Une fonction nouvelle survit à un moteur plus ancien.** Si sa route répond 404, c'est-à-dire une `ApiRequestError` de statut 404, la fonction se cache et la console affiche « Mets à jour le moteur », jamais une page blanche. Aucun écran ne le fait encore : la règle vaut pour les fonctions à venir. La console et le moteur se déploient à part : [ADR 0010](../docs/decisions/0010-moteur-et-console-se-deploient-a-part.md).
- Les rôles se lisent et s'écrivent par `src/api/roles.ts`. L'écran ne montre jamais les six droits bruts : [docs/api.md](../docs/api.md#rôles-et-droits).
- Les envois de fichiers passent par Uppy et tusd, nulle part ailleurs.
- Pas de dépendance lourde. Une dépendance nouvelle se justifie, et sa licence est compatible avec l'AGPL.
- Le lien « Code source », étiqueté AGPL, reste accessible dans le menu du compte (`components/topbar/AccountMenu.tsx`).

## Tests

- `npm test` lance `node --experimental-strip-types --test src/api/*.test.ts`. Seuls les fichiers de test au premier niveau de `src/api/` tournent. La logique à tester va donc dans un module de `src/api/`, sans React.
- Les imports des tests portent l'extension `.ts`. `tsc` ignore les tests (`tsconfig.json`).
- `src/api/nginxRoutes.test.ts` échoue si la console appelle une route du moteur que nginx ne relaie pas.
- Les parcours dans un vrai navigateur sont dans `e2e/`, avec Playwright. `../scripts/e2e.sh` monte leur banc et les lance : [docs/developpement.md](../docs/developpement.md#les-parcours-dans-un-navigateur).

## Pièges

- **Une nouvelle page de premier niveau**, comme `/antenne`, s'ajoute aussi dans `engine/radiotomate/interface/spa.py`. Le moteur y sert la console quand son build est posé à côté de lui.
- En dev, le mode strict de React lance les effets deux fois. Un objet comme une instance Uppy se garde au niveau du module, sans destruction au nettoyage.
- Une heure de l'Agenda s'affiche à Paris dans la console, et à l'heure locale chez l'invité. Toujours passer par les fonctions du domaine (`agendaView.ts`, `parisClock.ts`), jamais par `Date` brut.
- Les gros fichiers sont des points de conflit entre agents : `pages/ImporterPage.tsx`, `lib/useMonitor.ts`, `components/agenda/DiffusionDialog.tsx`, `pages/AntennePage.tsx`, `pages/AgendaPage.tsx`, `pages/SemainePage.tsx`, `api/types.ts`. Un seul agent à la fois sur chacun : [docs/travailler-a-plusieurs.md](../docs/travailler-a-plusieurs.md).
- `public/brand.json` et les replis de `lib/` contiennent encore des adresses d'une station. La fiche GEN-02 les retire. N'en ajoute pas.
