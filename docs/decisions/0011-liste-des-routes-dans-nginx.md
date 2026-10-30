# 0011 · Les routes du moteur passent par une liste dans nginx

Acceptée, octobre 2026.

## Contexte

En prod, nginx sert la console et relaie l'API du moteur. Le moteur sert aussi les pages HTMX de l'amont, et des routes internes que seul le catalogue appelle.

## Décision

nginx ne relaie vers le moteur qu'une liste de chemins, écrite dans `console/docker/nginx.conf.template`. Une route nouvelle de la console y entre explicitement. Les routes internes (`/internal/…`) et les pages HTMX n'y entrent pas.

## Conséquences

- Le piège : une route absente de la liste marche en dev, par le proxy de Vite, et reçoit en prod la page HTML de la console.
- `console/src/api/nginxRoutes.test.ts` lit les appels de la console et la liste, et échoue si une route manque. Il tourne avec `npm test`, donc en CI.
