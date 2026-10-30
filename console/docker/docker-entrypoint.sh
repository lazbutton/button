#!/bin/sh
set -e
if [ -n "${BUTTON_BACKEND:-}" ]; then
  AUTOMATE_BACKEND=$BUTTON_BACKEND
fi
: "${AUTOMATE_BACKEND:=http://127.0.0.1:6811}"
: "${CATALOG_UPSTREAM:=http://catalog:30127}"
: "${TUSD_UPSTREAM:=http://tusd:8080}"
# Le flux et now.json sur une autre origine : des sources de la CSP, séparées
# par des espaces. Ni guillemet, ni point-virgule, ni $ : la valeur entre telle
# quelle dans la configuration de nginx. Vides par défaut.
case "$CSP_MEDIA_SRC $CSP_CONNECT_SRC" in
  *[!A-Za-z0-9\ .:/*_~%-]*)
    echo "CSP_MEDIA_SRC, CSP_CONNECT_SRC : des origines séparées par des espaces, comme https://flux.radio.example (docs/deploiement.md, « Les en-têtes de sécurité »)." >&2
    exit 1
    ;;
esac
AUTOMATE_BACKEND=${AUTOMATE_BACKEND%/}
CATALOG_UPSTREAM=${CATALOG_UPSTREAM%/}
TUSD_UPSTREAM=${TUSD_UPSTREAM%/}
# Une espace devant chaque liste non vide : security-headers.conf la colle à
# la source qui la précède.
CSP_MEDIA_SRC=${CSP_MEDIA_SRC:+ $CSP_MEDIA_SRC}
CSP_CONNECT_SRC=${CSP_CONNECT_SRC:+ $CSP_CONNECT_SRC}
export AUTOMATE_BACKEND CATALOG_UPSTREAM TUSD_UPSTREAM CSP_MEDIA_SRC CSP_CONNECT_SRC
variables='${AUTOMATE_BACKEND} ${CATALOG_UPSTREAM} ${TUSD_UPSTREAM} ${CSP_MEDIA_SRC} ${CSP_CONNECT_SRC}'
envsubst "$variables" < /etc/nginx/nginx-default.conf.template > /etc/nginx/conf.d/default.conf
envsubst "$variables" < /etc/nginx/security-headers.conf.template > /etc/nginx/security-headers.conf
