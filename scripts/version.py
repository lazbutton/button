#!/usr/bin/env python3
"""Les versions publiées de BUTTON, pour le workflow version.yml.

    scripts/version.py notes 0.1.0 [--liens https://github.com/<dépôt>/blob/v0.1.0/]
    scripts/version.py tags 0.1.0 [v0.0.9 v0.1.1 …]
    scripts/version.py avant 0.1.1 [v0.1.0 v0.1.1 …]
    scripts/version.py images
    scripts/version.py lignes <CHANGELOG d'avant> <CHANGELOG d'après> [v0.1.0 …]

notes : les notes de la version, sa partie de CHANGELOG.md sans son titre,
`## 0.1.0`, seul sur sa ligne ou suivi d'une espace. Un `## ` dans un bloc de
code ne coupe pas la partie. Avec --liens, chaque lien relatif part de cette
adresse : sur la page de la version, il ne mènerait nulle part. Échoue si la
partie manque ou ne dit rien.

tags : les tags que la version prend en plus de X.Y.Z, d'après les versions
déjà publiées, données après elle : X.Y si aucune version X.Y publiée n'est
plus haute, et stable si aucune version publiée n'est plus haute. Un correctif
d'une ancienne version, publié après une plus récente, ne fait donc jamais
reculer stable.

avant : la version d'avant de la même ligne X.Y, parmi les tags donnés, ceux
de l'histoire du commit à publier (git tag --merged HEAD) ; rien pour la
première. Échoue si l'un d'eux est plus haut : un correctif d'une ancienne
version part du tag de sa ligne, pas de main.

images : les images de BUTTON, celles de deploy/compose.yml qui suivent
BUTTON_VERSION, une par ligne.

lignes : compare deux états du CHANGELOG, avant et après une pull request ou
une fusion. Échoue si des lignes de liste s'ajoutent sous une version publiée,
celle d'un des tags donnés, ou de chaque partie de version sans tag donné. Une
branche ouverte avant la coupe d'une version y range sinon sa ligne sans le
voir, et la version suivante la perd. Couper une version, ce qui ajoute son
titre, passe. Stdlib seule.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
COMPOSE = ROOT / "deploy" / "compose.yml"

# X.Y.Z, sans zéro en tête ni préversion : 0.1.0, jamais 0.1 ni 0.1.0-rc.1.
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
FENCE = re.compile(r" {0,3}(```|~~~)")
# La cible d'un lien Markdown, en ligne ou en définition, qui n'est ni une
# adresse (https:, mailto:, //hôte), ni une ancre ou une requête de la même
# page. Un « / » en tête part de la racine du dépôt.
_LOCAL = r"(?![a-zA-Z][a-zA-Z0-9+.-]*:|#|\?|//)/?"
INLINE_LINK = re.compile(r"\]\((<?)" + _LOCAL)
# Les espaces avant la cible, toutes : sinon l'expression reviendrait sur
# l'une d'elles pour placer l'adresse devant un lien https:.
REFERENCE_LINK = re.compile(r"^( {0,3}\[[^\]]+\]:[ \t]*<?)(?=[^ \t<])" + _LOCAL)
# Une image de BUTTON dans compose.yml : …/button-<nom>:${BUTTON_VERSION…}.
IMAGE = re.compile(r"/(button-[a-z0-9-]+):\$\{BUTTON_VERSION\b")


def parse(version: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"{version} : une version s'écrit X.Y.Z, par exemple 0.1.0.")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def parse_tag(tag: str) -> tuple[int, int, int] | None:
    """Un tag git vX.Y.Z, ou None pour tout autre tag."""
    if not tag.startswith("v"):
        return None
    try:
        return parse(tag[1:])
    except ValueError:
        return None


def name(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def sections(changelog: str) -> list[tuple[str, list[str]]]:
    """Les parties du CHANGELOG, dans l'ordre : (titre sans « ## », lignes).
    Ce qui précède le premier titre a pour titre "". Les lignes d'un bloc de
    code ne sont jamais un titre."""
    parts: list[tuple[str, list[str]]] = [("", [])]
    fenced = False
    for line in changelog.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            parts.append((line[3:].strip(), []))
            continue
        parts[-1][1].append(line)
    return parts


def heading_version(heading: str) -> str:
    """Le numéro d'un titre de version : « 0.1.0 · 12 novembre » donne « 0.1.0 »."""
    first = heading.split(maxsplit=1)[0] if heading else ""
    return first if VERSION.fullmatch(first) else ""


