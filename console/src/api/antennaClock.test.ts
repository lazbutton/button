import assert from "node:assert/strict";
import test from "node:test";
import { anchorClock, liveDuration, liveTrackKey, readClock, type ClockAnchor } from "./antennaClock.ts";
import type { LiveSnapshot } from "./types";

const T0 = Date.parse("2026-11-12T19:17:06Z");

function beat(over: Partial<LiveSnapshot> = {}): LiveSnapshot {
  return {
    status: "playing",
    source: "autodj",
    title: "Titre",
    artist: "Artiste",
    on_air: "2026-11-12 20:17:06",
    ...over,
  };
}

/** Passe les battements à l'horloge, un par seconde, et rend ce qu'elle affiche au dernier. */
function play(beats: LiveSnapshot[], startMs = T0, from: ClockAnchor | null = null) {
  let anchor = from;
  let wall = startMs;
  beats.forEach((live, index) => {
    wall = startMs + index * 1000;
    anchor = anchorClock(anchor, live, wall);
  });
  const last = beats[beats.length - 1];
  return { anchor, wall, reading: readClock(anchor, liveTrackKey(last), wall) };
}

test("un titre qui démarre : l'écoulé et le reste du moteur donnent sa durée", () => {
  const { reading } = play([beat({ elapsed: 0.62, remaining: 149.35 })]);
  assert.deepEqual(reading, { elapsedSec: 1, remainingSec: 149, durationSec: 150 });
});

test("entre deux battements, l'horloge avance avec l'heure", () => {
  const { anchor } = play([beat({ elapsed: 10, remaining: 140 })]);
  const key = liveTrackKey(beat());
  assert.deepEqual(readClock(anchor, key, T0 + 400), { elapsedSec: 10, remainingSec: 140, durationSec: 150 });
  assert.deepEqual(readClock(anchor, key, T0 + 1_600), { elapsedSec: 12, remainingSec: 138, durationSec: 150 });
});

test("un premier battement qui annonce 3 s de reste ne fixe pas la durée du titre", () => {
  // Le playout dit d'abord le reste de son fondu, puis celui du titre.
  const { reading } = play([
    beat({ elapsed: 0.18, remaining: 2.82 }),
    beat({ elapsed: 1.14, remaining: 1.86 }),
    beat({ elapsed: 2.16, remaining: 0.84 }),
    beat({ elapsed: 3.16, remaining: 146.81 }),
    beat({ elapsed: 4.14, remaining: 145.83 }),
  ]);
  assert.deepEqual(reading, { elapsedSec: 4, remainingSec: 146, durationSec: 150 });
});

test("une durée qui tremble d'un battement à l'autre ne fait pas sauter le compte à rebours", () => {
  const first = play([beat({ elapsed: 5, remaining: 144.4 })]);
  const { anchor } = play([beat({ elapsed: 6, remaining: 144.2 }), beat({ elapsed: 7, remaining: 142.6 })], T0 + 1_000, first.anchor);
  assert.equal(anchor?.duration, 149.4);
});

test("un reste qui se corrige pour de bon est suivi, dans les deux sens", () => {
  const first = play([beat({ elapsed: 5, remaining: 145 })]);
  const longer = play([beat({ elapsed: 6, remaining: 174 })], T0 + 1_000, first.anchor);
  assert.equal(longer.reading.durationSec, 180);
  const shorter = play([beat({ elapsed: 7, remaining: 113 })], T0 + 2_000, longer.anchor);
  assert.deepEqual(shorter.reading, { elapsedSec: 7, remainingSec: 113, durationSec: 120 });
});

test("sans reste, la durée n'est pas connue, puis elle arrive", () => {
  const unknown = play([beat({ elapsed: 30, remaining: 0 })]);
  assert.deepEqual(unknown.reading, { elapsedSec: 30, remainingSec: 0, durationSec: 1 });
  const known = play([beat({ elapsed: 31, remaining: 89 })], T0 + 1_000, unknown.anchor);
  assert.deepEqual(known.reading, { elapsedSec: 31, remainingSec: 89, durationSec: 120 });
});

test("la durée que dit le moteur passe avant l'écoulé et le reste", () => {
  assert.equal(liveDuration(beat({ elapsed: 12, remaining: 3, duration: 200 })), 200);
  assert.equal(liveDuration(beat({ elapsed: 12, remaining: 3 })), 15);
  assert.equal(liveDuration(beat({ elapsed: 12 })), 0);
  assert.equal(liveDuration(beat({ remaining: 40 })), 0);
});

test("l'écoulé du moteur s'écarte de plus de 3 s : l'horloge se recale sur lui", () => {
  const first = play([beat({ elapsed: 60, remaining: 120 })]);
  // Dix secondes plus tard, le moteur dit 40 s : le titre a repris plus tôt.
  const anchor = anchorClock(first.anchor, beat({ elapsed: 40, remaining: 140 }), T0 + 10_000);
  assert.deepEqual(readClock(anchor, liveTrackKey(beat()), T0 + 10_000), {
    elapsedSec: 40,
    remainingSec: 140,
    durationSec: 180,
  });
});

test("un autre titre prend un nouveau repère", () => {
  const first = play([beat({ elapsed: 170, remaining: 10 })]);
  const next = beat({ title: "Suivant", on_air: "2026-11-12 20:20:06", elapsed: 0.5, remaining: 239.5 });
  const anchor = anchorClock(first.anchor, next, T0 + 11_000);
  assert.deepEqual(readClock(anchor, liveTrackKey(next), T0 + 11_000), {
    elapsedSec: 1,
    remainingSec: 239,
    durationSec: 240,
  });
  // Le repère n'est plus celui du titre d'avant.
  assert.deepEqual(readClock(anchor, liveTrackKey(beat()), T0 + 11_000), {
    elapsedSec: 0,
    remainingSec: 1,
    durationSec: 1,
  });
});

test("sans battement lisible, l'horloge garde son repère", () => {
  const first = play([beat({ elapsed: 20, remaining: 100 })]);
  assert.equal(anchorClock(first.anchor, null, T0 + 1_000), first.anchor);
  assert.equal(anchorClock(first.anchor, { status: "offline" }, T0 + 1_000), first.anchor);
  assert.equal(anchorClock(first.anchor, beat({ elapsed: Number.NaN }), T0 + 1_000), first.anchor);
  assert.equal(anchorClock(null, null, T0), null);
  assert.deepEqual(readClock(null, liveTrackKey(null), T0), { elapsedSec: 0, remainingSec: 1, durationSec: 1 });
});
