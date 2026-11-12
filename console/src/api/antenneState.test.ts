import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { airBanner, derivePillars, formatDuration, incidentAdvice, incidentLabel, worstTone } from "./antenneState.ts";
import type { AntenneState } from "./types";

/** Les incidents qu'ouvre le moteur : chaque `active["…"]` de sa surveillance. */
function engineIncidentKinds(): string[] {
  const alerts = readFileSync(new URL("../../../engine/radiotomate/scheduler/alerts.py", import.meta.url), "utf8");
  return [...new Set([...alerts.matchAll(/\bactive\["([a-z_]+)"\]/g)].map((match) => match[1]))];
}

function state(over: Partial<AntenneState> = {}): AntenneState {
  return {
    at: "2026-09-21T22:00:00",
    playout: {
      reachable: true,
      source: "autodj",
      silence_s: 0.2,
      rms_db: -17.6,
      icecast_targets: ["icecast:8000/radio.mp3", "radio.example:8000/radio.mp3"],
      icecast_connected: ["icecast:8000/radio.mp3", "radio.example:8000/radio.mp3"],
      icecast_down: [],
    },
    engine: { heartbeat_age_s: 0.4, heartbeat_ok: true, playout_connected: true, db_ok: true, tick_run_total: 10, tick_gated_total: 30 },
    incidents: [],
    listeners: [
      { target: "icecast:8000/radio.mp3", host: "icecast", mount: "radio.mp3", reachable: true, mounted: true, connected: true, listeners: 0, listener_peak: 1 },
      { target: "radio.example:8000/radio.mp3", host: "radio.example", mount: "radio.mp3", reachable: true, mounted: true, connected: true, listeners: 4, listener_peak: 9 },
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
    playout: { reachable: true, source: "autodj", silence_s: 25, rms_db: -90, icecast_down: ["radio.example:8000/radio.mp3"] },
    incidents: [
      { kind: "icecast_down", detail: "Sortie Icecast déconnectée : radio.example", since_s: 40, notified: true },
      { kind: "silence", detail: "25 s de silence (source autodj)", since_s: 20, notified: true },
    ],
    listeners: [
      { target: "icecast:8000/radio.mp3", host: "icecast", mount: "radio.mp3", reachable: true, mounted: true, connected: true, listeners: 0, listener_peak: 1 },
      { target: "radio.example:8000/radio.mp3", host: "radio.example", mount: "radio.mp3", reachable: false, mounted: false, connected: false, listeners: null, listener_peak: null },
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

test("no live within the week, the weekly shows declared or not", () => {
  // The engine also says null when the week's shows are cancelled in the Agenda.
  const direct = derivePillars(state({ next_live_slot: null }), false).find((p) => p.key === "direct");
  assert.equal(direct?.value, "aucun prévu");
  assert.equal(direct?.tone, "off");
  assert.deepEqual(direct?.detail, ["Aucun direct prévu d’ici 7 jours."]);
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

test("a stalled playout is named before a silence, and says what to do", () => {
  const stalled = {
    kind: "playout_stalled",
    detail: "« Dahlia » n'avance plus depuis 45 s : le même son passe en boucle (source autodj)",
    since_s: 45,
    notified: true,
  };
  const banner = (over: { harbor?: boolean; silenceS?: number; incidentKinds: string[] }) =>
    airBanner({ harbor: false, directTitle: "QG", offline: false, silenceS: 0.2, playoutReachable: true, ...over });
  assert.deepEqual(banner({ incidentKinds: ["playout_stalled"] }), {
    label: "Problème",
    cause: "Antenne figée",
    tone: "problem",
    hot: false,
  });
  // Le son figé peut être un blanc : le gel reste la cause, et « Suivant » n'est pas son remède.
  assert.equal(banner({ silenceS: 40, incidentKinds: ["silence", "playout_stalled"] }).cause, "Antenne figée");
  // Sans nouvelles du playout, rien ne dit que le gel dure encore.
  assert.equal(banner({ incidentKinds: ["heartbeat", "playout_stalled"] }).cause, "Battement perdu");
  // Un direct qui a pris l'antenne reste un direct.
  assert.equal(banner({ harbor: true, incidentKinds: ["playout_stalled"] }).label, "Direct : QG");

  assert.equal(incidentLabel(stalled), "Antenne figée");
  assert.match(incidentAdvice(stalled), /« Suivant » et « Vider les files » n’y changent rien/);
  assert.match(incidentAdvice(stalled), /relancer le moteur, sur la machine de la station/);
  assert.equal(incidentAdvice({ kind: "silence", detail: "", since_s: 0, notified: false }), "");

  // Le niveau est bon, et le pilier Antenne ne reste pas vert pour autant.
  const pillars = derivePillars(state({ incidents: [stalled] }), false);
  const antenne = pillars.find((pillar) => pillar.key === "antenne");
  assert.equal(antenne?.value, "figée");
  assert.equal(antenne?.tone, "alert");
  assert.equal(antenne?.detail[0], stalled.detail);
  assert.equal(antenne?.detail[1], incidentAdvice(stalled));
  assert.equal(worstTone(pillars), "alert");
});

test("a disk almost full is named in the alerts", () => {
  const pillars = derivePillars(
    state({
      incidents: [
        { kind: "disk", detail: "1,8 Go libres sur 40 Go", since_s: 120, notified: true },
      ],
    }),
  );
  const alertes = pillars.find((pillar) => pillar.key === "alertes");
  assert.equal(alertes?.tone, "alert");
  assert.deepEqual(alertes?.detail, ["Disque presque plein — 1,8 Go libres sur 40 Go (depuis 2 min)"]);
});

test("each incident the engine opens has a name, the Agenda's too", () => {
  const kinds = engineIncidentKinds();
  // Huit aujourd'hui : si le moteur les ouvre autrement, relire ce test.
  assert.ok(kinds.length >= 8, `incidents du moteur introuvables : ${kinds.join(", ")}`);
  assert.ok(kinds.includes("playout_stalled"), "le moteur n’ouvre plus l’incident « playout_stalled »");
  for (const kind of kinds) {
    const label = incidentLabel({ kind, detail: "", since_s: 0, notified: false });
    assert.notEqual(label, kind, `l’incident « ${kind} » n’a pas de nom dans la console`);
  }
  const agenda = derivePillars(
    state({
      incidents: [{ kind: "agenda", detail: "Set attendu pour 20:30 : Nuit blanche", since_s: 300, notified: false }],
    }),
    false,
  ).find((pillar) => pillar.key === "alertes");
  assert.deepEqual(agenda?.detail, ["Diffusion de l’Agenda — Set attendu pour 20:30 : Nuit blanche (depuis 5 min)"]);
});

test("formatDuration", () => {
  assert.equal(formatDuration(42), "42 s");
  assert.equal(formatDuration(600), "10 min");
  assert.equal(formatDuration(3600 * 2 + 60 * 5), "2 h 05");
  assert.equal(formatDuration(86400 * 2 + 3600 * 3), "2 j 3 h");
});
