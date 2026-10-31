#!/bin/sh
set -e
if [ -n "${BUTTON_BACKEND:-}" ]; then
  AUTOMATE_BACKEND=$BUTTON_BACKEND
fi
: "${AUTOMATE_BACKEND:=http://127.0.0.1:6811}"
: "${CATALOG_UPSTREAM:=http://catalog:30127}"
: "${TUSD_UPSTREAM:=http://tusd:8080}"
# Les reverse proxies de confiance : nginx ne croit qu'eux pour l'adresse du
# client, dans X-Forwarded-For. Des adresses ou des réseaux, séparés par des
# espaces. Vide ou absente : la boucle locale et les réseaux privés, où est un
# reverse proxy posé sur la machine ou dans Compose. Pas de nom d'hôte : nginx
# le résoudrait au démarrage, et ne démarrerait pas sans lui.
: "${TRUSTED_PROXIES:=127.0.0.0/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7}"
case "$TRUSTED_PROXIES" in
  *[!0-9A-Fa-f\ .:/]*)
    echo "TRUSTED_PROXIES : des adresses ou des réseaux séparés par des espaces, comme 172.16.0.0/12 ou 127.0.0.1." >&2
    exit 1
    ;;
esac
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
# Un set_real_ip_from par proxy : nginx.conf.template inclut ce fichier.
for proxy in $TRUSTED_PROXIES; do
  echo "set_real_ip_from $proxy;"
done > /etc/nginx/real-ip.conf
