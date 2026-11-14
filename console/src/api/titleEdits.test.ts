import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import type { BankTitle } from "./bankTitles.ts";
import {
  FAMILIES,
  batchLot,
  formOf,
  issueLines,
  savedMessage,
  selectionLines,
  sheetLot,
  undoneMessage,
  withoutTitles,
  yearProblem,
  type EditOutcome,
} from "./titleEdits.ts";

const RULES = fileURLToPath(new URL("../../../engine/radiotomate/fiches/rules.py", import.meta.url));

function title(id: number, change: Partial<BankTitle> = {}): BankTitle {
  return {
    id,
    title: "Comète",
    artist: "Orage",
    album: "Ciel",
    year: 2015,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    duration: 200,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
    ...change,
  };
}

function outcome(change: Partial<EditOutcome> = {}): EditOutcome {
  return {
    dry_run: false,
    entry: 3,
    written: 0,
    waiting: [],
    kept: [],
    refused: [],
    unchanged: 0,
    selections: [],
    ...change,
  };
}

const issue = (id: number, reason = "Il est à l'antenne : sa fiche s'écrira quand il sera passé.") => ({
  id,
  label: `Orage – Titre ${id}`,
  code: "on_air",
  reason,
});

test("les familles de la console sont celles du moteur", () => {
  const rules = readFileSync(RULES, "utf8");
  const engine = [...rules.matchAll(/Family\(\s*"([^"]+)",\s*"([^"]+)"/g)].map(([, name, label]) => ({ name, label }));
  assert.equal(engine.length, 14);
  assert.deepEqual(FAMILIES, engine);
});

test("une fiche se lit en texte, une année vide plutôt que 0", () => {
  assert.equal(formOf(title(1)).year, "2015");
  assert.equal(formOf(title(1, { year: null })).year, "");
  assert.equal(formOf(title(1, { year: 0 })).year, "");
});

test("une année s'écrit en quatre chiffres, ou se vide", () => {
  assert.equal(yearProblem(""), "");
  assert.equal(yearProblem(" 2019 "), "");
  assert.match(yearProblem("87"), /quatre chiffres/);
  assert.match(yearProblem("deux mille"), /quatre chiffres/);
  assert.match(yearProblem("0999"), /quatre chiffres/);
});

test("la fiche du panneau n'envoie que ses champs changés, avec ce qu'elle montrait", () => {
  const entry = title(7);
  assert.equal(sheetLot(entry, formOf(entry)), null);
  // des espaces de plus ne sont pas un changement
  assert.equal(sheetLot(entry, { ...formOf(entry), album: "  Ciel " }), null);

  const lot = sheetLot(entry, { ...formOf(entry), album: " Été ", year: "", famille: "soul-funk" });
  assert.deepEqual(lot, {
    titles: [
      {
        id: 7,
        values: { album: "Été", year: "", famille: "soul-funk" },
        expected: { album: "Ciel", year: "2015", famille: "jazz" },
      },
    ],
  });
});

test("un champ coché prend la même valeur pour tous, un champ décoché garde la sienne", () => {
  const lot = batchLot([title(1), title(2, { album: "", year: null })], { album: "Ciel", famille: "" });
  assert.deepEqual(lot.titles, [
    { id: 1, values: { album: "Ciel", famille: "" }, expected: { album: "Ciel", famille: "jazz" } },
    { id: 2, values: { album: "Ciel", famille: "" }, expected: { album: "", famille: "jazz" } },
  ]);
  assert.deepEqual(
    withoutTitles(lot, [1]).titles.map((entry) => entry.id),
    [2],
  );
});

test("l'essai nomme les sélections qui gagnent ou perdent des titres", () => {
  assert.deepEqual(
    selectionLines([
      { id: 1, name: "Jazz", gained: 0, lost: 12 },
      { id: 2, name: "Soul", gained: 1, lost: 0 },
      { id: 3, name: "Nuit", gained: 3, lost: 2 },
    ]),
    ["« Jazz » perd 12 titres.", "« Soul » gagne 1 titre.", "« Nuit » gagne 3 titres et en perd 2."],
  );
});

test("les titres en cause se disent cinq au plus", () => {
  const lines = issueLines([1, 2, 3, 4, 5, 6, 7].map((id) => issue(id)));
  assert.equal(lines.length, 6);
  assert.equal(lines[0], "Orage – Titre 1 : Il est à l'antenne : sa fiche s'écrira quand il sera passé.");
  assert.equal(lines[5], "Et 2 autres titres.");
  assert.equal(issueLines([1, 2, 3, 4, 5, 6].map((id) => issue(id))).at(-1), "Et un autre titre.");
});

test("après l'écriture, la console dit ce qui est fait et ce qui attend", () => {
  assert.deepEqual(savedMessage(outcome({ written: 1 }), "Comète"), {
    text: "Fiche de « Comète » corrigée.",
    tone: "success",
  });
  assert.deepEqual(savedMessage(outcome({ waiting: [issue(1)] }), "Comète"), {
    text: "La fiche de « Comète » s'écrira quand le titre aura fini de passer à l'antenne.",
    tone: "info",
  });
  assert.deepEqual(savedMessage(outcome({ written: 38, waiting: [issue(1), issue(2)] })), {
    text: "38 fiches corrigées. 2 autres s'écriront quand leurs titres auront fini de passer à l'antenne.",
    tone: "success",
  });
  assert.deepEqual(savedMessage(outcome({ written: 1, waiting: [issue(1)] })), {
    text: "1 fiche corrigée. Une autre s'écrira quand son titre aura fini de passer à l'antenne.",
    tone: "success",
  });
  assert.deepEqual(savedMessage(outcome({ waiting: [issue(1), issue(2)] })), {
    text: "2 fiches s'écriront quand leurs titres auront fini de passer à l'antenne.",
    tone: "info",
  });
  assert.equal(savedMessage(outcome({ unchanged: 3 })).tone, "info");
});

test("après « Revenir », la console dit ce qui a repris sa valeur et ce qui l'a gardée", () => {
  assert.deepEqual(undoneMessage(outcome({ written: 3 })), {
    text: "3 fiches ont repris leurs valeurs d'avant.",
    tone: "success",
  });
  assert.deepEqual(undoneMessage(outcome({ written: 1, kept: [issue(2)] })), {
    text: "1 fiche a repris sa valeur d'avant. Un titre a gardé la sienne : sa fiche a changé depuis.",
    tone: "info",
  });
  assert.deepEqual(undoneMessage(outcome({ written: 0 })), {
    text: "Rien n'était encore écrit : le lot ne s'écrira pas.",
    tone: "success",
  });
});
