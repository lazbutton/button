import assert from "node:assert/strict";
import test from "node:test";
import { DAY_SHORT_FR } from "./agendaView.ts";
import { emissionPillLabel, nextEmissionLabel, nextEmissionWhen } from "./emissionMeta.ts";
import type { EmissionNext } from "./types";

// Lundi 16 novembre 2026 : QG, chaque lundi de 20:00 à 22:00.
const tonight: EmissionNext = {
  id: 1,
  title: "QG",
  artist: "avec l'équipe",
  scope: "weekly",
  at: "2026-11-16T20:00:00+01:00",
  until: "2026-11-16T22:00:00+01:00",
  day_of_week: 0,
  start_minute: 20 * 60,
  end_minute: 22 * 60,
};

test("le prochain direct porte sa date : annulé ce soir, celui de la semaine d'après se distingue", () => {
  assert.equal(nextEmissionWhen(tonight, DAY_SHORT_FR), "Lun 16 · 20:00");
  const nextWeek = { ...tonight, at: "2026-11-23T20:00:00+01:00", until: "2026-11-23T22:00:00+01:00" };
  assert.equal(nextEmissionLabel(nextWeek, DAY_SHORT_FR), "Lun 23 · 20:00 · QG");
  assert.notEqual(nextEmissionLabel(nextWeek, DAY_SHORT_FR), nextEmissionLabel(tonight, DAY_SHORT_FR));
});

test("un direct de l'Agenda se date comme une émission hebdo", () => {
  const live: EmissionNext = {
    id: 7,
    title: "Concert",
    artist: "lea",
    scope: "dated",
    kind: "live",
    at: "2026-11-19T21:00:00+01:00",
    until: "2026-11-19T23:00:00+01:00",
    day_of_week: 3,
    start_minute: 21 * 60,
  };
  assert.equal(nextEmissionLabel(live, DAY_SHORT_FR), "Jeu 19 · 21:00 · Concert");
  // Sans le jour ni la minute, la date suffit.
  const bare: EmissionNext = { id: 7, title: "Concert", artist: "lea", at: live.at };
  assert.equal(nextEmissionLabel(bare, DAY_SHORT_FR), "Jeu 19 · 21:00 · Concert");
});

test("l'heure se lit à Paris, quel que soit le décalage rendu", () => {
  assert.equal(nextEmissionWhen({ ...tonight, at: "2026-11-16T19:00:00Z" }, DAY_SHORT_FR), "Lun 16 · 20:00");
  // 23:30 en UTC, c'est déjà le lendemain à Paris.
  assert.equal(nextEmissionWhen({ ...tonight, at: "2026-11-15T23:30:00Z" }, DAY_SHORT_FR), "Lun 16 · 00:30");
  // Le jour du passage à l'heure d'hiver.
  assert.equal(nextEmissionWhen({ ...tonight, at: "2026-10-25T20:00:00+01:00" }, DAY_SHORT_FR), "Dim 25 · 20:00");
});

test("sans heure lisible, le jour et l'heure de l'émission hebdo, sans date", () => {
  assert.equal(nextEmissionLabel({ ...tonight, at: "bientôt" }, DAY_SHORT_FR), "Lun · 20:00 · QG");
  assert.equal(nextEmissionLabel({ id: 1, title: "QG", artist: "", at: "" }, DAY_SHORT_FR), "QG");
});

test("la pastille du conducteur dit l'émission en cours avant la prochaine", () => {
  assert.equal(
    emissionPillLabel({ title: "Matinale", state: "waiting", start_minute: 8 * 60 }, tonight, DAY_SHORT_FR),
    "08:00 en attente · Matinale",
  );
  assert.equal(emissionPillLabel(null, tonight, DAY_SHORT_FR), "Lun 16 · 20:00 · QG");
  assert.equal(emissionPillLabel(null, null, DAY_SHORT_FR), null);
});
