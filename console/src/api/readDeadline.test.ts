import assert from "node:assert/strict";
import test from "node:test";
import { apiSharedGet } from "./jsonCache.ts";
import { READ_DEADLINE_MS, withDeadline } from "./readDeadline.ts";

class Unavailable extends Error {}
const late = () => new Unavailable();

// Le moteur a accepté la connexion, puis ne répond plus.
const silent = () => new Promise<never>(() => {});

test("a read that never answers fails at its deadline, and is aborted", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  const read = withDeadline(
    1_000,
    (given) => {
      signal = given;
      return silent();
    },
    late,
  );

  t.mock.timers.tick(999);
  assert.equal(signal?.aborted, false);
  t.mock.timers.tick(1);
  await assert.rejects(read, Unavailable);
  assert.equal(signal?.aborted, true);
});

test("an answer in time is kept, and its deadline stops", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  const value = await withDeadline(
    1_000,
    async (given) => {
      signal = given;
      return { ok: true };
    },
    late,
  );

  assert.deepEqual(value, { ok: true });
  t.mock.timers.tick(1_000);
  assert.equal(signal?.aborted, false);
});

test("an error in time keeps its own error", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  // Une session expirée reste une session expirée, pas un moteur injoignable.
  class Expired extends Error {}
  const read = withDeadline(
    1_000,
    async () => {
      throw new Expired();
    },
    late,
  );

  await assert.rejects(read, Expired);
});

test("polls waiting on a silent read fail with it, then the next poll asks again", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let reads = 0;
  const poll = () =>
    apiSharedGet("/live.json", () =>
      withDeadline(
        READ_DEADLINE_MS,
        () => {
          reads += 1;
          return silent();
        },
        late,
      ),
    );

  // Le pupitre lit /live.json chaque seconde : le sondage suivant attend la lecture pendante.
  const first = poll();
  t.mock.timers.tick(1_000);
  const second = poll();
  assert.equal(reads, 1);
  t.mock.timers.tick(READ_DEADLINE_MS - 1_000);
  await assert.rejects(first, Unavailable);
  await assert.rejects(second, Unavailable);

  // La lecture abandonnée ne retient plus le chemin.
  const third = poll();
  assert.equal(reads, 2);
  t.mock.timers.tick(READ_DEADLINE_MS);
  await assert.rejects(third, Unavailable);
});
