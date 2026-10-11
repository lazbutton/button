import assert from "node:assert/strict";
import test from "node:test";
import type { LiveSnapshot, RundownItem } from "./types";
import {
  DESK_FILE_AHEAD,
  antennaFile,
  antennaRundownItem,
  clockCoveringItem,
  clockElapsedSec,
  clockNextFileItem,
  clockPlayableItem,
  isDeskPin,
  liveHarborRundownItem,
  partitionRundown,
} from "./rundownLive.ts";

test("Icecast title wins over the wall covering slot", () => {
  const wall = new Date("2026-09-20T14:01:00+02:00");
  const items: RundownItem[] = [
    {
      at: "2026-09-20T13:58:00+02:00",
      duration: 240,
      kind: "musique",
      when: "sequential",
      resource: "nowave — Poinsetta",
      queue: "autodj",
      status: "prévu",
      clock: "",
      daypart: "",
      title: "Poinsetta",
      artist: "nowave",
    },
    {
      at: "2026-09-20T14:02:00+02:00",
      duration: 180,
      kind: "musique",
      when: "sequential",
      resource: "Prog — Yama Warashi — Saku Saku",
      queue: "autodj",
      status: "prévu",
      clock: "",
      daypart: "",
      title: "Saku Saku",
      artist: "Yama Warashi",
    },
  ];
  const live: LiveSnapshot = {
    status: "playing",
    title: "Saku Saku",
    artist: "Yama Warashi",
    source: "autodj",
    remaining: 90,
    elapsed: 90,
  };
  const { onAir } = partitionRundown(items, wall, live);
  assert.equal(onAir?.title, "Saku Saku");
});

test("pad outside the rundown stays a live cart insert", () => {
  const wall = new Date("2026-09-20T14:01:00+02:00");
  const items: RundownItem[] = [
    {
      at: "2026-09-20T13:58:00+02:00",
      duration: 240,
      kind: "musique",
      when: "sequential",
      resource: "nowave — Poinsetta",
      queue: "autodj",
      status: "prévu",
      clock: "",
      daypart: "",
    },
  ];
  const live: LiveSnapshot = {
    status: "playing",
    title: "ID BUTTON",
    artist: "Jingles",
    source: "carts",
    kind: "son",
    remaining: 4,
    elapsed: 2,
  };
  const { onAir } = partitionRundown(items, wall, live);
  assert.equal(onAir?.status_code, "on_air");
  assert.equal(onAir?.queue, "carts");
  assert.equal(onAir?.resource.includes("ID BUTTON"), true);
});

test("desk file only keeps the next ten upcoming items", () => {
  assert.equal(DESK_FILE_AHEAD, 10);
});

test("clock preview ids are not desk pins", () => {
  assert.equal(
    isDeskPin({
      id: "clock|2026-09-20T14:02:00+02:00|nowave",
      at: "2026-09-20T14:02:00+02:00",
      kind: "musique",
      when: "sequential",
      resource: "nowave — Agave",
      queue: "autodj",
      status: "prévu",
      clock: "",
      daypart: "",
      origin: "clock",
    }),
    false,
  );
  assert.equal(
    isDeskPin({
      id: "desk-1",
      at: "2026-09-20T14:02:00+02:00",
      kind: "musique",
      when: "sequential",
      resource: "collé",
      queue: "autodj",
      status: "prévu",
      clock: "",
      daypart: "",
      origin: "desk",
    }),
    true,
  );
});

function fileItem(partial: Partial<RundownItem> & Pick<RundownItem, "at" | "resource">): RundownItem {
  return {
    kind: "musique",
    when: "sequential",
    queue: "autodj",
    status: "prévu",
    clock: "",
    daypart: "",
    beets_id: 1,
    duration: 180,
    ...partial,
  };
}

