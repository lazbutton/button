import assert from "node:assert/strict";
import test from "node:test";
import { orderBanner, sameOrder, sortSounds, transferSummary } from "./cartOrder.ts";

const split = (raw: string) => {
  const cut = raw.indexOf(" - ");
  return cut > 0 ? { artist: raw.slice(0, cut), title: raw.slice(cut + 3) } : { artist: "", title: raw };
};

const sounds = [
  { id: 1, rank: 1, title: "Zéphyr - Dune", duration: 200, last_played: "2026-11-13T10:00+01:00" },
  { id: 2, rank: 2, title: "Orage - Été indien", duration: 120, last_played: null },
  { id: 3, rank: 3, title: "annonce", duration: 30, last_played: "2026-11-01T10:00+01:00" },
];

test("a view sorts by a column, never the cart's ranks", () => {
  assert.deepEqual(sortSounds(sounds, "title", split).map((s) => s.id), [3, 1, 2]);
  assert.deepEqual(sortSounds(sounds, "artist", split).map((s) => s.id), [2, 1, 3]);
  assert.deepEqual(sortSounds(sounds, "duration", split).map((s) => s.id), [3, 2, 1]);
  assert.deepEqual(sortSounds(sounds, "last_played", split).map((s) => s.id), [2, 3, 1]);
  assert.deepEqual(sortSounds(sounds, "rank", split).map((s) => s.id), [1, 2, 3]);
  assert.deepEqual(sounds.map((s) => s.rank), [1, 2, 3]);
});

test("the cart's order already shown leaves nothing to apply", () => {
  assert.equal(sameOrder(sortSounds(sounds, "rank", split), sounds), true);
  assert.equal(sameOrder(sortSounds(sounds, "title", split), sounds), false);
});

test("the band says the cart plays as before; a random cart has no order", () => {
  assert.match(orderBanner("title", "playlist"), /^Vue triée par titre : le bac passe toujours dans son ordre/);
  assert.match(orderBanner("duration", "random"), /En Aléatoire, le bac n'a pas d'ordre/);
});

test("what a move or a copy did, in a toast", () => {
  assert.deepEqual(transferSummary(true, 2, [], "Nuit"), { text: "2 sons copiés dans « Nuit ».", tone: "success" });
  assert.deepEqual(transferSummary(false, 1, [{ title: "Dune", reason: "à l'antenne" }], "Nuit"), {
    text: "1 son déplacé vers « Nuit ». 1 son est resté : à l'antenne.",
    tone: "info",
  });
  assert.equal(transferSummary(false, 0, [{ title: "Dune", reason: "déjà dans le bac d'arrivée" }], "Nuit").tone, "error");
});
