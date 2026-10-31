#!/usr/bin/env python3
"""Les licences des dépendances livrées avec BUTTON.

    scripts/licences.py npm console/package-lock.json engine/sass/package-lock.json
    scripts/licences.py poetry engine/poetry.lock
    scripts/licences.py pip

npm : les paquets d'un package-lock.json, sauf ceux de développement.
poetry : le groupe main d'un poetry.lock. pip : toutes les distributions de
l'environnement. Pour ces deux-là, la licence se lit dans l'environnement de
l'interpréteur qui lance le script : le lancer avec celui du projet, par
exemple `poetry run python`.

Chaque licence doit être acceptée par licences.toml, à côté de ce script.
Une dépendance refusée, ou dont la licence ne se lit pas, fait échouer le
contrôle. Stdlib seule.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from collections import Counter
from importlib import metadata
from pathlib import Path

POLICY = Path(__file__).with_name("licences.toml")

ACCEPTED = "acceptée"
REFUSED = "refusée"
UNKNOWN = "inconnue"

# Les anciens identifiants SPDX, encore courants dans les métadonnées. SPDX
# compare les identifiants sans tenir compte de la casse.
DEPRECATED = {
    "agpl-3.0": "AGPL-3.0-only",
    "gpl-2.0+": "GPL-2.0-or-later",
    "gpl-3.0": "GPL-3.0-only",
    "gpl-3.0+": "GPL-3.0-or-later",
    "lgpl-2.0+": "LGPL-2.0-or-later",
    "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-2.1+": "LGPL-2.1-or-later",
    "lgpl-3.0": "LGPL-3.0-only",
    "lgpl-3.0+": "LGPL-3.0-or-later",
}

# Les classifieurs « License :: » de PyPI. « BSD License » ne dit pas combien
# de clauses : les BSD approuvées par l'OSI en ont 2 ou 3, toutes acceptées.
CLASSIFIERS = {
    "OSI Approved :: Apache Software License": "Apache-2.0",
    "OSI Approved :: BSD License": "BSD-3-Clause",
    "OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0-only",
    "OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0-or-later",
    "OSI Approved :: GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "OSI Approved :: GNU General Public License v2 or later (GPLv2+)": "GPL-2.0-or-later",
    "OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "OSI Approved :: GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.0-or-later",
    "OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "OSI Approved :: ISC License (ISCL)": "ISC",
    "OSI Approved :: MIT License": "MIT",
    "OSI Approved :: MIT No Attribution License (MIT-0)": "MIT-0",
    "OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "OSI Approved :: zlib/libpng License": "Zlib",
    "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
}

# Un champ License trop vague pour décider : les classifieurs le précisent.
VAGUE = {"", "unknown", "bsd", "gpl", "lgpl", "apache", "mpl", "psf", "dual license"}


class Unreadable(Exception):
    """Le texte n'est pas une expression SPDX."""


def parse(text: str) -> tuple:
    """Une expression SPDX en arbre : ("id", nom), ("or", a, b) ou ("and", a, b).

    Une exception (WITH) ne fait qu'ajouter des droits : la licence de base
    décide seule.
    """
    tokens = re.findall(r"[()]|[^\s()]+", text)
    pos = 0

    def peek() -> str:
        return tokens[pos].upper() if pos < len(tokens) else ""

    def disjunction() -> tuple:
        nonlocal pos
        tree = conjunction()
        while peek() == "OR":
            pos += 1
            tree = ("or", tree, conjunction())
        return tree

    def conjunction() -> tuple:
        nonlocal pos
        tree = term()
        while peek() == "AND":
            pos += 1
            tree = ("and", tree, term())
        return tree

    def identifier() -> str:
        nonlocal pos
        if peek() in ("", "(", ")", "AND", "OR", "WITH"):
            raise Unreadable(text)
        pos += 1
        return tokens[pos - 1]

    def term() -> tuple:
        nonlocal pos
        if peek() == "(":
            pos += 1
            tree = disjunction()
            if peek() != ")":
                raise Unreadable(text)
            pos += 1
            return tree
        name = identifier()
        if peek() == "WITH":
            pos += 1
            identifier()
        return ("id", DEPRECATED.get(name.lower(), name))

    tree = disjunction()
    if pos != len(tokens):
        raise Unreadable(text)
    return tree


def license_ids(tree: tuple) -> list[str]:
    if tree[0] == "id":
        return [tree[1]]
    return license_ids(tree[1]) + license_ids(tree[2])


class Policy:
    """licences.toml : les licences acceptées, les refusées, les paquets vérifiés."""

    def __init__(self, path: Path) -> None:
        with path.open("rb") as file:
            data = tomllib.load(file)
        self.accepted = {
            name.lower(): group["pourquoi"]
            for group in data["acceptees"]
            for name in group["licences"]
        }
        self.refused = {
            name.lower(): group["pourquoi"]
            for group in data["refusees"]
            for name in group["licences"]
        }
        self.checked = data.get("paquets", {})

    def status(self, tree: tuple) -> str:
        if tree[0] == "id":
            name = tree[1].lower()
            if name in self.accepted:
                return ACCEPTED
            return REFUSED if name in self.refused else UNKNOWN
        a, b = self.status(tree[1]), self.status(tree[2])
        if tree[0] == "or":
            if ACCEPTED in (a, b):
                return ACCEPTED
            return UNKNOWN if UNKNOWN in (a, b) else REFUSED
        if REFUSED in (a, b):
            return REFUSED
        return UNKNOWN if UNKNOWN in (a, b) else ACCEPTED

    def checked_license(self, ecosystem: str, name: str, version: str) -> str | None:
        """La licence d'un paquet vérifiée à la main, à cette version."""
        entry = self.checked.get(ecosystem, {}).get(f"{name}@{version}")
        return entry["licence"] if entry else None


