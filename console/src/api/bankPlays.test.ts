import assert from "node:assert/strict";
import test from "node:test";
import { playLine, playsHeadline, playsOrigins, type TitlePlays } from "./bankPlays.ts";

const plays: TitlePlays = {
  days: 90,
  count: 3,
  by_origin: { autodj: 2, bac: 0, agenda: 1, autre: 0 },
  recent: [
    { on_air: "2026-11-13T22:10+01:00", origin: "autodj", cart: null },
    { on_air: "2026-11-12T09:00+01:00", origin: "bac", cart: { id: 4, title: "Nuit douce" } },
    { on_air: "2026-11-12T09:00+01:00", origin: "agenda", cart: { id: 9, title: "Agenda" } },
  ],
};

test("the headline counts the plays in 90 days", () => {
  assert.equal(playsHeadline(plays), "Passé 3 fois en 90 jours");
  assert.equal(playsHeadline({ count: 1, days: 90 }), "Passé une fois en 90 jours");
  assert.equal(playsHeadline({ count: 0, days: 90 }), "Pas passé à l'antenne en 90 jours");
});

test("the origins that count, in their order", () => {
  assert.equal(playsOrigins(plays), "Auto-DJ 2 · Agenda 1");
  assert.equal(playsOrigins({ by_origin: { autodj: 0, bac: 0, agenda: 0, autre: 0 } }), "");
});

test("a play says when, at Paris, and where from", () => {
  const now = new Date("2026-11-14T10:00:00+01:00");
  assert.deepEqual(playLine(plays.recent[0], now), { when: "hier à 22:10", from: "Auto-DJ" });
  assert.deepEqual(playLine(plays.recent[1], now), { when: "le 12/11 à 09:00", from: "Bac « Nuit douce »" });
  assert.deepEqual(playLine(plays.recent[2], now), { when: "le 12/11 à 09:00", from: "Agenda" });
});
