import assert from "node:assert/strict";
import test from "node:test";
import {
  findSoundByPath,
  ranksSwapSounds,
  ranksUnslotSound,
  ranksWithSoundAt,
} from "./deskPads.ts";
import type { Cart, Sound } from "./types.ts";

function sound(id: number, rank: number, path: string): Sound {
  return {
    id,
    rank,
    title: `s${id}`,
    duration: 8,
    active: true,
    available: true,
    gain: null,
    peak: null,
    last_played: null,
    uploader: null,
    path,
  };
}

test("ranksWithSoundAt slides the chosen sound to the pad slot", () => {
  const sounds = [sound(1, 1, "a"), sound(2, 2, "b"), sound(3, 3, "c")];
  assert.deepEqual(ranksWithSoundAt(sounds, 3, 0), [3, 1, 2]);
  assert.deepEqual(ranksUnslotSound(sounds, 1), [2, 3, 1]);
  assert.deepEqual(ranksSwapSounds(sounds, 1, 3), [3, 2, 1]);
});

test("findSoundByPath matches a suffix path", () => {
  const cart = {
    id: 4,
    title: "Jingles",
    sounds: [sound(9, 1, "30-habillage/id.flac")],
  } as Cart;
  assert.equal(findSoundByPath(cart, "/media/30-habillage/id.flac")?.id, 9);
});
