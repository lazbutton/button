import { mergeConfig } from "vite";
import base from "../vite.config.ts";
import { engineRoutes } from "./routes.ts";

// vite preview sert le build de la console comme nginx le sert en prod : les
// routes du moteur à la racine, le catalogue sous /library, tusd sous /tus.
// La liste des routes du moteur est lue dans le gabarit de nginx, comme le
// fait src/api/nginxRoutes.test.ts : une route qu'il ne relaie pas casse aussi
// les parcours. scripts/e2e.sh donne les adresses du banc.

function address(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} manque : lancer les parcours avec ./scripts/e2e.sh.`);
  return value;
}

const engine = address("E2E_MOTEUR");

export default mergeConfig(base, {
  preview: {
    proxy: {
      [`^/(${engineRoutes})`]: { target: engine, xfwd: true },
      // Comme nginx : les routes d'un invité ne reçoivent aucun cookie.
      "^/public/": { target: engine, xfwd: true, headers: { cookie: "" } },
      "/library/": {
        target: address("E2E_CATALOGUE"),
        xfwd: true,
        rewrite: (path: string) => path.replace(/^\/library/, ""),
      },
      "/tus/": { target: address("E2E_TUSD"), xfwd: true },
    },
  },
});
