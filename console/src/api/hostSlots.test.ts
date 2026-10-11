import assert from "node:assert/strict";
import test from "node:test";
import { slotsForHost } from "./hostSlots.ts";
import type { Emission } from "./types.ts";

test("slots follow the named host, whatever the case", () => {
  const rows = [
    { id: 1, scope: "weekly", title: "QG", artist: "", host_username: "Lea" },
    { id: 2, scope: "weekly", title: "Nuit", artist: "", host_username: "sam" },
    { id: 3, scope: "session", title: "Direct", artist: "", host_username: "lea" },
  ] as Emission[];
  assert.deepEqual(slotsForHost(rows, "lea").map((row) => row.id), [1]);
  assert.deepEqual(slotsForHost(rows, "").map((row) => row.id), []);
});
