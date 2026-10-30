#!/bin/sh
set -eu
ICECAST_SOURCE_PASSWORD="${ICECAST_SOURCE_PASSWORD:-buttonhackme}"
ICECAST_ADMIN_PASSWORD="${ICECAST_ADMIN_PASSWORD:-buttonadmin}"
# Public contact shown on the Icecast status page.
ICECAST_ADMIN_EMAIL="${ICECAST_ADMIN_EMAIL:-admin@localhost}"
export ICECAST_SOURCE_PASSWORD ICECAST_ADMIN_PASSWORD ICECAST_ADMIN_EMAIL
# The tests point these at their own files.
TEMPLATE="${ICECAST_TEMPLATE:-/etc/icecast2/icecast.xml.template}"
CONFIG="${ICECAST_CONFIG:-/tmp/icecast.xml}"
# The playout sends the source password as typed: changed by one character,
# Icecast refuses the source. So awk reads the values from ENVIRON ("-v" would
# turn backslashes into escapes) and replaces with index (gsub would turn "&"
# into the matched text). XML escaping keeps "&" and "<" from breaking the
# file; Icecast decodes it.
awk '
function replace(text, from, to,    out, at) {
  out = ""
  while ((at = index(text, from)) > 0) {
    out = out substr(text, 1, at - 1) to
    text = substr(text, at + length(from))
  }
  return out text
}
function xml(text) {
  text = replace(text, "&", "&amp;")
  text = replace(text, "<", "&lt;")
  text = replace(text, ">", "&gt;")
  return replace(text, "\"", "&quot;")
}
BEGIN {
  src = xml(ENVIRON["ICECAST_SOURCE_PASSWORD"])
  adm = xml(ENVIRON["ICECAST_ADMIN_PASSWORD"])
  email = xml(ENVIRON["ICECAST_ADMIN_EMAIL"])
}
{
  line = replace($0, "__ICECAST_SOURCE_PASSWORD__", src)
  line = replace(line, "__ICECAST_ADMIN_PASSWORD__", adm)
  print replace(line, "__ICECAST_ADMIN_EMAIL__", email)
}' "$TEMPLATE" > "$CONFIG"
exec icecast2 -c "$CONFIG"
