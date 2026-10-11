import assert from "node:assert/strict";
import test from "node:test";
import { displayNow } from "../lib/nowPlaying.ts";
import { rundownCopy } from "./rundownLive.ts";
import type { RundownItem } from "./types";

test("a cart filename becomes artist and title, not the bac name", () => {
  const parsed = displayNow({
    title: "GingerRoot-LeChateau.mp3",
    artist: "RAPH",
  });
  assert.equal(parsed.artist, "Ginger Root");
  assert.equal(parsed.title, "Le Chateau");
});

test("spaced dash and camel case both split", () => {
  assert.deepEqual(
    displayNow({ title: "redveil - Campbell.mp3", artist: "RAPH" }),
    expectPair("redveil", "Campbell"),
  );
  assert.deepEqual(
    displayNow({ title: "Air-AllINeedavecBethHirsch.mp3", artist: "RAPH" }),
    expectPair("Air", "All I Need avec Beth Hirsch"),
  );
  assert.deepEqual(
    displayNow({ title: "BeeGeesetSGLewis-MoreThanaWoman.mp3", artist: "RAPH" }),
    expectPair("Bee Gees et SG Lewis", "More Thana Woman"),
  );
});

test("a letter-spaced title is left intact", () => {
  const parsed = displayNow({ title: "Nat King Cole - L-O-V-E.mp3", artist: "RAPH" });
  assert.equal(parsed.artist, "Nat King Cole");
  assert.equal(parsed.title, "L-O-V-E");
});

test("a real artist tag is kept when the title is not a file", () => {
  const parsed = displayNow({ title: "Le Chateau", artist: "Ginger Root" });
  assert.equal(parsed.artist, "Ginger Root");
  assert.equal(parsed.title, "Le Chateau");
});

test("rundown rows use the same reading", () => {
  const item = {
    resource: "JoeWalsh-IndianSummer.mp3",
    title: "JoeWalsh-IndianSummer.mp3",
    artist: "RAPH",
  } as RundownItem;
  assert.deepEqual(rundownCopy(item), {
    artist: "Joe Walsh",
    title: "Indian Summer",
  });
});

function expectPair(artist: string, title: string) {
  return {
    artist,
    title,
    duration: null,
    startedAt: null,
  };
}
