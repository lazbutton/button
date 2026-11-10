"""python3 scripts/test_version.py — les versions publiées (MAJ-01)."""

from __future__ import annotations

import contextlib
import io
import re
import unittest
from collections import Counter

import version

CHANGELOG = """# Journal des changements

Les versions publiées, de la plus récente à la plus ancienne.

## Non publié

- Une ligne pas encore publiée.

## 0.10.0 · 1er décembre 2026

**Mise en service.** Le schéma passe en v19. Dans `.env` :

```bash
## Un commentaire, pas un titre
BUTTON_VERSION=0.10.0
```

- Voir [le guide](docs/deploiement.md#mettre-à-jour), [le site](https://radio.example/),
  [plus bas](#corrigé), [la racine](/README.md) et `[pas un lien](docs/x.md)`.

### Corrigé

- Un correctif.

## 0.1.1

- Un correctif de la 0.1.

## 0.1.0

- La première.
"""

BASE = "https://github.com/lazbutton/button/blob/v0.10.0/"


class NotesTest(unittest.TestCase):
    def test_the_section_without_its_heading(self) -> None:
        self.assertEqual(version.notes("0.1.0", CHANGELOG), "- La première.\n")

    def test_a_date_after_the_number_subheadings_and_code(self) -> None:
        notes = version.notes("0.10.0", CHANGELOG)
        self.assertTrue(notes.startswith("**Mise en service.**"), notes)
        # Le « ## » du bloc de code ne coupe pas la partie.
        self.assertIn("## Un commentaire, pas un titre\nBUTTON_VERSION=0.10.0\n```", notes)
        self.assertIn("### Corrigé\n\n- Un correctif.\n", notes)
        self.assertNotIn("Un correctif de la 0.1", notes)

    def test_a_number_is_not_the_start_of_another(self) -> None:
        # 0.1.1 ne prend pas la partie 0.10.0 qui la précède, ni 0.1.0 la sienne.
        self.assertEqual(version.notes("0.1.1", CHANGELOG), "- Un correctif de la 0.1.\n")
        with self.assertRaises(ValueError):
            version.notes("0.1.10", CHANGELOG)

    def test_relative_links_point_to_the_version(self) -> None:
        notes = version.notes("0.10.0", CHANGELOG, BASE)
        self.assertIn(f"[le guide]({BASE}docs/deploiement.md#mettre-à-jour)", notes)
        self.assertIn(f"[la racine]({BASE}README.md)", notes)
        self.assertIn("[le site](https://radio.example/)", notes)
        self.assertIn("[plus bas](#corrigé)", notes)
        # Ni le code en ligne, ni les blocs de code.
        self.assertIn("`[pas un lien](docs/x.md)`", notes)

    def test_other_link_forms(self) -> None:
        body = "\n".join(
            [
                "- [a](<docs/a b.md>), [b](//radio.example/x), [c](?q=1), [d](mailto:a@radio.example).",
                "",
                "[ref]: docs/ref.md",
                "[web]: https://radio.example/",
            ]
        )
        rewritten = version.link_targets(body, BASE)
        self.assertIn(f"[a](<{BASE}docs/a b.md>)", rewritten)
        self.assertIn("[b](//radio.example/x)", rewritten)
        self.assertIn("[c](?q=1)", rewritten)
        self.assertIn("[d](mailto:a@radio.example)", rewritten)
        self.assertIn(f"[ref]: {BASE}docs/ref.md", rewritten)
        self.assertIn("[web]: https://radio.example/", rewritten)

    def test_a_missing_section_says_what_to_do(self) -> None:
        with self.assertRaises(ValueError) as raised:
            version.notes("0.2.0", CHANGELOG)
        self.assertIn("« ## 0.2.0 »", str(raised.exception))
        self.assertIn("Publier une version", str(raised.exception))

    def test_an_empty_section_fails(self) -> None:
        with self.assertRaises(ValueError):
            version.notes("0.1.0", "## 0.1.0\n\n\n## 0.0.1\n\n- Avant.\n")

    def test_a_version_is_x_y_z(self) -> None:
        for wrong in ("0.1", "01.1.0", "0.1.0-rc.1", "v0.1.0", "stable", ""):
            with self.assertRaises(ValueError, msg=wrong):
                version.parse(wrong)


