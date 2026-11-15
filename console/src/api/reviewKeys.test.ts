import assert from "node:assert/strict";
import test from "node:test";
import { count, type Decided, type FicheTitle } from "./fiches.ts";
import {
  endLine,
  gestureLine,
  positionLine,
  progressText,
  queueOf,
  reviewKey,
  undoneLine,
  waitingIds,
} from "./reviewKeys.ts";

test("A, R, Z and the arrows; a field or a shortcut keeps its key", () => {
  assert.equal(reviewKey({ key: "a" }), "accept");
  assert.equal(reviewKey({ key: "A" }), "accept");
  assert.equal(reviewKey({ key: "r" }), "refuse");
  assert.equal(reviewKey({ key: "z" }), "undo");
  assert.equal(reviewKey({ key: "ArrowRight" }), "next");
  assert.equal(reviewKey({ key: "ArrowDown" }), "next");
  assert.equal(reviewKey({ key: "ArrowLeft" }), "previous");
  assert.equal(reviewKey({ key: "ArrowUp" }), "previous");
  assert.equal(reviewKey({ key: "Escape" }), null);
  assert.equal(reviewKey({ key: "x" }), null);
  // Les raccourcis du navigateur : Ctrl+R recharge, ⌘+Z défait, Alt+flèche revient.
  assert.equal(reviewKey({ key: "r", ctrlKey: true }), null);
  assert.equal(reviewKey({ key: "z", metaKey: true }), null);
  assert.equal(reviewKey({ key: "ArrowLeft", altKey: true }), null);
  // Une touche frappée dans un champ y reste.
  assert.equal(reviewKey({ key: "a" }, { tagName: "INPUT" }), null);
  assert.equal(reviewKey({ key: "a" }, { tagName: "textarea" }), null);
  assert.equal(reviewKey({ key: "a" }, { tagName: "DIV", isContentEditable: true }), null);
  assert.equal(reviewKey({ key: "a" }, { tagName: "BUTTON" }), "accept");
  // Tenue enfoncée, A n'accepte pas la suite ; une flèche, si.
  assert.equal(reviewKey({ key: "a", repeat: true }), null);
  assert.equal(reviewKey({ key: "ArrowRight", repeat: true }), "next");
});

const proposition = (id: number, state = "proposée") => ({
  id,
  field: "album",
  before: "",
  value: "Ciel",
  level: "sûr",
  why: "",
  source: "Deezer",
  state,
  error: "",
});

function title(id: number, states: string[]): FicheTitle {
  return {
    id,
    title: `Titre ${id}`,
    artist: "Orage",
    album: "",
    year: null,
    duration: 180,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    status: "trouvé",
    level: "sûr",
    reasons: [],
    source: "Deezer",
    url: "",
    propositions: states.map((state, index) => proposition(id * 10 + index, state)),
  };
}

test("the queue: the titles with something to read, once each", () => {
  assert.deepEqual(waitingIds(title(1, ["proposée", "écrite", "proposée"]).propositions), [10, 12]);
  const first = queueOf([title(1, ["proposée"]), title(2, ["refusée"]), title(3, ["proposée"])]);
  assert.deepEqual(
    first.map((one) => one.id),
    [1, 3],
  );
  assert.deepEqual(
    queueOf([title(3, ["proposée"]), title(4, ["proposée"])], first).map((one) => one.id),
    [4],
  );
});

const decided = (written: number, waiting = 0): Decided => ({
  accepted: written,
  refused: 0,
  written,
  waiting: Array.from({ length: waiting }, (_, index) => ({ id: index, label: "", code: "on_air", reason: "" })),
  failed: [],
  stale: 0,
  entry: 3,
});

test("what a screen reader hears", () => {
  assert.equal(progressText(11, 87), "12 sur 87");
  // Les milliers, séparés comme la console les écrit partout.
  assert.equal(progressText(1199, 1200), `${count(1200)} sur ${count(1200)}`);
  assert.equal(positionLine(0, 2, "Comète"), "1 sur 2 : « Comète ».");
  assert.equal(gestureLine({ kind: "accept", name: "Comète" }, decided(2)), "« Comète » accepté. 2 propositions écrites.");
  assert.equal(gestureLine({ kind: "refuse", name: "Brume" }, decided(0)), "« Brume » refusé.");
  assert.equal(undoneLine({ kind: "accept", name: "Comète" }, decided(2)), "Acceptation défaite : « Comète ». Il est de nouveau à relire.");
  assert.equal(
    undoneLine({ kind: "accept", name: "Comète" }, decided(0, 1)),
    "Acceptation défaite : « Comète ». Il passe à l'antenne : sa valeur d'avant reviendra après son passage.",
  );
  assert.equal(undoneLine({ kind: "refuse", name: "Brume" }, decided(0)), "Refus défait : « Brume ». Il est de nouveau à relire.");
  assert.equal(endLine(3, 1), "Tout est relu : 3 titres acceptés, 1 refusé.");
  assert.equal(endLine(1, 0), "Tout est relu : 1 titre accepté.");
  assert.equal(endLine(0, 0), "Tout est passé, sans geste.");
});
