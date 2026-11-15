import assert from "node:assert/strict";
import test from "node:test";
import {
  archiveAction,
  archiveLot,
  healthPath,
  type HealthTitle,
  lotOf,
  MAX_LOT,
  moreLine,
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

test("a lot takes 500 titles at most", () => {
  const many = Array.from({ length: MAX_LOT + 3 }, (_, index) => index);
  assert.deepEqual(lotOf(many).left, 3);
  assert.equal(lotOf(many).taken.length, MAX_LOT);
  assert.equal(archiveAction(2), "Retirer « Archive » de 2 fiches");
  assert.equal(archiveAction(MAX_LOT + 3), "Retirer « Archive » de 500 fiches");
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

test("a list cut short says how many more", () => {
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
