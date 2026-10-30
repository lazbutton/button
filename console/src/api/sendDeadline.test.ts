import assert from "node:assert/strict";
import test from "node:test";
import { UPLOAD_IDLE_MS, withIdleDeadline } from "./sendDeadline.ts";

class NoAnswer extends Error {}
const late = () => new NoAnswer();

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
