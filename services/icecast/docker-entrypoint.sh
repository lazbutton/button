#!/bin/sh
set -eu
SRC="${ICECAST_SOURCE_PASSWORD:-buttonhackme}"
ADMIN="${ICECAST_ADMIN_PASSWORD:-buttonadmin}"
# Public contact shown on the Icecast status page.
EMAIL="${ICECAST_ADMIN_EMAIL:-admin@localhost}"
awk -v src="$SRC" -v adm="$ADMIN" -v email="$EMAIL" '{
  gsub(/__ICECAST_SOURCE_PASSWORD__/, src)
  gsub(/__ICECAST_ADMIN_PASSWORD__/, adm)
  gsub(/__ICECAST_ADMIN_EMAIL__/, email)
  print
}' /etc/icecast2/icecast.xml.template > /tmp/icecast.xml
exec icecast2 -c /tmp/icecast.xml
