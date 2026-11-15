import assert from "node:assert/strict";
import test from "node:test";
import {
  archiveAction,
  archiveLot,
  completeLine,
  emptyFieldTable,
  familiesLine,
  healthPath,
  type HealthTitle,
  incompleteLine,
  lotOf,
  MAX_LOT,
  moreLine,
  placeLine,
  renameAction,
  renameLine,
  spellingAction,
  spellingLine,
  type SpellingGroup,
  verdictLine,
} from "./bankHealth.ts";

function title(id: number, more: Partial<HealthTitle> = {}): HealthTitle {
  return {
    id,
    title: "Estuaire",
    artist: "Les Marées Hautes",
    album: "Delta",
    year: 2020,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    duration: 200,
    zone: "collections",
    collection: "nuit",
    path: `20-archives/nuit/${id}.mp3`,
    missing: [],
    ...more,
  };
}

test("the address asks for a model, and for a new count", () => {
  assert.equal(healthPath("artiste-titre"), "/media/health.json?model=artiste-titre");
  assert.equal(healthPath("titre", true), "/media/health.json?model=titre&refresh=1");
});

test("the bank in figures", () => {
  const figures = {
    titles: 8,
    complete: 7,
    families: [
      { value: "jazz", label: "Jazz", count: 5 },
      { value: "rock", label: "Rock", count: 2 },
      { value: "pop", label: "Pop", count: 1 },
      { value: "folk", label: "Folk", count: 1 },
    ],
    without_family: 0,
  };
  assert.equal(completeLine(figures), "7 sur 8 fiches complètes, 88 %");
  assert.equal(completeLine({ ...figures, titles: 0, complete: 0 }), "La banque est vide.");
  assert.equal(familiesLine(figures), "4 familles : Jazz (5), Rock (2), Pop (1)…");
  assert.equal(familiesLine({ ...figures, families: [] }), "Aucune famille encore.");
});

test("an artist written several ways, and its correction", () => {
  const group: SpellingGroup = {
    key: "lesmareeshautes",
    spellings: [
      { value: "Les Marées Hautes", count: 3 },
      { value: "les marees hautes", count: 1 },
      { value: "LES MARÉES HAUTES", count: 1 },
    ],
    suggested: "Les Marées Hautes",
    count: 5,
    titles: [],
  };
  assert.equal(spellingLine(group), "« Les Marées Hautes » s'écrit de 3 façons, sur 5 titres");
  assert.equal(spellingAction(group), "Écrire partout « Les Marées Hautes »");
});

test("a lot takes 500 titles at most", () => {
  const many = Array.from({ length: MAX_LOT + 3 }, (_, index) => index);
  assert.deepEqual(lotOf(many).left, 3);
  assert.equal(lotOf(many).taken.length, MAX_LOT);
  assert.equal(renameAction(1), "Renommer 1 fichier");
  assert.equal(renameAction(31), "Renommer 31 fichiers");
  assert.equal(renameAction(MAX_LOT + 3), "Renommer 500 fichiers");
  assert.equal(archiveAction(2), "Retirer « Archive » de 2 fiches");
});

test("« Archive » leaves, the other genres stay", () => {
  const lot = archiveLot([
    title(6, { genre: "Archive", genre_without: "" }),
    title(7, { genre: "Rock, Archive", genre_without: "Rock" }),
  ]);
  assert.deepEqual(lot.titles, [
    { id: 6, values: { genre: "" }, expected: { genre: "Archive" } },
    { id: 7, values: { genre: "Rock" }, expected: { genre: "Rock, Archive" } },
  ]);
});

test("an empty field opens the table ranged on it, when it ranges", () => {
  assert.deepEqual(emptyFieldTable("album"), { ranger: "album", groupe: "" });
  assert.deepEqual(emptyFieldTable("famille"), { ranger: "famille", groupe: "" });
  assert.equal(emptyFieldTable("year"), null);
  assert.equal(incompleteLine("album", 12), "12 fiches sans album");
  assert.equal(incompleteLine("year", 1), "1 fiche sans année");
});

test("the lines that name a title", () => {
  assert.equal(
    renameLine(title(3, { path: "20-archives/nuit/03_un.mp3", to: "Ada - Un.mp3" })),
    "03_un.mp3 → Ada - Un.mp3",
  );
  assert.equal(placeLine(title(3, { path: "20-archives/nuit/a.mp3" })), "nuit · a.mp3");
  assert.equal(
    placeLine(title(3, { path: "10-rotation/a.mp3", zone: "rotation", collection: "rotation" })),
    "Rotation · a.mp3",
  );
  assert.equal(moreLine(25, 20, ["fichier", "fichiers"]), "et 5 fichiers de plus");
  assert.equal(moreLine(1 + 20, 20, ["fichier", "fichiers"]), "et 1 fichier de plus");
  assert.equal(moreLine(20, 20, ["fichier", "fichiers"]), "");
});

test("la part des « oui » parmi les verdicts connus, seulement le verdict allumé (FON-80)", () => {
  const figures = { titles: 10, complete: 5, families: [], without_family: 10 };
  assert.equal(verdictLine(figures), null);
  assert.equal(
    verdictLine({ ...figures, verdicts: { oui: 0, mixte: 0, non: 0 } }),
    "Aucun verdict connu pour l'instant.",
  );
  assert.equal(
    verdictLine({ ...figures, verdicts: { oui: 2, mixte: 1, non: 1 } }),
    "2 « oui » sur 4 verdicts connus, 50 % (1 mixte, 1 « non »)",
  );
  assert.equal(
    verdictLine({ ...figures, verdicts: { oui: 1, mixte: 0, non: 0 } }),
    "1 « oui » sur 1 verdict connu, 100 %",
  );
});
