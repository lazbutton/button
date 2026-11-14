import assert from "node:assert/strict";
import test from "node:test";
import { cleanTag, parseTags, tagProblem, tagSuggestions, tagsOnTitles, taggedMessage, withTag } from "./stationTags.ts";
import type { EditOutcome } from "./titleEdits.ts";

test("a tag is written as the engine writes it", () => {
  assert.equal(cleanTag("  Fin   de SOIRÉE "), "fin de soirée");
  assert.equal(cleanTag("été"), "été");
  assert.equal(tagProblem("nuit"), "");
  assert.equal(tagProblem("   "), "Une étiquette a au moins une lettre.");
  for (const refused of ["a|b", "nuit,", 'dit "oui"', "a\\b"]) {
    assert.equal(tagProblem(refused), "Une étiquette ne prend ni barre droite, ni virgule, ni guillemet : ils couperaient une sélection de titres.", refused);
  }
  assert.equal(tagProblem("x".repeat(40)), "");
  assert.equal(tagProblem("x".repeat(41)), "Une étiquette tient en 40 signes.");
});

test("a tag added once, cleaned, or refused with its reason", () => {
  assert.deepEqual(withTag([], " Nuit "), { tags: ["nuit"], problem: "" });
  assert.deepEqual(withTag(["nuit"], "NUIT"), { tags: ["nuit"], problem: "" });
  assert.deepEqual(withTag(["nuit"], "a,b"), {
    tags: ["nuit"],
    problem: "Une étiquette ne prend ni barre droite, ni virgule, ni guillemet : ils couperaient une sélection de titres.",
  });
  assert.deepEqual(parseTags("|instrumental|nuit|"), ["instrumental", "nuit"]);
  assert.deepEqual(parseTags(""), []);
});

test("the tags of the titles chosen, each with its count", () => {
  const titles = [{ etiquettes: ["nuit", "instrumental"] }, { etiquettes: ["nuit"] }, { etiquettes: [] }];
  assert.deepEqual(tagsOnTitles(titles), [
    { value: "instrumental", label: "instrumental", count: 1 },
    { value: "nuit", label: "nuit", count: 2 },
  ]);
});

test("the station's tags proposed: what is typed, the most worn first", () => {
  const facets = [
    { value: "minuit", label: "minuit", count: 2 },
    { value: "nuit", label: "nuit", count: 9 },
    { value: "été", label: "été", count: 4 },
    { value: "", label: "", count: 30 },
  ];
  assert.deepEqual(
    tagSuggestions(facets, "", []).map((facet) => facet.value),
    ["nuit", "été", "minuit"],
  );
  assert.deepEqual(
    tagSuggestions(facets, "NUI", ["nuit"]).map((facet) => facet.value),
    ["minuit"],
  );
  assert.deepEqual(
    tagSuggestions(facets, "ete", []).map((facet) => facet.value),
    ["été"],
  );
  assert.equal(tagSuggestions(facets, "", [], 1).length, 1);
});

function outcome(written: number): EditOutcome {
  return { dry_run: false, entry: 3, written, waiting: [], kept: [], refused: [], unchanged: 0, selections: [] };
}

test("what the console says once the tags are written", () => {
  assert.deepEqual(taggedMessage(outcome(3), ["nuit"], []), {
    text: "Étiquette « nuit » posée sur 3 titres.",
    tone: "success",
  });
  assert.deepEqual(taggedMessage(outcome(1), [], ["nuit"]), {
    text: "Étiquette « nuit » retirée de 1 titre.",
    tone: "success",
  });
  assert.deepEqual(taggedMessage(outcome(2), ["nuit", "calme"], ["jour"]), {
    text: "Étiquettes changées sur 2 titres : « nuit » et « calme » posées, « jour » retirée.",
    tone: "success",
  });
  assert.equal(taggedMessage(outcome(0), ["nuit"], []).tone, "info");
});
