import assert from "node:assert/strict";
import test from "node:test";
import {
  clockTints,
  clockWeekUsage,
  copyName,
  copySteps,
  cutsSummary,
  daySetLabel,
  defaultSource,
  engineErrorText,
  hhmm,
  minuteMark,
  nameTaken,
  nextRun,
  parseHhmm,
  redundantSlotIds,
  runAt,
  spanLabel,
  starterMotif,
  stepsSummary,
  weekRuns,
} from "./programmationView.ts";
import type { ClockPosition, Slot } from "./types.ts";

const slot = (id: number, day: number, minute: number, clockId: number, clock: string): Slot => ({
  id,
  day_of_week: day,
  minute,
  title: clock,
  color: "#7a9e6a",
  clock_id: clockId,
  clock,
});

const step = (kind: ClockPosition["kind"], extra: Partial<ClockPosition> = {}): ClockPosition => ({
  kind,
  when: "sequential",
  cart: null,
  category: null,
  fallback_cart: null,
  ...extra,
});

test("times read like a programme grid", () => {
  assert.equal(hhmm(0), "00:00");
  assert.equal(hhmm(450), "07:30");
  assert.equal(hhmm(1440), "24:00");
  assert.equal(minuteMark(5), ":05");
  assert.equal(parseHhmm("7:30"), 450);
  assert.equal(parseHhmm("24:00"), 1440);
  assert.equal(parseHhmm("24:30"), null);
  assert.equal(parseHhmm("midi"), null);
  assert.equal(spanLabel(45), "45 min");
  assert.equal(spanLabel(420), "7 h");
  assert.equal(spanLabel(185), "3 h 05");
});

test("a set of days says itself shortly", () => {
  assert.equal(daySetLabel([0, 1, 2, 3, 4, 5, 6]), "Tous les jours");
  assert.equal(daySetLabel([4, 0, 1, 2, 3]), "Lun–Ven");
  assert.equal(daySetLabel([5, 6]), "Sam, Dim");
  assert.equal(daySetLabel([0, 2, 4]), "Lun, Mer, Ven");
  assert.equal(daySetLabel([0, 1, 2, 5]), "Lun–Mer, Sam");
  assert.equal(daySetLabel([]), "");
});

test("the week reads as runs, and repeated changes merge", () => {
  const slots = [
    slot(1, 0, 0, 4, "Nuit nappe"),
    slot(2, 0, 420, 3, "Jour habillé"),
    slot(3, 0, 600, 3, "Jour habillé"),
    slot(4, 1, 0, 4, "Nuit nappe"),
  ];
  const runs = weekRuns(slots);
  assert.deepEqual(
    runs.map((run) => [run.day, run.start, run.end, run.clockName, run.slots.map((row) => row.id)]),
    [
      [0, 0, 420, "Nuit nappe", [1]],
      [0, 420, 1440, "Jour habillé", [2, 3]],
      [1, 0, 1440, "Nuit nappe", [4]],
    ],
  );
  assert.deepEqual(redundantSlotIds(slots), [3]);
  assert.equal(runAt(runs, 0, 500)?.clockName, "Jour habillé");
  assert.equal(runAt(runs, 2, 500), null);
  assert.equal(nextRun(runs, 0, 500)?.day, 1);
  assert.equal(nextRun(runs, 1, 30)?.day, 0);
});

test("an heure type knows where it plays", () => {
  const slots = [0, 1, 2, 3, 4].flatMap((day) => [
    slot(day * 2 + 1, day, 0, 4, "Nuit"),
    slot(day * 2 + 2, day, 420, 3, "Jour"),
  ]);
  slots.push(slot(20, 5, 0, 4, "Nuit"), slot(21, 6, 0, 4, "Nuit"));
  assert.deepEqual(clockWeekUsage(slots, 3), ["Lun–Ven 07:00 → 24:00"]);
  assert.deepEqual(clockWeekUsage(slots, 4), ["Lun–Ven 00:00 → 07:00", "Sam, Dim 00:00 → 24:00"]);
  assert.deepEqual(clockWeekUsage(slots, 9), []);
});

test("names, copies and summaries", () => {
  assert.equal(nameTaken(" jour HABILLÉ ", ["Jour habillé"]), true);
  assert.equal(nameTaken("", ["Jour habillé"]), false);
  assert.equal(copyName("Jour", ["Jour", "Jour (copie)"]), "Jour (copie 2)");
  assert.deepEqual(copySteps([step("jingle", { id: 7, cart: "Jingles" })]), [step("jingle", { cart: "Jingles" })]);
  assert.equal(
    stepsSummary({ motif: [step("jingle"), step("musique"), step("musique"), step("musique"), step("pub")] }),
    "Jingle → Titres ×3 → Pub",
  );
  assert.equal(
    cutsSummary({
      anchors: [step("pub", { when: "anchored", minute: 40 }), step("jingle", { when: "anchored", minute: 0 })],
    }),
    ":00 :40",
  );
  assert.equal(cutsSummary({ anchors: [] }), "");
});

test("tints stay put and the engine speaks French", () => {
  const tints = clockTints([{ id: 9 }, { id: 2 }]);
  assert.equal(tints.get(2), "blue");
  assert.equal(tints.get(9), "amber");
  assert.equal(engineErrorText("Clock Jour already exists", "x"), "Une heure type porte déjà ce nom.");
  assert.match(engineErrorText("Object changed since version 3; current version is 4.", "x"), /modifié ailleurs/);
  assert.equal(engineErrorText("Le nom de l'emission est requis.", "x"), "Le nom de l'emission est requis.");
  assert.equal(engineErrorText("", "Enregistrement impossible."), "Enregistrement impossible.");
  assert.match(engineErrorText("Unknown cart: Pubs", "x"), /Le bac « Pubs » n'existe plus/);
  assert.match(engineErrorText("unknown category: Jazz", "x"), /La sélection « Jazz » n'existe plus/);
});

test("a new heure type starts with a jingle and titres", () => {
  const carts = [
    { id: 1, title: "Jingles", mode: "random" },
    { id: 2, title: "Radio Zef", mode: "relay" },
    { id: 3, title: "Prog", mode: "playlist_loop" },
  ];
  assert.deepEqual(
    starterMotif(carts, [{ name: "Archives" }, { name: "Rotation" }]).map((row) => [
      row.kind,
      row.cart ?? row.category,
    ]),
    [
      ["jingle", "Jingles"],
      ["musique", "Rotation"],
    ],
  );
  assert.deepEqual(
    starterMotif(carts, []).map((row) => [row.kind, row.cart]),
    [
      ["jingle", "Jingles"],
      ["son", "Prog"],
    ],
  );
  assert.deepEqual(starterMotif([], []), []);
});

test("a new step plays what its kind suggests", () => {
  const carts = [
    { id: 1, title: "Jingles", mode: "random" },
    { id: 2, title: "Pubs partenaires", mode: "playlist_loop" },
    { id: 3, title: "Chroniques", mode: "playlist" },
    { id: 4, title: "Prog relais", mode: "relay" },
  ];
  const selections = [{ name: "Archives" }, { name: "Rotation" }];
  assert.equal(defaultSource("jingle", carts, selections).cart, "Jingles");
  assert.equal(defaultSource("pub", carts, selections).cart_id, 2);
  assert.equal(defaultSource("son", carts, selections).cart, "Chroniques");
  assert.deepEqual(defaultSource("musique", carts, selections), { cart: null, cart_id: null, category: "Rotation" });
  assert.equal(defaultSource("pub", [], []).cart, null);
});
