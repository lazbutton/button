"""python scripts/test_licences.py — le contrôle des licences des dépendances (LEG-01)."""

from __future__ import annotations

import contextlib
import email
import io
import json
import tempfile
import unittest
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
        self.assertEqual(licences.parse("MIT"), ("id", "MIT"))
        self.assertEqual(
            licences.parse("(MIT OR Apache-2.0) AND BSD-3-Clause"),
            ("and", ("or", ("id", "MIT"), ("id", "Apache-2.0")), ("id", "BSD-3-Clause")),
        )
        # AND lie plus fort que OR.
        self.assertEqual(
            licences.parse("MIT OR ISC AND Zlib"),
            ("or", ("id", "MIT"), ("and", ("id", "ISC"), ("id", "Zlib"))),
        )
        self.assertEqual(
            licences.parse("GPL-2.0+ WITH Classpath-exception-2.0"), ("id", "GPL-2.0-or-later")
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
            "Apache-2.0 WITH LLVM-exception": licences.ACCEPTED,
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
        dist = FakeDist(
            "Classifier: License :: OSI Approved :: MIT License\n"
            "Classifier: License :: Other/Proprietary License\n"
        )
        license_ = licences.python_license(dist)
        self.assertIn("Other/Proprietary License", license_)
        with self.assertRaises(licences.Unreadable):
            licences.parse(license_)

    def test_nothing(self) -> None:
        self.assertIsNone(licences.python_license(FakeDist("Name: rien\n")))


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
        self.assertIn("Une licence inconnue se vérifie", output)


if __name__ == "__main__":
    unittest.main()