def normalize(name: str) -> str:
    """Le nom d'une distribution Python selon la PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def python_license(dist: metadata.Distribution) -> str | None:
    """License-Expression, puis License, puis les classifieurs."""
    meta = dist.metadata
    for field in ("License-Expression", "License"):
        text = (meta.get(field) or "").strip()
        # Un texte de licence entier, ou une phrase, n'est pas un identifiant.
        if "\n" in text or len(text) > 100 or text.lower() in VAGUE:
            continue
        try:
            parse(text)
        except Unreadable:
            continue
        return text
    classifiers = [
        c.removeprefix("License :: ")
        for c in meta.get_all("Classifier") or []
        if c.startswith("License :: ") and c != "License :: OSI Approved"
    ]
    if not classifiers:
        return None
    if all(c in CLASSIFIERS for c in classifiers):
        return " AND ".join(CLASSIFIERS[c] for c in classifiers)
    return "classifieurs : " + " ; ".join(classifiers)


def npm_packages(lockfile: Path):
    data = json.loads(lockfile.read_text(encoding="utf-8"))
    if "packages" not in data:
        sys.exit(f"{lockfile} : lockfileVersion 2 ou plus attendu.")
    for path, package in data["packages"].items():
        # La racine est BUTTON lui-même ; un lien, du code du dépôt.
        if not path or package.get("dev") or package.get("link"):
            continue
        name = package.get("name") or path.rpartition("node_modules/")[2]
        license_ = package.get("license")
        yield name, package.get("version", "?"), license_ if isinstance(license_, str) else None


def poetry_packages(lockfile: Path):
    with lockfile.open("rb") as file:
        data = tomllib.load(file)
    for package in data.get("package", []):
        if "main" not in package.get("groups", ["main"]):
            continue
        name, version = package["name"], package["version"]
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            markers = package.get("markers")
            if isinstance(markers, dict):
                markers = markers.get("main")
            if markers:
                print(f"  {name} {version} : pas pour cette plateforme ({markers}), sauté")
                continue
            sys.exit(f"{name} {version} n'est pas installé : lancer d'abord poetry install.")
        if dist.version != version:
            sys.exit(
                f"{name} : {dist.version} installé, {version} verrouillé :"
                " lancer d'abord poetry install."
            )
        yield normalize(name), version, python_license(dist)


def pip_packages():
    seen = {}
    for dist in metadata.distributions():
        seen.setdefault(normalize(dist.metadata["Name"]), dist)
    for name, dist in sorted(seen.items()):
        yield name, dist.version, python_license(dist)


def check(policy: Policy, ecosystem: str, source: str, packages) -> bool:
    """Contrôle les paquets d'une source et dit ce qui échoue. Vrai si tout passe."""
    counts = Counter()
    failures = []
    for name, version, read in packages:
        license_ = policy.checked_license(ecosystem, name, version) or read
        if license_ is None:
            failures.append((name, version, "aucune licence lue", UNKNOWN, None))
            continue
        try:
            tree = parse(license_)
        except Unreadable:
            failures.append((name, version, license_, UNKNOWN, None))
            continue
        status = policy.status(tree)
        if status == ACCEPTED:
            counts[license_] += 1
        else:
            failures.append((name, version, license_, status, tree))

    total = sum(counts.values()) + len(failures)
    detail = ", ".join(f"{license_} {n}" for license_, n in counts.most_common())
    if not failures:
        print(f"{source} : {total} paquets, licences acceptées ({detail})")
        return True

    print(f"{source} : {len(failures)} paquet(s) en échec sur {total}", file=sys.stderr)
    for name, version, license_, status, tree in failures:
        print(f"  {name} {version} : {license_}, {status}", file=sys.stderr)
        if status == REFUSED:
            for license_id in license_ids(tree):
                reason = policy.refused.get(license_id.lower())
                if reason:
                    print(f"    {license_id} : {reason}", file=sys.stderr)
    if any(failure[3] == UNKNOWN for failure in failures):
        print(
            "  Une licence inconnue se vérifie, puis s'ajoute à [[acceptees]] ou à"
            " [[refusees]] de scripts/licences.toml, avec sa raison. Un paquet sans"
            " licence lisible va dans [paquets], une fois sa licence vérifiée.",
            file=sys.stderr,
        )
    return False


def main(args: list[str]) -> int:
    policy = Policy(POLICY)
    mode, rest = (args[0], args[1:]) if args else ("", [])
    if mode == "npm" and rest:
        results = [check(policy, "npm", lock, npm_packages(Path(lock))) for lock in rest]
    elif mode == "poetry" and len(rest) == 1:
        results = [check(policy, "python", rest[0], poetry_packages(Path(rest[0])))]
    elif mode == "pip" and not rest:
        results = [check(policy, "python", sys.prefix, pip_packages())]
    else:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 64
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
