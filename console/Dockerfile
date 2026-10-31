FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginx:1.29-alpine
COPY docker/nginx.conf.template /etc/nginx/nginx-default.conf.template
COPY docker/security-headers.conf.template /etc/nginx/security-headers.conf.template
COPY docker/docker-entrypoint.sh /docker-entrypoint.d/99-automate-backend.sh
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.d/99-automate-backend.sh
ENV AUTOMATE_BACKEND=http://127.0.0.1:6811
ENV CATALOG_UPSTREAM=http://catalog:30127
ENV TUSD_UPSTREAM=http://tusd:8080
ENV CSP_MEDIA_SRC=
ENV CSP_CONNECT_SRC=
ENV TRUSTED_PROXIES="127.0.0.0/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7"
EXPOSE 80