class TagsTest(unittest.TestCase):
    def test_the_first_version_takes_its_line_and_stable(self) -> None:
        self.assertEqual(version.tags("0.1.0", []), ["0.1", "stable"])

    def test_a_newer_version_takes_both(self) -> None:
        self.assertEqual(version.tags("0.2.0", ["v0.1.0", "v0.1.1"]), ["0.2", "stable"])

    def test_a_fix_of_an_older_line_leaves_stable(self) -> None:
        self.assertEqual(version.tags("0.1.2", ["v0.1.1", "v0.2.0"]), ["0.1"])

    def test_nothing_moves_back(self) -> None:
        self.assertEqual(version.tags("0.1.1", ["v0.1.2", "v0.2.0"]), [])

    def test_publishing_again_keeps_the_tags(self) -> None:
        # Un job relancé : la version est déjà parmi les publiées.
        self.assertEqual(version.tags("0.2.0", ["v0.1.0", "v0.2.0"]), ["0.2", "stable"])

    def test_numbers_not_text(self) -> None:
        self.assertEqual(version.tags("0.10.0", ["v0.9.0"]), ["0.10", "stable"])
        self.assertEqual(version.tags("0.9.1", ["v0.10.0"]), ["0.9"])

    def test_other_tags_do_not_count(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(version.tags("0.1.0", ["v0.2.0-rc.1", "0.3.0", "essai"]), ["0.1", "stable"])


class PreviousTest(unittest.TestCase):
    def test_the_previous_version_of_the_line(self) -> None:
        self.assertEqual(version.previous("0.1.2", ["v0.1.0", "v0.1.1", "v0.1.2"]), "0.1.1")
        self.assertEqual(version.previous("0.2.0", ["v0.1.0", "v0.1.1", "v0.2.0"]), "")
        self.assertEqual(version.previous("0.1.0", ["v0.1.0", "essai"]), "")

    def test_a_newer_version_in_the_history_is_refused(self) -> None:
        # Un correctif de la 0.1 posé sur un main qui a déjà la 0.2.
        with self.assertRaises(ValueError) as raised:
            version.previous("0.1.2", ["v0.1.0", "v0.1.1", "v0.2.0"])
        self.assertIn("v0.2.0", str(raised.exception))


class ImagesTest(unittest.TestCase):
    def test_the_images_that_follow_button_version(self) -> None:
        compose = """
          image: ${BUTTON_IMAGES:-ghcr.io/lazbutton}/button-radiotomate:${BUTTON_VERSION:-stable}
          image: ${BUTTON_IMAGES:-ghcr.io/lazbutton}/button-console:${BUTTON_VERSION:-stable}
          image: ${BUTTON_IMAGES:-ghcr.io/lazbutton}/button-radiotomate:${BUTTON_VERSION:-stable}
          image: getmeili/meilisearch:v1.11
          image: ghcr.io/lazbutton/button-ancienne:main
        """
        self.assertEqual(version.images(compose), ["button-console", "button-radiotomate"])


class LinesTest(unittest.TestCase):
    def test_a_line_under_a_published_version_is_refused(self) -> None:
        # Une branche ouverte avant la coupe de la 0.10.0 fusionne main : sa
        # ligne, ajoutée « à la fin de Non publié », tombe sous la 0.10.0.
        after = CHANGELOG.replace("- La première.\n", "- La première.\n- Une ligne d'une branche.\n")
        with self.assertRaises(ValueError) as raised:
            version.check_lines(CHANGELOG, after)
        self.assertIn("- Une ligne d'une branche.", str(raised.exception))

    def test_a_line_under_unreleased_and_a_fixed_typo_pass(self) -> None:
        after = CHANGELOG.replace(
            "- Une ligne pas encore publiée.\n", "- Une ligne pas encore publiée.\n- Une autre.\n"
        ).replace("- La première.", "- La toute première.")
        version.check_lines(CHANGELOG, after)

    def test_cutting_a_version_passes(self) -> None:
        after = CHANGELOG.replace("## Non publié\n\n", "## Non publié\n\n## 0.11.0\n\n")
        version.check_lines(CHANGELOG, after)

    def test_only_tagged_versions_are_published(self) -> None:
        # 0.10.0 est coupée, mais son tag n'existe pas, ou a été retiré pour
        # la reprendre : elle reçoit encore des lignes. 0.1.0 non.
        after = CHANGELOG.replace("### Corrigé\n\n", "### Corrigé\n\n- Une correction de dernière minute.\n")
        version.check_lines(CHANGELOG, after, ["v0.1.0", "v0.1.1"])
        with self.assertRaises(ValueError):
            version.check_lines(CHANGELOG, after, ["v0.1.0", "v0.10.0"])
        with self.assertRaises(ValueError):
            version.check_lines(CHANGELOG, after)


class MainTest(unittest.TestCase):
    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = version.main(list(args))
        return code, out.getvalue()

    def test_tags_and_previous_on_one_line(self) -> None:
        self.assertEqual(self.run_main("tags", "0.1.0"), (0, "0.1 stable\n"))
        self.assertEqual(self.run_main("tags", "0.1.0", "v0.2.0"), (0, "0.1\n"))
        self.assertEqual(self.run_main("avant", "0.1.1", "v0.1.0"), (0, "0.1.0\n"))
        self.assertEqual(self.run_main("avant", "0.1.0"), (0, "\n"))

    def test_errors_and_usage(self) -> None:
        self.assertEqual(self.run_main("tags", "0.1")[0], 1)
        self.assertEqual(self.run_main("avant", "0.1.1", "v0.2.0")[0], 1)
        self.assertEqual(self.run_main("notes")[0], 64)
        self.assertEqual(self.run_main("notes", "0.1.0", "--autre", "x")[0], 64)


class RepositoryTest(unittest.TestCase):
    """Les vrais fichiers : CHANGELOG.md, d'où sortent les notes de chaque
    version, et la liste des images, que version.yml et failles.yml lisent
    dans compose.yml."""

    def setUp(self) -> None:
        self.text = version.CHANGELOG.read_text(encoding="utf-8")

    def test_each_version_has_notes_newest_first(self) -> None:
        headings = [heading for heading, _ in version.sections(self.text)][1:]
        numbers = [version.heading_version(heading) for heading in headings]
        for heading, number in zip(headings, numbers):
            self.assertTrue(number or heading == "Non publié", f"Titre inattendu : ## {heading}")
        self.assertLessEqual(headings.count("Non publié"), 1)
        if "Non publié" in headings:
            self.assertEqual(headings[0], "Non publié", "« Non publié » vient en premier.")
        parsed = [version.parse(number) for number in numbers if number]
        self.assertEqual(parsed, sorted(set(parsed), reverse=True), "Des versions de la plus haute à la plus basse, une fois chacune.")
        for number in filter(None, numbers):
            version.notes(number, self.text)

    def test_no_line_twice_in_a_part(self) -> None:
        # Un conflit réglé en gardant les deux côtés peut doubler des lignes,
        # qui passeraient ensuite dans les notes d'une version. Un même
        # correctif peut, lui, figurer dans deux versions.
        for heading, lines in version.sections(self.text):
            kept, fenced = [], False
            for line in lines:
                if version.FENCE.match(line):
                    fenced = not fenced
                elif line.strip() and not fenced:
                    kept.append(line)
            twice = sorted(line[:80] for line, count in Counter(kept).items() if count > 1)
            self.assertEqual(twice, [], f"Lignes en double sous « ## {heading} »")
            glued = [line[:80] for line in kept if re.search(r"[.)]- [A-Z`«ÉÀ]", line)]
            self.assertEqual(glued, [], f"Deux lignes de liste collées sous « ## {heading} »")

    def test_the_seven_images_and_their_builds(self) -> None:
        names = version.images(version.COMPOSE.read_text(encoding="utf-8"))
        self.assertEqual(len(names), 7, names)
        built = []
        for workflow in ("engine", "console", "services"):
            text = (version.ROOT / ".github" / "workflows" / f"{workflow}.yml").read_text(encoding="utf-8")
            built += re.findall(r"for image in ([a-z ]+); do", text)[0].split()
        self.assertEqual(sorted(f"button-{image}" for image in built), names)


if __name__ == "__main__":
    unittest.main()
