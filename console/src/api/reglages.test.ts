import assert from "node:assert/strict";
import test from "node:test";
import { derivePillars, type Pillar } from "./antenneState.ts";
import { automateSummary, reglagesSections } from "./reglages.ts";
import type { AntenneState } from "./types";

test("l'admin voit la station, puis son compte ; les autres rôles, leur compte seulement", () => {
  assert.deepEqual(
    reglagesSections("admin").map((section) => section.id),
    ["comptes", "station", "automate", "compte"],
  );
  for (const role of ["programmateur", "animateur"] as const) {
    assert.deepEqual(
      reglagesSections(role).map((section) => [section.id, section.label]),
      [["compte", "Mon compte"]],
    );
  }
});

function state(over: Partial<AntenneState> = {}): AntenneState {
  return {
    at: "2026-11-10T11:18:00",
    playout: {
      reachable: true,
      source: "autodj",
      silence_s: 0.2,
      rms_db: -18,
      icecast_targets: ["icecast:8000/button.mp3"],
      icecast_connected: ["icecast:8000/button.mp3"],
      icecast_down: [],
    },
    engine: { heartbeat_age_s: 0.5, heartbeat_ok: true, playout_connected: true, db_ok: true },
    incidents: [],
    listeners: [
      { target: "icecast:8000/button.mp3", host: "icecast", mount: "button.mp3", reachable: true, mounted: true, connected: true, listeners: 0, listener_peak: 1 },
    ],
    asrun: [],
    next_live_slot: null,
    ...over,
  };
}

test("tout va bien : une phrase qui le dit", () => {
  assert.deepEqual(automateSummary(derivePillars(state(), false), false, "11:18"), {
    tone: "ok",
    title: "Tout va bien",
    detail: "L’antenne tourne, sans incident ouvert.",
  });
});

test("un souci : la phrase nomme les pastilles en cause, à transmettre", () => {
  const pillars = derivePillars(
    state({
      playout: { ...state().playout, silence_s: 25 },
      incidents: [{ kind: "silence", detail: "−58 dB", since_s: 25, notified: true }],
    }),
    false,
  );
  assert.deepEqual(automateSummary(pillars, false, "11:18"), {
    tone: "alert",
    title: "Problème en cours",
    detail:
      "Antenne : silence 25 s · Alertes : 1 ouverte. Transmets ce résumé à la personne qui s’occupe de la machine.",
  });
});

test("à surveiller : les pastilles orange seulement", () => {
  const pillars = derivePillars(
    state({ next_live_slot: { title: "QG", label: "QG 20:00-22:00", starts_in_s: 0, active: true } }),
    false,
  );
  const summary = automateSummary(pillars, false, "11:18");
  assert.equal(summary.tone, "warn");
  assert.equal(summary.title, "À surveiller");
  assert.equal(summary.detail, "Direct : QG · encodeur absent.");
});

test("sans relevé récent, ou sans relevé du tout, la phrase ne dit jamais que tout va bien", () => {
  const stale = automateSummary(derivePillars(state(), false), true, "11:18");
  assert.equal(stale.tone, "off");
  assert.equal(stale.title, "Sans nouvelles depuis 11:18");
  assert.match(stale.detail, /préviens la personne qui s’occupe de la machine/);

  const none: Pillar[] = derivePillars(null, false);
  const missing = automateSummary(none, true, null);
  assert.equal(missing.tone, "off");
  assert.equal(missing.title, "État indisponible");
});
