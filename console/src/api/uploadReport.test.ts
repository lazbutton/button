import assert from "node:assert/strict";
import { test } from "node:test";
import { settled, uploadKey, uploadNotes, uploadsBody, type UploadFileReport } from "./uploadReport.ts";

const labelOf = (id: string) => (id === "rotation" ? "Rotation" : id === "jazz" ? "Jazz" : id);

const base: UploadFileReport = {
  dest: "jazz",
  name: "feeling good.wav",
  in_bank: true,
  id: 2,
  path: "20-archives/jazz/feeling good.flac",
  duplicates: [],
  recognized: null,
  searched: false,
};

test("un fichier pas encore dans la banque attend", () => {
  const waiting = { ...base, in_bank: false, id: null, path: null };
  assert.deepEqual(uploadNotes(waiting, true, labelOf), [{ tone: "wait", text: "En route vers la banque" }]);
  assert.equal(settled(waiting, false), false);
});

test("un doublon se signale, avec où est l'autre", () => {
  const twin = { id: 1, artist: "Nina Simone", title: "Feeling Good", path: "10-rotation/x.mp3", zone: "rotation", collection: "rotation" };
  const notes = uploadNotes({ ...base, duplicates: [twin] }, false, labelOf);
  assert.deepEqual(notes, [{ tone: "warn", text: "Doublon de Nina Simone - Feeling Good (Rotation)" }]);
  const more = uploadNotes({ ...base, duplicates: [twin, { ...twin, id: 3 }, { ...twin, id: 4 }] }, false, labelOf);
  assert.equal(more[0].text, "Doublon de Nina Simone - Feeling Good (Rotation) et 2 autres");
});

test("un titre reconnu dit ce qu'il est, comme la fiche le demande", () => {
  const recognized = { artist: "Les Marées Hautes", title: "Estuaire", level: "sûr", source: "Deezer" };
  assert.deepEqual(uploadNotes({ ...base, recognized, searched: true }, true, labelOf), [
    { tone: "found", text: "Reconnu : Les Marées Hautes, Estuaire" },
  ]);
  assert.equal(settled({ ...base, recognized, searched: true }, true), true);
});

test("dans la banque, la recherche dit où elle en est", () => {
  assert.deepEqual(uploadNotes(base, true, labelOf), [{ tone: "wait", text: "Dans la banque, recherche en cours" }]);
  assert.equal(settled(base, true), false);
  assert.deepEqual(uploadNotes({ ...base, searched: true }, true, labelOf), [
    { tone: "plain", text: "Dans la banque, pas reconnu en ligne" },
  ]);
  // La recherche éteinte : rien à attendre.
  assert.deepEqual(uploadNotes(base, false, labelOf), [{ tone: "plain", text: "Dans la banque" }]);
  assert.equal(settled(base, false), true);
});

test("une demande ne porte chaque fichier qu'une fois, cent au plus", () => {
  const files = [
    { dest: "rotation", name: "a.mp3" },
    { dest: "rotation", name: "a.mp3" },
    { dest: "jazz", name: "a.mp3" },
  ];
  assert.deepEqual(uploadsBody(files).files, [
    { dest: "rotation", name: "a.mp3" },
    { dest: "jazz", name: "a.mp3" },
  ]);
  const many = Array.from({ length: 150 }, (_, index) => ({ dest: "rotation", name: `${index}.mp3` }));
  assert.equal(uploadsBody(many).files.length, 100);
  assert.notEqual(uploadKey("a", "b c"), uploadKey("a b", "c"));
});
