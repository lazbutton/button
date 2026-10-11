import assert from "node:assert/strict";
import test from "node:test";
import { airBanner, derivePillars, formatDuration, worstTone } from "./antenneState.ts";
import type { AntenneState } from "./types";

function state(over: Partial<AntenneState> = {}): AntenneState {
  return {
    at: "2026-09-21T22:00:00",
    playout: {
      reachable: true,
      source: "autodj",
      silence_s: 0.2,
      rms_db: -17.6,
      icecast_targets: ["icecast:8000/button.mp3", "radio.example:8000/button.mp3"],
      icecast_connected: ["icecast:8000/button.mp3", "radio.example:8000/button.mp3"],
      icecast_down: [],
    },
    engine: { heartbeat_age_s: 0.4, heartbeat_ok: true, playout_connected: true, db_ok: true, tick_run_total: 10, tick_gated_total: 30 },
    incidents: [],
    listeners: [
      { target: "icecast:8000/button.mp3", host: "icecast", mount: "button.mp3", reachable: true, mounted: true, connected: true, listeners: 0, listener_peak: 1 },
      { target: "radio.example:8000/button.mp3", host: "radio.example", mount: "button.mp3", reachable: true, mounted: true, connected: true, listeners: 4, listener_peak: 9 },
    ],
    asrun: [],
    next_live_slot: { title: "QG", label: "QG 20:00-22:00", starts_in_s: 7800, active: false },
    ...over,
  };
}

test("all green when everything is fine", () => {
  const pillars = derivePillars(state(), false);
  assert.equal(worstTone(pillars), "ok");
  const byKey = Object.fromEntries(pillars.map((p) => [p.key, p]));
  assert.equal(byKey.antenne.value, "-18 dB");
  assert.equal(byKey.public.value, "4 auditeurs");
  assert.equal(byKey.local.value, "0 auditeurs");
  assert.equal(byKey.direct.value, "QG dans 2 h 10");
  assert.equal(byKey.moteur.value, "OK");
  assert.equal(byKey.alertes.value, "aucune");
  assert.deepEqual(
    pillars.map((pillar) => pillar.label),
    ["Antenne", "Public", "Local", "Direct", "Moteur", "Alertes"],
  );
});

test("silence and disconnected public output turn red", () => {
  const s = state({
    playout: { reachable: true, source: "autodj", silence_s: 25, rms_db: -90, icecast_down: ["radio.example:8000/button.mp3"] },
    incidents: [
      { kind: "icecast_down", detail: "Sortie Icecast déconnectée : radio.example", since_s: 40, notified: true },
      { kind: "silence", detail: "25 s de silence (source autodj)", since_s: 20, notified: true },
    ],
    listeners: [
      { target: "icecast:8000/button.mp3", host: "icecast", mount: "button.mp3", reachable: true, mounted: true, connected: true, listeners: 0, listener_peak: 1 },
      { target: "radio.example:8000/button.mp3", host: "radio.example", mount: "button.mp3", reachable: false, mounted: false, connected: false, listeners: null, listener_peak: null },
    ],
  });
  const byKey = Object.fromEntries(derivePillars(s, false).map((p) => [p.key, p]));
  assert.equal(byKey.antenne.tone, "alert");
  assert.equal(byKey.antenne.value, "silence 25 s");
  assert.equal(byKey.public.tone, "alert");
  assert.equal(byKey.public.value, "coupée");
  assert.equal(byKey.alertes.value, "2 ouvertes");
});

test("engine degradation and missing state", () => {
  const s = state({ engine: { heartbeat_age_s: 3.2, heartbeat_ok: false, playout_connected: true, db_ok: true } });
  const moteur = derivePillars(s, false).find((p) => p.key === "moteur");
  assert.equal(moteur?.tone, "warn");
  const lost = state({ engine: { heartbeat_age_s: 12, heartbeat_ok: false, playout_connected: false, db_ok: true } });
  assert.equal(derivePillars(lost, false).find((p) => p.key === "moteur")?.tone, "alert");
  assert.equal(worstTone(derivePillars(null, false)), "off");
});

test("harbor on air and EF-01 window without encoder", () => {
  const live = state({ playout: { reachable: true, source: "stream", silence_s: 0, harbor_s: 6.5 } });
  assert.equal(derivePillars(live, true).find((p) => p.key === "direct")?.value, "à l’antenne");
  const absent = state({ next_live_slot: { title: "QG", label: "QG 20:00-22:00", starts_in_s: 0, active: true } });
  const direct = derivePillars(absent, false).find((p) => p.key === "direct");
  assert.equal(direct?.tone, "warn");
  assert.match(direct?.value ?? "", /encodeur absent/);
});

test("air banner is the same story for every role", () => {
  assert.deepEqual(
    airBanner({
      harbor: false,
      directTitle: "",
      offline: false,
      silenceS: 0.2,
      playoutReachable: true,
      incidentKinds: [],
    }),
    { label: "En onde", cause: "", tone: "on", hot: false },
  );
  assert.equal(
    airBanner({
      harbor: false,
      directTitle: "",
      offline: false,
      silenceS: 8,
      playoutReachable: true,
      incidentKinds: [],
    }).label,
    "Silence 8 s",
  );
  assert.equal(
    airBanner({
      harbor: false,
      directTitle: "",
      offline: true,
      silenceS: 0,
      playoutReachable: false,
      incidentKinds: ["playout_down"],
    }).cause,
    "Playout injoignable",
  );
  assert.equal(
    airBanner({
      harbor: false,
      directTitle: "",
      offline: false,
      silenceS: 25,
      playoutReachable: true,
      incidentKinds: ["silence"],
    }).hot,
    true,
  );
  assert.equal(
    airBanner({
      harbor: true,
      directTitle: "Hop Pop Hop",
      offline: false,
      silenceS: 30,
      playoutReachable: false,
      incidentKinds: ["playout_down"],
    }).label,
    "Direct : Hop Pop Hop",
  );
  assert.equal(
    airBanner({
      harbor: false,
      directTitle: "",
      offline: true,
      silenceS: 0,
      playoutReachable: false,
      incidentKinds: [],
    }).tone,
    "problem",
  );
});

test("formatDuration", () => {
  assert.equal(formatDuration(42), "42 s");
  assert.equal(formatDuration(600), "10 min");
  assert.equal(formatDuration(3600 * 2 + 60 * 5), "2 h 05");
  assert.equal(formatDuration(86400 * 2 + 3600 * 3), "2 j 3 h");
});
