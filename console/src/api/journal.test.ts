import assert from "node:assert/strict";
import test from "node:test";
import {
  changeField,
  changeValue,
  entryByline,
  entryNotes,
  entryTitle,
  journalQuery,
  undoQuestion,
  type JournalCounts,
} from "./journal.ts";

const counts = (change: Partial<JournalCounts> = {}): JournalCounts => ({
  done: 0,
  waiting: 0,
  kept: 0,
  cancelled: 0,
  failed: 0,
  pending: 0,
  ...change,
});

test("les filtres de la page vont dans l'adresse de la route", () => {
  assert.equal(journalQuery({ gesture: "", username: "" }), "");
  assert.equal(journalQuery({ gesture: "edit", username: "" }), "?gesture=edit");
  assert.equal(journalQuery({ gesture: "", username: "anne marie" }, 42), "?username=anne+marie&before=42");
});

test("un lot se dit par son geste, son nombre de titres et ses champs", () => {
  assert.equal(
    entryTitle({ gesture_label: "Correction", titles: 38, fields: ["album", "year"] }),
    "Correction de 38 titres : album et année",
  );
  assert.equal(
    entryTitle({ gesture_label: "Correction", titles: 1, fields: ["famille", "genre", "title"] }),
    "Correction de 1 titre : famille, genre et titre",
  );
  assert.equal(entryTitle({ gesture_label: "Annulation", titles: 0, fields: [] }), "Annulation de 0 titres");
});

test("qui, et quand, à l'heure de Paris", () => {
  const now = new Date("2026-11-14T15:00:00+01:00");
  assert.equal(entryByline({ username: "anne", created: "2026-11-14T14:02+01:00" }, now), "par anne, aujourd’hui à 14:02");
  assert.equal(entryByline({ username: "anne", created: "2026-11-13T09:30+01:00" }, now), "par anne, hier à 09:30");
});

test("ce qu'un lot n'a pas encore fait, ou pas fait", () => {
  assert.deepEqual(entryNotes(counts({ done: 3 })), []);
  assert.deepEqual(entryNotes(counts({ waiting: 1, kept: 2, cancelled: 1, failed: 3 })), [
    "1 titre en attente de la fin d'un passage à l'antenne",
    "2 titres ont gardé leur valeur",
    "1 titre jamais écrit",
    "3 titres en échec",
  ]);
});

test("l'annulation dit ce qu'elle défera", () => {
  assert.equal(
    undoQuestion({ titles: 38, counts: counts({ done: 38 }) }),
    "Les 38 titres reprennent leurs valeurs d'avant, sauf celles qui ont changé depuis.",
  );
  assert.equal(
    undoQuestion({ titles: 1, counts: counts({ waiting: 1 }) }),
    "Le titre reprend sa valeur d'avant, sauf si elle a changé depuis. Ce qui attend encore ne s'écrira pas.",
  );
});

test("une valeur vide se dit vide, un champ par son nom", () => {
  assert.equal(changeValue(""), "vide");
  assert.equal(changeValue(0), "vide");
  assert.equal(changeValue(null), "vide");
  assert.equal(changeValue(2019), "2019");
  assert.equal(changeValue("|instrumental|nuit|", "etiquettes"), "instrumental, nuit");
  assert.equal(changeValue("", "etiquettes"), "vide");
  assert.equal(changeField("etiquettes"), "Étiquettes");
  assert.equal(changeField("year"), "Année");
  assert.equal(changeField("famille"), "Famille");
  assert.equal(changeField("path"), "Fichier");
  assert.equal(changeField("isrc"), "ISRC");
});

test("a gesture on the carts says its name, without its fields", () => {
  assert.equal(entryTitle({ gesture_label: "Ordre d'un bac", titles: 5, fields: ["rank"] }), "Ordre d'un bac de 5 titres");
  assert.equal(entryTitle({ gesture_label: "Copie dans un bac", titles: 1, fields: ["cart"] }), "Copie dans un bac de 1 titre");
});
