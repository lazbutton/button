import assert from "node:assert/strict";
import test from "node:test";
import { isTooManyAttempts, tooManyAttemptsMessage } from "./tooManyAttempts.ts";

test("le moteur, ou nginx, refuse une adresse après trop d'essais", () => {
  assert.equal(isTooManyAttempts(429, "too_many_attempts"), true);
});

test("le code ne compte qu'avec son statut", () => {
  assert.equal(isTooManyAttempts(401, "too_many_attempts"), false);
  assert.equal(isTooManyAttempts(429, undefined), false);
  assert.equal(isTooManyAttempts(429, "<html>\r\n<head><title>429 Too Many Requests</title></head>"), false);
});

test("le formulaire dit combien de minutes attendre, arrondi à la minute du dessus", () => {
  assert.equal(tooManyAttemptsMessage(900), "Trop d’essais. Réessaie dans 15 minutes.");
  assert.equal(tooManyAttemptsMessage(840), "Trop d’essais. Réessaie dans 14 minutes.");
  assert.equal(tooManyAttemptsMessage(841), "Trop d’essais. Réessaie dans 15 minutes.");
  assert.equal(tooManyAttemptsMessage(60), "Trop d’essais. Réessaie dans 1 minute.");
  assert.equal(tooManyAttemptsMessage(1), "Trop d’essais. Réessaie dans 1 minute.");
  assert.equal(tooManyAttemptsMessage(86400), "Trop d’essais. Réessaie dans 1440 minutes.");
});

test("Retry-After compte aussi, un en-tête étant du texte", () => {
  assert.equal(tooManyAttemptsMessage("60"), "Trop d’essais. Réessaie dans 1 minute.");
});

test("sans délai connu, le formulaire dit quand même pourquoi", () => {
  for (const retryIn of [undefined, null, "", "bientôt", 0, -5, Number.NaN]) {
    assert.equal(tooManyAttemptsMessage(retryIn), "Trop d’essais. Réessaie plus tard.");
  }
});
