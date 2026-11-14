import assert from "node:assert/strict";
import test from "node:test";
import type { BankTitle } from "./bankTitles.ts";
import { GRID_FIELDS, cellLot, cellName, moveOf, nextCell, pasteLot, pasteQuestion } from "./titleGrid.ts";

function title(id: number, change: Partial<BankTitle> = {}): BankTitle {
  return {
    id,
    title: `Titre ${id}`,
    artist: "Orage",
    album: "",
    year: null,
    genre: "Jazz",
    famille: "",
    famille_label: "",
    duration: 200,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
    ...change,
  };
}

test("les colonnes qui s'ouvrent, et le nom d'une cellule", () => {
  assert.deepEqual(GRID_FIELDS, ["artist", "album", "famille", "genre", "year"]);
  assert.equal(cellName("album", "Comète"), "Album de « Comète »");
});

test("les flèches et Tab passent d'une cellule à l'autre, et s'arrêtent au bord", () => {
  assert.equal(moveOf("Tab", false), "next");
  assert.equal(moveOf("Tab", true), "previous");
  assert.equal(moveOf("Enter", false), null);
  const at = { row: 1, column: 4 };
  assert.deepEqual(nextCell(at, "next", 3, 5), { row: 2, column: 0 });
  assert.deepEqual(nextCell({ row: 1, column: 0 }, "previous", 3, 5), { row: 0, column: 4 });
  assert.deepEqual(nextCell(at, "up", 3, 5), { row: 0, column: 4 });
  assert.equal(nextCell(at, "right", 3, 5), null);
  assert.equal(nextCell({ row: 2, column: 4 }, "next", 3, 5), null);
  assert.equal(nextCell({ row: 0, column: 0 }, "up", 3, 5), null);
});

test("une cellule enregistrée n'envoie que son champ, avec ce qu'elle montrait", () => {
  assert.equal(cellLot(title(1, { album: "Ciel" }), "album", " Ciel "), null);
  assert.deepEqual(cellLot(title(1), "album", "Ciel "), {
    titles: [{ id: 1, values: { album: "Ciel" }, expected: { album: "" } }],
  });
  assert.deepEqual(cellLot(title(2, { year: 2019 }), "year", ""), {
    titles: [{ id: 2, values: { year: "" }, expected: { year: "2019" } }],
  });
});

test("un collage écrit une seule valeur sur la colonne des titres sélectionnés", () => {
  const titles = Array.from({ length: 30 }, (_, index) => title(index + 1));
  const pasted = pasteLot(titles, "album", "Ciel\n");
  assert.ok("lot" in pasted);
  assert.equal(pasted.value, "Ciel");
  assert.equal(pasted.lot.titles.length, 30);
  assert.deepEqual(pasted.lot.titles[0], { id: 1, values: { album: "Ciel" }, expected: { album: "" } });

  assert.match((pasteLot(titles, "album", "Ciel\nNuages") as { problem: string }).problem, /une seule valeur/);
  assert.match((pasteLot(titles, "year", "87") as { problem: string }).problem, /quatre chiffres/);
  assert.match((pasteLot(titles, "famille", "jazz") as { problem: string }).problem, /dans sa liste/);
});

test("la question avant d'écrire un collage", () => {
  assert.equal(pasteQuestion("album", "Ciel", 30), "Écrire « Ciel » dans l'album de 30 titres ?");
  assert.equal(pasteQuestion("genre", "Soul", 1), "Écrire « Soul » dans le genre de 1 titre ?");
  assert.equal(pasteQuestion("year", "", 2), "Vider l'année de 2 titres ?");
});