def link_targets(body: str, base: str) -> str:
    """Les liens relatifs, hors code, partent de base."""
    lines, fenced = [], False
    for line in body.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            line = REFERENCE_LINK.sub(lambda match: match.group(1) + base, line)
            # Hors des `code` seulement : un morceau sur deux, entre les accents graves.
            pieces = line.split("`")
            pieces[::2] = [
                INLINE_LINK.sub(lambda match: "](" + match.group(1) + base, piece)
                for piece in pieces[::2]
            ]
            line = "`".join(pieces)
        lines.append(line)
    return "\n".join(lines)


def notes(version: str, changelog: str, links: str = "") -> str:
    parse(version)
    found = [lines for heading, lines in sections(changelog) if heading_version(heading) == version]
    if not found:
        raise ValueError(
            f"CHANGELOG.md n'a pas de partie « ## {version} ». La version se prépare dans"
            f" une pull request qui renomme « Non publié » en « ## {version} » : le tag se"
            " pose ensuite sur son commit. Voir docs/developpement.md, « Publier une version »."
        )
    body = "\n".join(found[0]).strip()
    if not body:
        raise ValueError(f"La partie « ## {version} » de CHANGELOG.md est vide : y mettre ses notes.")
    if links:
        body = link_targets(body, links)
    return body + "\n"


def tags(version: str, published: list[str]) -> list[str]:
    current = parse(version)
    others = []
    for tag in published:
        other = parse_tag(tag)
        if other is None:
            print(f"{tag} : pas une version vX.Y.Z, ignoré.", file=sys.stderr)
        else:
            others.append(other)
    extra = []
    # Des nombres, pas du texte : 0.10.0 passe après 0.9.0.
    if not any(other[:2] == current[:2] and other > current for other in others):
        extra.append(f"{current[0]}.{current[1]}")
    if not any(other > current for other in others):
        extra.append("stable")
    return extra


def previous(version: str, reachable: list[str]) -> str:
    current = parse(version)
    others = [other for other in map(parse_tag, reachable) if other is not None and other != current]
    newer = [other for other in others if other > current]
    if newer:
        raise ValueError(
            f"v{name(max(newer))} est déjà dans l'histoire de ce commit, plus haute que {version}."
            f" Un correctif de la {current[0]}.{current[1]} se pose sur une branche tirée de son"
            " dernier tag, pas sur main : voir docs/developpement.md, « Publier une version »."
        )
    line = [other for other in others if other[:2] == current[:2]]
    return name(max(line)) if line else ""


def images(compose: str) -> list[str]:
    return sorted(set(IMAGE.findall(compose)))


def released_lines(changelog: str, published: set[str] | None = None) -> list[str]:
    """Les lignes de liste des versions publiées : celles de published, ou
    toutes les versions du CHANGELOG sans published."""
    return [
        line
        for heading, lines in sections(changelog)
        if heading_version(heading) and (published is None or heading_version(heading) in published)
        for line in lines
        if line.startswith("- ")
    ]


def check_lines(before: str, after: str, tags: list[str] | None = None) -> None:
    def versions(text: str) -> set[str]:
        return {heading_version(heading) for heading, _ in sections(text)} - {""}

    if versions(after) - versions(before):
        return  # La coupe d'une version : ses lignes changent de partie.
    # Une version coupée mais pas encore taguée, ou dont le tag a été retiré
    # pour la reprendre, reçoit encore des lignes.
    published = None if tags is None else {name(v) for v in map(parse_tag, tags) if v is not None}
    added = Counter(released_lines(after, published)) - Counter(released_lines(before, published))
    if len(released_lines(after, published)) > len(released_lines(before, published)):
        raise ValueError(
            "Lignes ajoutées sous une version déjà publiée de CHANGELOG.md : les remettre"
            " à la fin de « Non publié ». Une branche ouverte avant la coupe d'une version"
            " y range sa ligne en fusionnant main.\n"
            + "\n".join(f"  {line[:100]}" for line in added)
        )


def main(args: list[str]) -> int:
    try:
        if len(args) == 2 and args[0] == "notes":
            print(notes(args[1], CHANGELOG.read_text(encoding="utf-8")), end="")
            return 0
        if len(args) == 4 and args[0] == "notes" and args[2] == "--liens":
            print(notes(args[1], CHANGELOG.read_text(encoding="utf-8"), args[3]), end="")
            return 0
        if len(args) >= 2 and args[0] == "tags":
            print(" ".join(tags(args[1], args[2:])))
            return 0
        if len(args) >= 2 and args[0] == "avant":
            print(previous(args[1], args[2:]))
            return 0
        if args == ["images"]:
            print("\n".join(images(COMPOSE.read_text(encoding="utf-8"))))
            return 0
        if len(args) >= 3 and args[0] == "lignes":
            before, after = (Path(path).read_text(encoding="utf-8") for path in args[1:3])
            check_lines(before, after, args[3:] or None)
            return 0
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
