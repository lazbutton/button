import assert from "node:assert/strict";
import test from "node:test";
import { audience, initials, listenHint, stateAgeS, topAir, topHealth, topNow, type ListenState } from "./topbar.ts";
import type { AntenneState, LiveSnapshot } from "./types";

const NOW = new Date("2026-10-12T10:19:05Z"); // 12:19:05 à Paris (UTC+2)

function state(over: Partial<AntenneState> = {}): AntenneState {
  return {
    at: "2026-10-12T12:19:03",
    playout: { reachable: true, source: "autodj", silence_s: 0.2, rms_db: -17.6 },
    engine: { heartbeat_age_s: 0.4, heartbeat_ok: true, playout_connected: true, db_ok: true },
    incidents: [],
    listeners: [
      { target: "icecast:8000/button.mp3", host: "icecast", mount: "button.mp3", reachable: true, mounted: true, connected: true, listeners: 1, listener_peak: 2 },
      { target: "icecast:8000/studio.wav", host: "icecast", mount: "studio.wav", reachable: true, mounted: true, connected: true, listeners: 3, listener_peak: 3 },
      { target: "radio.example:8000/button.mp3", host: "radio.example", mount: "button.mp3", reachable: true, mounted: true, connected: true, listeners: 12, listener_peak: 20 },
    ],
    asrun: [],
    next_live_slot: null,
    ...over,
  };
}

const playing: LiveSnapshot = { status: "playing", source: "autodj", title: "Titre", artist: "Artiste" };

test("on air: the source is the detail", () => {
  assert.deepEqual(topAir({ live: playing, antenne: state(), loading: false, unreachable: false }), {
    tone: "on",
    label: "En onde",
    detail: "Auto-DJ",
  });
  const relay = topAir({ live: { ...playing, source: "relay" }, antenne: state(), loading: false, unreachable: false });
  assert.equal(relay.detail, "Relais");
});

test("a dated set on air says so", () => {
  const live: LiveSnapshot = {
    ...playing,
    source: "carts",
    emission: { id: 4, title: "Nuit club", artist: "", state: "on_air", scope: "dated", kind: "set" },
  };
  assert.equal(topAir({ live, antenne: state(), loading: false, unreachable: false }).detail, "Émission datée");
});

test("harbor on air is a direct with the show name", () => {
  const live: LiveSnapshot = {
    ...playing,
    source: "stream",
    emission: { id: 2, title: "QG", artist: "", state: "on_air" },
  };
  assert.deepEqual(topAir({ live, antenne: state(), loading: false, unreachable: false }), {
    tone: "direct",
    label: "Direct",
    detail: "QG",
  });
});

test("silence warns, then alerts past twenty seconds", () => {
  const short = topAir({ live: playing, antenne: state({ playout: { reachable: true, silence_s: 6 } }), loading: false, unreachable: false });
  assert.deepEqual(short, { tone: "warn", label: "Silence 6 s", detail: "" });
  const long = topAir({ live: playing, antenne: state({ playout: { reachable: true, silence_s: 31 } }), loading: false, unreachable: false });
  assert.equal(long.tone, "alert");
});

test("problems name their cause", () => {
  const down = topAir({ live: { status: "offline" }, antenne: state(), loading: false, unreachable: false });
  assert.deepEqual(down, { tone: "alert", label: "Playout injoignable", detail: "" });
  const icecast = topAir({
    live: playing,
    antenne: state({ incidents: [{ kind: "icecast_down", detail: "", since_s: 4, notified: false }] }),
    loading: false,
    unreachable: false,
  });
  assert.equal(icecast.label, "Sortie Icecast coupée");
});

test("before the first answer, loading or unreachable", () => {
  assert.equal(topAir({ live: null, antenne: null, loading: true, unreachable: false }).tone, "off");
  assert.deepEqual(topAir({ live: null, antenne: null, loading: false, unreachable: true }), {
    tone: "alert",
    label: "Automate injoignable",
    detail: "",
  });
});

test("an engine that stops answering is not hidden by its last snapshot", () => {
  assert.deepEqual(topAir({ live: playing, antenne: state(), loading: false, unreachable: true }), {
    tone: "alert",
    label: "Automate injoignable",
    detail: "",
  });
});

const song = { title: "Titre", artist: "Artiste" };
const clock = { elapsedSec: 30, remainingSec: 150, durationSec: 180 };

test("the title on air counts down to its end", () => {
  const now = topNow({ live: playing, item: song, clock, stale: false, answeredAt: undefined });
  assert.equal(now.title, "Titre");
  assert.equal(now.artist, "Artiste");
  assert.equal(now.timed, true);
  assert.equal(now.ratio, 1 / 6);
  assert.equal(now.remain, "−2:30");
  assert.equal(now.ending, false);
  assert.equal(now.note, "");
  assert.equal(now.label, "À l’antenne : Titre, Artiste, reste 2:30. Ouvrir l’antenne.");
  const ending = topNow({
    live: playing,
    item: song,
    clock: { elapsedSec: 170, remainingSec: 10, durationSec: 180 },
    stale: false,
    answeredAt: undefined,
  });
  assert.equal(ending.ending, true);
  const idle = topNow({ live: { status: "offline" }, item: undefined, clock, stale: false, answeredAt: undefined });
  assert.equal(idle.idle, true);
  assert.equal(idle.timed, false);
  assert.equal(idle.label, "À l’antenne : Rien à l’antenne. Ouvrir l’antenne.");
});