test("harbor live wins over the clock covering slot", () => {
  const wall = new Date("2026-09-20T10:20:05+02:00");
  const music = fileItem({
    id: "music",
    at: "2026-09-20T10:18:00+02:00",
    duration: 240,
    origin: "clock",
    resource: "nowave — Poinsetta",
    title: "Poinsetta",
  });
  const jingle = fileItem({
    id: "jingle",
    at: "2026-09-20T10:20:00+02:00",
    duration: 8,
    kind: "jingle",
    origin: "clock",
    resource: "Jingles — ID",
    title: "ID",
    cart_id: 2,
    sound_id: 4,
    beets_id: null,
  });
  const live: LiveSnapshot = {
    status: "playing",
    title: "Hop Pop Hop",
    artist: "Marie",
    source: "stream",
    remaining: 0,
    elapsed: 12,
  };
  const { onAir } = partitionRundown([music, jingle], wall, live);
  assert.equal(onAir?.title, "Hop Pop Hop");
  assert.equal(onAir?.origin, "live");
  assert.notEqual(onAir?.id, "jingle");
});

test("live harbor item is Direct when Icecast has no title", () => {
  const wall = new Date("2026-09-20T10:20:05+02:00");
  const item = liveHarborRundownItem(
    { status: "playing", source: "stream", remaining: 0, elapsed: 3 },
    wall,
  );
  assert.equal(item?.title, "Direct");
  assert.equal(item?.origin, "live");
});

test("clock covering prefers the later start so an anchor cuts the motif", () => {
  const wall = new Date("2026-09-20T10:20:05+02:00");
  const music = fileItem({
    id: "music",
    at: "2026-09-20T10:18:00+02:00",
    duration: 240,
    resource: "nowave — Poinsetta",
    title: "Poinsetta",
  });
  const pub = fileItem({
    id: "pub",
    at: "2026-09-20T10:20:00+02:00",
    duration: 30,
    kind: "pub",
    when: "anchored",
    resource: "Pubs — Spot",
    title: "Spot",
    cart_id: 3,
    sound_id: 9,
    beets_id: null,
  });
  const items = [music, pub];
  assert.equal(clockCoveringItem(items, wall)?.id, "pub");
  assert.equal(clockPlayableItem(items, wall)?.id, "pub");
  assert.equal(clockNextFileItem(items, music)?.id, "pub");
  assert.ok(Math.abs(clockElapsedSec(pub, wall) - 5) < 0.001);
});

test("clock elapsed ignores Icecast remaining", () => {
  const wall = new Date("2026-09-20T14:01:00+02:00");
  const item = fileItem({
    at: "2026-09-20T14:00:00+02:00",
    duration: 200,
    resource: "nowave — Poinsetta",
    title: "Poinsetta",
  });
  assert.equal(clockElapsedSec(item, wall), 60);
  assert.equal(clockPlayableItem([item], wall)?.resource, item.resource);
});

test("clock playable waits for the next file when nothing covers now", () => {
  const wall = new Date("2026-09-20T14:00:00+02:00");
  const next = fileItem({
    id: "soon",
    at: "2026-09-20T14:00:08+02:00",
    resource: "Jingles — ID",
    kind: "jingle",
    cart_id: 2,
    sound_id: 4,
    beets_id: null,
    duration: 8,
  });
  assert.equal(clockCoveringItem([next], wall), null);
  assert.equal(clockPlayableItem([next], wall)?.id, "soon");
  assert.ok(clockElapsedSec(next, wall) < 0);
});

test("antenna file follows Liquidsoap elapsed, not the planned clock", () => {
  const wall = new Date("2026-09-28T13:29:00+02:00");
  const live: LiveSnapshot = {
    status: "playing",
    source: "autodj",
    artist: "RAPH",
    title: "FlawlessIssues-WhatsGoingOn.mp3",
    elapsed: 110,
    remaining: 40,
    on_air: "2026-09-28 13:27:10",
    initial_uri:
      'annotate:radiotomate_sound_id="72":/media/50-carts/4/FlawlessIssues-WhatsGoingOn.mp3',
    radiotomate_sound_id: "72",
  };
  const file = antennaFile(live);
  assert.equal(file?.cartId, 4);
  assert.equal(file?.soundId, 72);
  assert.equal(file?.elapsed, 110);
  const item = antennaRundownItem(file!, wall.getTime() - 110_000);
  assert.ok(Math.abs(clockElapsedSec(item, wall) - 110) < 0.001);
});
