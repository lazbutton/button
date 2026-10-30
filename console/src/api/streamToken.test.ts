import assert from "node:assert/strict";
import test from "node:test";
import { streamTokenAction, streamTokenLine } from "./streamToken.ts";

test("la date du jeton se lit à l'heure de Paris", () => {
  assert.equal(streamTokenLine(null), "Pas encore de jeton.");
  assert.equal(streamTokenLine("2026-10-30T14:05+01:00"), "Jeton créé le vendredi 30 octobre à 14:05.");
  // l'heure d'été, et un instant donné en UTC
  assert.equal(streamTokenLine("2026-07-01T07:30:00Z"), "Jeton créé le mercredi 1 juillet à 09:30.");
  assert.equal(streamTokenLine("2026-10-31T23:30:00Z"), "Jeton créé le dimanche 1 novembre à 00:30.");
});

test("renouveler un jeton demande une confirmation, pas en créer un", () => {
  assert.equal(streamTokenAction(null, false), "Créer un jeton");
  assert.equal(streamTokenAction("2026-10-30T14:05+01:00", false), "Renouveler");
  assert.equal(streamTokenAction("2026-10-30T14:05+01:00", true), "Renouveler quand même");
});
