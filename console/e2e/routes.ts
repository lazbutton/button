import { readFileSync } from "node:fs";

// Les routes du moteur, celles que nginx lui relaie, lues dans le gabarit comme
// le fait src/api/nginxRoutes.test.ts. Le relais de vite preview et les
// parcours qui simulent le moteur partent de la même liste.
const template = readFileSync(new URL("../docker/nginx.conf.template", import.meta.url), "utf8");
const routes = template.match(/location ~ \^\/\((.+)\) \{/)?.[1];
if (!routes) throw new Error("Liste des routes du moteur introuvable dans nginx.conf.template.");

/** L'alternative des routes du moteur, à placer après « ^/ » dans une expression. */
export const engineRoutes = routes;
