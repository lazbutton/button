"""La pochette d'un titre trouvé, par son lien (FON-83).

Tranché le 15 novembre 2026 avec l'utilisateur : la pochette ne se montre que dans la
console, la fiche d'un titre et le titre en cours, derrière un réglage éteint par
défaut. Seul son lien se garde, dans les preuves : elle n'est jamais copiée, jamais
écrite dans le fichier, et `now.json` n'en dit rien.

Un lien ne se rend que s'il mène, en HTTPS, à l'un des hôtes d'images des sources,
ceux que la politique de contenu de la console admet
(`console/docker/security-headers.conf.template`) : un lien d'ailleurs ne serait pas
chargé, et ne doit pas l'être.

Sans réseau, sans Quart, sans Beets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from radiotomate.fiches.proposals import SearchResult

# Les domaines des images des sources, chacun avec ses sous-domaines : Deezer
# (`cdn-images.dzcdn.net`, `e-cdns-images.dzcdn.net`), Apple Music
# (`is1-ssl.mzstatic.com`…) et Bandcamp (`f4.bcbits.com`…).
COVER_DOMAINS = ("dzcdn.net", "mzstatic.com", "bcbits.com")
# Une adresse plus longue n'est pas celle d'une pochette.
COVER_MAX = 500


def cover_link(url: object) -> str | None:
    """Le lien d'une pochette, s'il est sûr : en HTTPS, sur un hôte d'images des
    sources, sans nom ni mot de passe, sans espace. None sinon."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > COVER_MAX or any(char.isspace() for char in url):
        return None
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    safe = (
        parts.scheme == "https"
        and not parts.username
        and not parts.password
        and port in (None, 443)
        and any(host.endswith(f".{domain}") for domain in COVER_DOMAINS)
    )
    return url if safe else None


def deezer_cover(url: object) -> str | None:
    """La pochette d'un album Deezer, `cover_big` : 500 pixels de côté."""
    return cover_link(url)


def apple_cover(artwork: object) -> str | None:
    """La pochette d'Apple Music : `artworkUrl100`, demandée en 600 pixels de côté,
    comme l'API d'iTunes le permet."""
    if not isinstance(artwork, str):
        return None
    return cover_link(artwork.replace("100x100bb", "600x600bb"))


def bandcamp_cover(art_id: object) -> str | None:
    """La pochette de Bandcamp par son `art_id` : « a{art_id}_5.jpg », 700 pixels de
    côté."""
    if isinstance(art_id, bool) or not isinstance(art_id, int) or art_id <= 0:
        return None
    return cover_link(f"https://f4.bcbits.com/img/a{art_id:010d}_5.jpg")


def cover_of(result: SearchResult | None) -> str | None:
    """La pochette d'un titre trouvé, d'après ses preuves : l'album Deezer, sinon le
    morceau d'Apple Music, sinon celle du morceau trouvé (Bandcamp)."""
    if result is None or result.match is None:
        return None
    details = result.details
    deezer = details.deezer if details else None
    album = deezer.album if deezer else None
    apple = details.apple if details else None
    for url in (
        album.cover if album else None,
        apple.cover if apple else None,
        result.match.cover,
    ):
        found = cover_link(url)
        if found:
            return found
    return None
