import assert from "node:assert/strict";
import test from "node:test";
import { skippedFiles, skippedName, skippedNotice, skippedSplit } from "./cartRefusals.ts";
import type { SkippedFile } from "./types.ts";

const FOLDER = "Bacs/12-Nouveautes";
const faux: SkippedFile = { path: "faux.mp3", reason: "ce n'est pas un fichier audio" };
const ogg: SkippedFile = { path: "Album/b.ogg", reason: "durée illisible" };
const dossier: SkippedFile = {
  path: ".",
  reason: "plus de 2000 fichiers audio : le bac ne prend plus rien de son dossier",
};

test("an older engine gives no skipped files, and a relay follows no folder", () => {
  assert.deepEqual(skippedFiles({ mode: "playlist" }), []);
  assert.deepEqual(skippedFiles({ mode: "playlist", skipped_files: [faux] }), [faux]);
  assert.deepEqual(skippedFiles({ mode: "relay", skipped_files: [faux] }), []);
  // Une entrée mal formée ne casse pas l'écran : elle ne se montre pas.
  const odd = [faux, { path: "x.mp3" }, null, { path: 3, reason: "x" }] as unknown as SkippedFile[];
  assert.deepEqual(skippedFiles({ mode: "random", skipped_files: odd }), [faux]);
});

test("the notice counts the files, and says what to do with them", () => {
  assert.equal(skippedNotice([], FOLDER), null);
  assert.deepEqual(skippedNotice([faux], FOLDER), {
    title: "1 fichier n'est pas entré dans le bac",
    help: "Remplace-le dans Bacs/12-Nouveautes par un son que l'automate lit, ou retire-le.",
  });
  assert.deepEqual(skippedNotice([faux, ogg], FOLDER), {
    title: "2 fichiers ne sont pas entrés dans le bac",
    help: "Remplace-les dans Bacs/12-Nouveautes par des sons que l'automate lit, ou retire-les.",
  });
});

test("a folder over the cap is named by the station folder", () => {
  assert.deepEqual(skippedNotice([dossier], FOLDER), {
    title: "Le dossier du bac a trop de fichiers",
    help: "Déplace une partie des fichiers de Bacs/12-Nouveautes ailleurs : sous 2000, le bac reprend ceux qui y arrivent.",
  });
  assert.equal(skippedName(dossier, FOLDER), FOLDER);
  assert.equal(skippedName(ogg, FOLDER), "Album/b.ogg");
});

test("past four files, the rest waits to be asked for", () => {
  const files = Array.from({ length: 6 }, (_, index) => ({ path: `${index}.mp3`, reason: "durée illisible" }));
  assert.deepEqual(skippedSplit(files.slice(0, 4)), { shown: files.slice(0, 4), more: [] });
  assert.deepEqual(skippedSplit(files.slice(0, 5)), { shown: files.slice(0, 3), more: files.slice(3, 5) });
  assert.deepEqual(skippedSplit(files), { shown: files.slice(0, 3), more: files.slice(3) });
});
