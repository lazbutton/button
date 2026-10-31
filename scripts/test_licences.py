"""python scripts/test_licences.py — le contrôle des licences des dépendances (LEG-01)."""

from __future__ import annotations

import contextlib
import email
import io
import json
import tempfile
import unittest
from importlib import metadata
from pathlib import Path

import licences

POLICY = licences.Policy(licences.POLICY)


def status(expression: str) -> str:
    return POLICY.status(licences.parse(expression))


class FakeDist:
    """Une distribution Python réduite à ses métadonnées."""

    def __init__(self, headers: str) -> None:
        self.metadata = email.message_from_string(headers)


class ParseTest(unittest.TestCase):
    def test_expressions(self) -> None:
        mit = ("id", "MIT", None)
        self.assertEqual(licences.parse("MIT"), ("id", "MIT", None))
        self.assertEqual(
            licences.parse("(MIT OR Apache-2.0) AND BSD-3-Clause"),
            ("and", ("or", mit, ("id", "Apache-2.0", None)), ("id", "BSD-3-Clause", None)),
        )
        # AND lie plus fort que OR.
        self.assertEqual(
            licences.parse("MIT OR ISC AND Zlib"),
            ("or", mit, ("and", ("id", "ISC", None), ("id", "Zlib", None))),
        )
        self.assertEqual(
            licences.parse("GPL-2.0+ WITH Classpath-exception-2.0"),
            ("id", "GPL-2.0-or-later", "Classpath-exception-2.0"),
        )

    def test_unreadable(self) -> None:
        for text in ("", "MIT License", "(MIT", "MIT OR", "MIT WITH", "SEE LICENSE IN LICENSE"):
            with self.subTest(text=text), self.assertRaises(licences.Unreadable):
                licences.parse(text)


