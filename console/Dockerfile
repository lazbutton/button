# The source code of this version, for the "Code source" link (AGPL): the
# archive and source.json that scripts/version.py source writes. console.yml
# passes them as the source build context, which replaces this empty stage.
# Built without it, the image serves none, and the link leads to the
# repository.
FROM scratch AS source

FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginx:1.31-alpine AS serve
# The nginx image is only rebuilt with a release of nginx or of Alpine:
# Alpine's fixes in between come in here, at each build (console.yml never
# takes this stage from its cache). nginx and its modules keep the image's
# version, pinned in /etc/apk/world.
RUN apk upgrade --no-cache
COPY docker/nginx.conf.template /etc/nginx/nginx-default.conf.template
COPY docker/security-headers.conf.template /etc/nginx/security-headers.conf.template
COPY docker/docker-entrypoint.sh /docker-entrypoint.d/99-automate-backend.sh
COPY --from=build /app/dist /usr/share/nginx/html
# Outside the html root: nginx serves it to a team session only.
COPY --from=source / /usr/share/nginx/source/
RUN chmod +x /docker-entrypoint.d/99-automate-backend.sh
ENV AUTOMATE_BACKEND=http://127.0.0.1:6811
ENV CATALOG_UPSTREAM=http://catalog:30127
ENV TUSD_UPSTREAM=http://tusd:8080
ENV CSP_MEDIA_SRC=
ENV CSP_CONNECT_SRC=
ENV TRUSTED_PROXIES="127.0.0.0/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7"
EXPOSE 80
