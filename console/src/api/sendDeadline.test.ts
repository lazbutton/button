import assert from "node:assert/strict";
import test from "node:test";
import { UPLOAD_IDLE_MS, withIdleDeadline, withUploadDeadline } from "./sendDeadline.ts";

class NoAnswer extends Error {}
const late = () => new NoAnswer();

// Le dépôt n'a pas atteint le moteur, ou il l'a peut-être traité.
class Unsent extends Error {}
class Unanswered extends Error {}
const unsent = () => new Unsent();
const unanswered = () => new Unanswered();

// Le moteur a reçu l'envoi, puis ne répond plus.
const silent = () => new Promise<never>(() => {});

test("an upload that keeps moving is never cut, and its answer is kept", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let alive = () => {};
  let answer: (value: string) => void = () => {};
  const upload = withIdleDeadline(
    UPLOAD_IDLE_MS,
    (_signal, given) => {
      alive = given;
      return new Promise<string>((resolve) => {
        answer = resolve;
      });
    },
    late,
  );

  // Cinq minutes sur un réseau lent : des octets partent toutes les 20 s.
  for (let elapsed = 0; elapsed < 5 * 60_000; elapsed += 20_000) {
    t.mock.timers.tick(20_000);
    alive();
  }
  answer("ok");
  assert.equal(await upload, "ok");
});

test("an upload that stops moving fails after the idle delay, and is aborted", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  let alive = () => {};
  const upload = withIdleDeadline(
    UPLOAD_IDLE_MS,
    (given, beat) => {
      signal = given;
      alive = beat;
      return silent();
    },
    late,
  );

  t.mock.timers.tick(UPLOAD_IDLE_MS - 1);
  // Le dernier octet part : la réponse a tout le délai.
  alive();
  t.mock.timers.tick(UPLOAD_IDLE_MS - 1);
  assert.equal(signal?.aborted, false);
  t.mock.timers.tick(1);
  await assert.rejects(upload, NoAnswer);
  assert.equal(signal?.aborted, true);
});

test("an upload that never moves fails after the idle delay", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const upload = withIdleDeadline(UPLOAD_IDLE_MS, () => silent(), late);

  t.mock.timers.tick(UPLOAD_IDLE_MS);
  await assert.rejects(upload, NoAnswer);
});

test("an error in time keeps its own error", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  // Un envoi trop lourd pour nginx reste un envoi trop lourd, pas un moteur muet.
  class TooLarge extends Error {}
  const upload = withIdleDeadline(
    UPLOAD_IDLE_MS,
    async () => {
      throw new TooLarge();
    },
    late,
  );

  await assert.rejects(upload, TooLarge);
});

test("a sign of life after the deadline does not restart it", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let lates = 0;
  let alive = () => {};
  const upload = withIdleDeadline(
    1_000,
    (_signal, given) => {
      alive = given;
      return silent();
    },
    () => {
      lates += 1;
      return new NoAnswer();
    },
  );

  t.mock.timers.tick(1_000);
  await assert.rejects(upload, NoAnswer);
  alive();
  t.mock.timers.tick(1_000);
  assert.equal(lates, 1);
});

test("an upload stalled before its last byte is cut, and never reached the engine", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  let alive = () => {};
  const upload = withUploadDeadline(
    UPLOAD_IDLE_MS,
    (given, beat) => {
      signal = given;
      alive = beat;
      return silent();
    },
    unsent,
    unanswered,
  );

  // Le réseau perd les paquets à 40 % : plus un octet ne part.
  t.mock.timers.tick(20_000);
  alive();
  t.mock.timers.tick(UPLOAD_IDLE_MS);
  await assert.rejects(upload, Unsent);
  assert.equal(signal?.aborted, true);
});

test("after its last byte, an upload stops waiting without being cut", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  let sent = () => {};
  const upload = withUploadDeadline(
    UPLOAD_IDLE_MS,
    (given, _alive, done) => {
      signal = given;
      sent = done;
      return silent();
    },
    unsent,
    unanswered,
  );
  let settled = false;
  upload.catch(() => {
    settled = true;
  });

  // Le dernier octet part juste avant le délai : la réponse a tout le délai.
  t.mock.timers.tick(UPLOAD_IDLE_MS - 1);
  sent();
  t.mock.timers.tick(UPLOAD_IDLE_MS - 1);
  await Promise.resolve();
  assert.equal(settled, false);
  t.mock.timers.tick(1);
  await assert.rejects(upload, Unanswered);
  // Le moteur écrit peut-être encore les fichiers : couper laisserait un son tronqué.
  assert.equal(signal?.aborted, false);
});
