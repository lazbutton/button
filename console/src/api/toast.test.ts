import assert from "node:assert/strict";
import test from "node:test";
import {
  RESUME_FLOOR_MS,
  TONE_LABEL,
  clockLeft,
  pauseClock,
  resumeClock,
  startClock,
  toastDuration,
} from "./toast.ts";

test("a short confirmation stays long enough to be noticed", () => {
  assert.equal(toastDuration("Bac enregistré.", "success"), 4000);
  assert.equal(toastDuration("", "info"), 4000);
});

test("a longer message stays the time it takes to read it", () => {
  const short = toastDuration("« Matinale » créée.", "success");
  const long = toastDuration(
    "Banque « Archives du samedi » créée : les envois iront dans 20-archives/archives-du-samedi.",
    "success",
  );
  assert.equal(short, 4000);
  assert.equal(long, 2000 + 13 * 350);
});

test("a failure stays longer than a confirmation of the same length", () => {
  const text = "L’automate ne répond pas. Réessaie dans un instant.";
  assert.equal(toastDuration(text, "error"), 8000);
  assert.ok(toastDuration(text, "error") > toastDuration(text, "success"));

  const long =
    "Une heure type garde au moins une étape. Les changements restent à l'écran : corrige, ils repartiront au geste suivant.";
  assert.equal(toastDuration(long, "error"), (2000 + 20 * 350) * 1.5);
  assert.ok(toastDuration(long, "error") > toastDuration(long, "info"));
});

test("a message with a button leaves the time to use it", () => {
  assert.equal(toastDuration("« Jingle grave » retiré de la file.", "success", true), 8000);
  assert.equal(toastDuration("Coupure :20 retirée.", "info", true), 8000);
});

test("no message stays forever", () => {
  const endless = Array.from({ length: 200 }, () => "mot").join(" ");
  assert.equal(toastDuration(endless, "success"), 20_000);
  assert.equal(toastDuration(endless, "error", true), 20_000);
});

test("every tone has a name for a screen reader", () => {
  assert.deepEqual(TONE_LABEL, { success: "Succès", error: "Erreur", info: "Information" });
});

test("a running countdown loses the time that passes", () => {
  const clock = startClock(8000, 1000);
  assert.equal(clockLeft(clock, 1000), 8000);
  assert.equal(clockLeft(clock, 4000), 5000);
  assert.equal(clockLeft(clock, 60_000), 0);
});

test("a paused countdown keeps what was left, however long the pause", () => {
  const paused = pauseClock(startClock(8000, 1000), 4000);
  assert.deepEqual(paused, { left: 5000, since: null });
  assert.equal(clockLeft(paused, 90_000), 5000);
  // Une seconde pause ne retire rien de plus.
  assert.equal(pauseClock(paused, 95_000), paused);

  const resumed = resumeClock(paused, 100_000);
  assert.deepEqual(resumed, { left: 5000, since: 100_000 });
  assert.equal(clockLeft(resumed, 102_000), 3000);
  // Déjà reparti : rien ne le relance.
  assert.equal(resumeClock(resumed, 101_000), resumed);
});

test("a message left at its last instant stays a moment more", () => {
  const paused = pauseClock(startClock(4000, 0), 3900);
  assert.equal(paused.left, 100);
  const resumed = resumeClock(paused, 10_000);
  assert.equal(clockLeft(resumed, 10_000), RESUME_FLOOR_MS);
});

test("a message shown in a hidden tab waits to be seen", () => {
  const waiting = startClock(4000, 0, true);
  assert.equal(clockLeft(waiting, 3_600_000), 4000);
  assert.equal(clockLeft(resumeClock(waiting, 3_600_000), 3_601_000), 3000);
});
