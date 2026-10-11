import assert from "node:assert/strict";
import test from "node:test";
import { harborDetail, harborPhase, slotRule, weeklyHost } from "./harborPanel.ts";
import type { Emission, LiveSnapshot } from "./types.ts";

function live(source: string, state?: "waiting" | "on_air"): LiveSnapshot {
  return {
    status: "playing",
    source,
    emission: state ? { id: 4, title: "QG", artist: "soir", state } : null,
  };
}

test("harbor is connected, waiting, or absent", () => {
  assert.equal(harborPhase({ live: live("stream") }), "connected");
  assert.equal(
    harborPhase({ live: live("autodj", "waiting"), slotActive: true }),
    "waiting",
  );
  assert.equal(harborPhase({ live: live("autodj"), liveAbsent: true }), "waiting");
  assert.equal(harborPhase({ live: live("autodj") }), "absent");
  assert.equal(harborPhase({ live: { status: "offline" }, playoutSource: "stream" }), "absent");
  assert.equal(harborDetail("waiting", true), "L’antenne ne répond pas.");
});

test("a named slot names the only account that may connect", () => {
  const rows = [{ id: 4, scope: "weekly", title: "QG", artist: "", host_username: "lea" }] as Emission[];
  assert.equal(weeklyHost(rows, 4), "lea");
  assert.equal(weeklyHost(rows, 9), "");
  assert.match(slotRule("lea", "QG"), /nommé lea/);
  assert.match(slotRule(""), /droit Stream/);
});
