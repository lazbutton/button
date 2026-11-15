import assert from "node:assert/strict";
import test from "node:test";
import {
  type Arrival,
  type Arrivals,
  arrivalsLine,
  arrivalsPath,
  duplicateLine,
  nameLine,
  propositionLine,
  tidiedMessage,
  tidyAllAction,
  tidyLot,
  tidyPlan,
} from "./bankArrivals.ts";

function arrival(id: number, more: Partial<Arrival> = {}): Arrival {
  return {
    id,
    title: "Estuaire",
    artist: "Les Marées Hautes",
    album: "",
    year: null,
    genre: "",
    famille: "",
    famille_label: "",
    duration: 200,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
    added: "2026-11-15T10:00+01:00",
    searched: true,
    status: "trouvé",
    level: "sûr",
    propositions: [],
    sure: [],
    review: false,
    to: null,
    ready: false,
    duplicates: [],
    ...more,
  };
}

const empty = { written: 0, waiting: [], failed: [], stale: 0 };

test("the address asks for a model", () => {
  assert.equal(arrivalsPath("artiste-titre"), "/media/arrivals.json?model=artiste-titre");
});

test("the head of the view says what waits", () => {
  const payload: Arrivals = {
    days: 30,
    model: "titre",
    total: 12,
    ready: 8,
    review: 1,
    waiting: 3,
    duplicates: 1,
    titles: [],
  };
  assert.equal(
    arrivalsLine(payload),
    "12 titres arrivés en 30 jours, 8 prêts à ranger, 1 à relire, 3 pas encore cherchés.",
  );
  assert.equal(arrivalsLine({ ...payload, total: 0 }), "Aucun titre arrivé en 30 jours.");
});

test("« Ranger » takes the sure propositions and the names of the ready titles", () => {
  const lot = tidyLot([
    arrival(1, {
      ready: true,
      sure: [11, 12],
      to: "Les Marées Hautes - Estuaire.mp3",
    }),
    arrival(2, { ready: true, sure: [21] }),
    arrival(3, { ready: true, to: "Ada - Un.mp3" }),
    arrival(4, { review: true, sure: [41], to: "x.mp3" }),
  ]);
  assert.deepEqual(lot, {
    propositions: [11, 12, 21],
    renamed: [1, 3],
    titles: 3,
  });
  assert.equal(
    tidyPlan(lot),
    "3 propositions sûres acceptées, 2 fichiers renommés. Chaque geste se note au journal, et « Annuler » le défait.",
  );
  assert.equal(tidyAllAction(3), "Ranger les 3 sûrs");
  assert.equal(tidyAllAction(1), "Ranger le titre sûr");
});

test("the lines of an arrival", () => {
  assert.equal(
    propositionLine({
      field: "artist",
      before: "les marees hautes",
      value: "Les Marées Hautes",
    }),
    "Artiste : les marees hautes → Les Marées Hautes",
  );
  assert.equal(propositionLine({ field: "year", before: "", value: "2019" }), "Année : vide → 2019");
  assert.equal(
    nameLine({
      path: "10-rotation/new1.mp3",
      to: "Les Marées Hautes - Estuaire.mp3",
    }),
    "new1.mp3 → Les Marées Hautes - Estuaire.mp3",
  );
  assert.equal(nameLine({ path: "10-rotation/a.mp3", to: null }), "a.mp3");
  assert.equal(
    duplicateLine([
      {
        id: 3,
        title: "Avant",
        artist: "Ada",
        duration: 181,
        zone: "collections",
        collection: "nuit",
        path: "20-archives/nuit/avant.mp3",
      },
    ]),
    "Doublon possible : nuit · avant.mp3",
  );
});

test("what « Ranger » did", () => {
  assert.deepEqual(tidiedMessage(3, { ...empty, written: 5 }, 2, 0), {
    text: "3 titres rangés : 5 valeurs écrites, 2 fichiers renommés.",
    tone: "success",
  });
  assert.deepEqual(tidiedMessage(1, { ...empty, waiting: [{ id: 1, label: "", code: "", reason: "" }] }, 0, 1), {
    text: "1 titre rangé : rien n'a changé. 1 valeur s'écrira après le passage à l'antenne ; 1 fichier garde son nom.",
    tone: "error",
  });
});
