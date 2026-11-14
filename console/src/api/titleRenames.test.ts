import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_CHOICE,
  RENAME_MODELS,
  keptReasons,
  mergeAnswers,
  parseChoice,
  previewSummary,
  renameCounts,
  renameLabel,
  renamedMessage,
  sentence,
  splitPath,
  unrenamedMessage,
  type RenameTitle,
} from "./titleRenames.ts";

function title(id: number, state: RenameTitle["state"], reason = "", to: string | null = null): RenameTitle {
  return { id, label: `Titre ${id}`, path: `20-archives/jazz/${id}.mp3`, to, state, reason };
}

test("the three models of the fiche, as the engine names them", () => {
  assert.deepEqual(
    RENAME_MODELS.map((model) => model.value),
    ["artiste-titre", "artiste-album-titre", "titre"],
  );
});

test("the choice kept by the browser falls back on the default", () => {
  assert.deepEqual(parseChoice('{"model": "titre", "byArtist": true}'), { model: "titre", byArtist: true });
  assert.deepEqual(parseChoice('{"model": "autre"}'), DEFAULT_CHOICE);
  assert.deepEqual(parseChoice("pas du json"), DEFAULT_CHOICE);
  assert.deepEqual(parseChoice(null), DEFAULT_CHOICE);
});

test("a path below the bank, cut into its folder and its name", () => {
  assert.deepEqual(splitPath("20-archives/jazz/Ada/Ada - Un.mp3"), { folder: "20-archives/jazz/Ada", name: "Ada - Un.mp3" });
  assert.deepEqual(splitPath("a.mp3"), { folder: "", name: "a.mp3" });
});

test("the preview counts what changes, what is already so, and what keeps its name", () => {
  const titles = [
    title(1, "rename", "", "x"),
    title(2, "rename", "", "y"),
    title(3, "same", "Il porte déjà ce nom."),
    title(4, "taken", "Ce nom est déjà pris : rien n'est remplacé."),
    title(5, "busy", "À l'antenne en ce moment."),
  ];
  assert.deepEqual(renameCounts(titles), { rename: 2, same: 1, kept: 2 });
  assert.equal(
    previewSummary(titles),
    "2 fichiers prendront le nom de leur fiche. 1 fichier le porte déjà. 2 fichiers gardent leur nom, comme dit ci-dessous.",
  );
  assert.equal(previewSummary([title(1, "same")]), "Aucun fichier ne change de nom. 1 fichier le porte déjà.");
  assert.equal(renameLabel(1), "Renommer 1 fichier");
  assert.equal(renameLabel(300), "Renommer 300 fichiers");
});

test("a reason of the engine reads as a sentence, once", () => {
  assert.equal(sentence("déjà là"), "Déjà là.");
  assert.equal(sentence("Il porte déjà ce nom."), "Il porte déjà ce nom.");
  assert.deepEqual(keptReasons([title(1, "failed", "déjà là"), title(2, "failed", "déjà là"), title(3, "renamed")]), ["Déjà là."]);
});

test("after the renaming, the console says what was done and what was not", () => {
  assert.deepEqual(renamedMessage([title(1, "renamed"), title(2, "renamed")]), {
    text: "2 fichiers renommés.",
    tone: "success",
  });
  assert.deepEqual(renamedMessage([title(1, "renamed"), title(2, "failed", "en file pour l'antenne")]), {
    text: "1 fichier renommé. 1 fichier garde son nom. En file pour l'antenne.",
    tone: "error",
  });
  assert.equal(renamedMessage([title(1, "same")]).tone, "info");
});

test("a lot the engine had no time for comes back in parts, each its own lot", () => {
  const merged = mergeAnswers([
    { dry_run: false, titles: [title(1, "renamed"), title(2, "left")], entry: 7, left: [2] },
    { dry_run: false, titles: [title(2, "renamed")], entry: 8, left: [] },
  ]);
  assert.deepEqual(
    merged.titles.map((item) => [item.id, item.state]),
    [
      [1, "renamed"],
      [2, "renamed"],
    ],
  );
  assert.deepEqual(merged.entries, [7, 8]);
});

test("after « Annuler », the console says which files took their names back", () => {
  assert.deepEqual(unrenamedMessage({ written: 2, kept: [] }), {
    text: "2 fichiers ont repris leur nom d'avant.",
    tone: "success",
  });
  assert.equal(
    unrenamedMessage({ written: 1, kept: [{}] }).text,
    "1 fichier a repris son nom d'avant. Un fichier garde le sien : il a changé de place depuis, ou il passe à l'antenne.",
  );
});