test("a direct is named after its show, without a countdown", () => {
  const live: LiveSnapshot = {
    ...playing,
    source: "harbor",
    emission: { id: 2, title: "QG", artist: "", state: "on_air" },
  };
  const now = topNow({ live, item: { title: "Direct" }, clock, stale: false, answeredAt: undefined });
  assert.equal(now.title, "QG");
  assert.equal(now.timed, false);
  assert.equal(now.label, "À l’antenne : QG. Ouvrir l’antenne.");
});

test("an engine that stops answering leaves its last title, without its time", () => {
  const answeredAt = Date.parse("2026-10-12T10:16:40Z"); // 12:16 à Paris
  const now = topNow({ live: playing, item: song, clock, stale: true, answeredAt });
  assert.deepEqual(now, {
    title: "Titre",
    artist: "Artiste",
    idle: false,
    stale: true,
    timed: false,
    ratio: 0,
    remain: "−2:30",
    ending: false,
    note: "Sans nouvelles depuis 12:16",
    label: "Sans nouvelles depuis 12:16. Dernier titre connu : Titre, Artiste. Ouvrir l’antenne.",
  });
  // Hiver : UTC+1.
  const winter = topNow({ live: playing, item: song, clock, stale: true, answeredAt: Date.parse("2026-12-01T08:05:00Z") });
  assert.equal(winter.note, "Sans nouvelles depuis 09:05");
  // Un direct garde le nom de son émission.
  const direct = topNow({
    live: { ...playing, source: "harbor", emission: { id: 2, title: "QG", artist: "", state: "on_air" } },
    item: { title: "Direct" },
    clock,
    stale: true,
    answeredAt,
  });
  assert.equal(direct.label, "Sans nouvelles depuis 12:16. Dernier titre connu : QG. Ouvrir l’antenne.");
});

test("an engine that never answered knows neither title nor time", () => {
  const now = topNow({ live: null, item: undefined, clock, stale: true, answeredAt: undefined });
  assert.equal(now.title, "Aucun titre connu");
  assert.equal(now.idle, false);
  assert.equal(now.timed, false);
  assert.equal(now.note, "Sans nouvelles");
  assert.equal(now.label, "Sans nouvelles. Aucun titre connu. Ouvrir l’antenne.");
  // Le dernier relevé disait l'antenne vide : rien ne dit qu'elle l'est encore.
  const offline = topNow({ live: { status: "offline" }, item: undefined, clock, stale: true, answeredAt: Date.parse("2026-10-12T10:16:40Z") });
  assert.equal(offline.title, "Aucun titre connu");
  assert.equal(offline.label, "Sans nouvelles depuis 12:16. Aucun titre connu. Ouvrir l’antenne.");
});

test("audience counts public mounts, never the studio headphones", () => {
  assert.equal(audience(state()), 12);
  const local = state({ listeners: state().listeners.filter((row) => row.host === "icecast") });
  assert.equal(audience(local), 1);
  assert.equal(audience(state({ listeners: [] })), null);
  assert.equal(audience(null), null);
});

test("state age reads the Paris wall clock", () => {
  assert.equal(stateAgeS("2026-10-12T12:19:03", NOW), 2);
  assert.equal(stateAgeS("n'importe quoi", NOW), null);
  // Hiver : UTC+1.
  assert.equal(stateAgeS("2026-12-01T09:00:00", new Date("2026-12-01T08:00:30Z")), 30);
});

test("health is unknown once the state is stale", () => {
  const fresh = topHealth(state(), playing, NOW);
  assert.equal(fresh.stale, false);
  assert.equal(fresh.tone, "ok");
  const old = topHealth(state({ at: "2026-10-12T12:17:00" }), playing, NOW);
  assert.equal(old.stale, true);
  assert.equal(old.tone, "off");
  assert.equal(old.open, 0);
  const alert = topHealth(
    state({ incidents: [{ kind: "silence", detail: "", since_s: 40, notified: true }] }),
    playing,
    NOW,
  );
  assert.equal(alert.tone, "alert");
  assert.equal(alert.open, 1);
});

test("initials", () => {
  assert.equal(initials("atelier"), "AT");
  assert.equal(initials("jean-luc m"), "JM");
  assert.equal(initials("  "), "?");
});

test("headphone hints", () => {
  const base: ListenState = {
    muted: false,
    kind: "icecast",
    fileMissing: false,
    fileLoading: false,
    streamDown: false,
    startsInS: null,
    lagMs: 850,
  };
  assert.equal(listenHint({ ...base, muted: true }, "Antenne publique"), "Écouter au casque : Antenne publique");
  assert.equal(listenHint(base, "Antenne publique"), "Retard du casque : 850 ms");
  assert.equal(listenHint({ ...base, kind: "files", startsInS: 12 }, "x"), "Le titre démarre dans 0:12");
  assert.equal(listenHint({ ...base, kind: "files", lagMs: -40 }, "x"), "Écart avec l'horloge : 40 ms");
  assert.equal(listenHint({ ...base, kind: "files", fileMissing: true }, "x"), "Fichier du conducteur introuvable");
});

test("a stream that does not answer says so while listening", () => {
  const down: ListenState = {
    muted: false,
    kind: "icecast",
    fileMissing: false,
    fileLoading: false,
    streamDown: true,
    startsInS: null,
    lagMs: null,
  };
  assert.equal(listenHint(down, "x"), "Le flux ne répond pas : le casque réessaie seul");
  assert.equal(listenHint({ ...down, kind: "harbor" }, "x"), "Le flux ne répond pas : le casque réessaie seul");
  // Muet, le bouton propose d'écouter : l'échec se dira à l'écoute.
  assert.equal(listenHint({ ...down, muted: true }, "Antenne publique"), "Écouter au casque : Antenne publique");
});