class PolicyTest(unittest.TestCase):
    def test_status(self) -> None:
        cases = {
            "MIT": licences.ACCEPTED,
            "mit": licences.ACCEPTED,
            "GPL-3.0": licences.ACCEPTED,
            "lgpl-2.1+": licences.ACCEPTED,
            "Apache-2.0 WITH LLVM-exception": licences.ACCEPTED,
            # Commons-Clause interdit la vente : une exception inconnue ne passe pas.
            "Apache-2.0 WITH Commons-Clause": licences.UNKNOWN,
            "MIT WITH LicenseRef-NonCommercial": licences.UNKNOWN,
            "GPL-2.0-only WITH Classpath-exception-2.0": licences.REFUSED,
            "GPL-2.0-only": licences.REFUSED,
            "GPL-2.0": licences.REFUSED,
            "MIT OR GPL-2.0-only": licences.ACCEPTED,
            "MIT AND GPL-2.0-only": licences.REFUSED,
            "Foo-1.0": licences.UNKNOWN,
            "MIT OR Foo-1.0": licences.ACCEPTED,
            "MIT AND Foo-1.0": licences.UNKNOWN,
            "GPL-2.0-only OR Foo-1.0": licences.UNKNOWN,
            "GPL-2.0-only AND Foo-1.0": licences.REFUSED,
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(status(expression), expected)

    def test_lists(self) -> None:
        self.assertFalse(POLICY.accepted.keys() & POLICY.refused.keys())
        self.assertFalse(POLICY.exceptions & (POLICY.accepted.keys() | POLICY.refused.keys()))
        for ecosystem, packages in POLICY.checked.items():
            for package, entry in packages.items():
                with self.subTest(package=f"{ecosystem}:{package}"):
                    self.assertEqual(status(entry["licence"]), licences.ACCEPTED)
                    self.assertTrue(entry["verifiee"])


class PythonLicenseTest(unittest.TestCase):
    GPL2_ONLY = "Classifier: License :: OSI Approved :: GNU General Public License v2 (GPLv2)\n"
    GPL2_LATER = (
        "Classifier: License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)\n"
    )

    def test_license_expression_first(self) -> None:
        dist = FakeDist("License-Expression: MIT\nLicense: GPL\n" + self.GPL2_ONLY)
        self.assertEqual(licences.python_license(dist), "MIT")

    def test_license_field(self) -> None:
        dist = FakeDist("License: MIT AND Python-2.0\n" + self.GPL2_ONLY)
        self.assertEqual(licences.python_license(dist), "MIT AND Python-2.0")

    def test_classifiers_when_the_field_says_too_little(self) -> None:
        for field in (
            "License: GPL\n",
            "License-Expression: MIT license\n",
            "License: Copyright (c) 2005, NumPy Developers.\n All rights reserved.\n",
            "",
        ):
            with self.subTest(field=field):
                dist = FakeDist(field + self.GPL2_LATER)
                self.assertEqual(licences.python_license(dist), "GPL-2.0-or-later")

    def test_classifiers_together(self) -> None:
        dist = FakeDist(
            "Classifier: License :: OSI Approved\n"
            "Classifier: License :: OSI Approved :: BSD License\n"
            "Classifier: License :: OSI Approved :: ISC License (ISCL)\n"
        )
        self.assertEqual(licences.python_license(dist), "BSD-3-Clause AND ISC")

    def test_unknown_classifier(self) -> None:
        for classifier in (
            "Other/Proprietary License",
            # Apache 1.1 ou 2.0 : le classifieur ne le dit pas.
            "OSI Approved :: Apache Software License",
        ):
            with self.subTest(classifier=classifier):
                dist = FakeDist(
                    "Classifier: License :: OSI Approved :: MIT License\n"
                    f"Classifier: License :: {classifier}\n"
                )
                license_ = licences.python_license(dist)
                self.assertIn(classifier, license_)
                with self.assertRaises(licences.Unreadable):
                    licences.parse(license_)

    def test_nothing(self) -> None:
        self.assertIsNone(licences.python_license(FakeDist("Name: rien\n")))


class PoetryTest(unittest.TestCase):
    """Le groupe main d'un poetry.lock, lu dans l'environnement des tests."""

    def setUp(self) -> None:
        try:
            self.pip = metadata.version("pip")
        except metadata.PackageNotFoundError:
            self.skipTest("pip absent de cet environnement")

    def read(self, lock: str) -> tuple[list, str]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        lockfile = Path(directory.name) / "poetry.lock"
        lockfile.write_text(lock)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            packages = list(licences.poetry_packages(lockfile))
        return packages, output.getvalue()

    def test_main_group(self) -> None:
        packages, output = self.read(
            f"""
            [[package]]
            name = "pip"
            version = "{self.pip}"
            groups = ["main"]

            [[package]]
            name = "outil-de-dev"
            version = "1.0"
            groups = ["dev"]

            [[package]]
            name = "pour-windows"
            version = "1.0"
            groups = ["main"]
            markers = {{main = "sys_platform == 'win32'"}}
            """
        )
        self.assertEqual([(name, version) for name, version, _ in packages], [("pip", self.pip)])
        self.assertIn("pour-windows 1.0 : pas installé ici", output)

    def test_environment_out_of_date(self) -> None:
        for name, version in (("absent-sans-marqueur", "1.0"), ("pip", "0.0.1")):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                self.read(f'[[package]]\nname = "{name}"\nversion = "{version}"\ngroups = ["main"]\n')


class NpmTest(unittest.TestCase):
    def check(self, packages: dict) -> tuple[bool, str]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        lockfile = Path(directory.name) / "package-lock.json"
        root = {"": {"name": "button-console", "license": "AGPL-3.0-or-later"}}
        lockfile.write_text(json.dumps({"lockfileVersion": 3, "packages": {**root, **packages}}))
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            passed = licences.check(
                POLICY, "npm", "package-lock.json", licences.npm_packages(lockfile)
            )
        return passed, output.getvalue()

    def test_accepted(self) -> None:
        passed, output = self.check(
            {
                "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                # Un outil de développement n'est pas livré.
                "node_modules/outil": {"version": "1.0.0", "license": "GPL-2.0-only", "dev": True},
                # Sa licence est vérifiée à la main dans licences.toml.
                "node_modules/combine-errors": {"version": "3.0.3"},
            }
        )
        self.assertTrue(passed, output)
        self.assertIn("2 paquets, licences acceptées (MIT 2)", output)

    def test_refused_and_unknown(self) -> None:
        passed, output = self.check(
            {
                "node_modules/gpl": {"version": "1.0.0", "license": "GPL-2.0-only"},
                "node_modules/@scope/muet": {"version": "2.0.0"},
                # Vérifiée en 3.0.3 seulement : une autre version repasse.
                "node_modules/combine-errors": {"version": "3.0.4"},
            }
        )
        self.assertFalse(passed)
        self.assertIn("3 paquet(s) en échec sur 3", output)
        self.assertIn("gpl 1.0.0 : GPL-2.0-only, refusée", output)
        self.assertIn("GPL-2.0-only : GPL v2 seule", output)
        self.assertIn("@scope/muet 2.0.0 : aucune licence lue, inconnue", output)
        self.assertIn("combine-errors 3.0.4 : aucune licence lue, inconnue", output)
        self.assertIn("inconnue se vérifie", output)


if __name__ == "__main__":
    unittest.main()
