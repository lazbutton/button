import assert from "node:assert/strict";
import test from "node:test";
import { apiSharedGet } from "./jsonCache.ts";
import { READ_DEADLINE_MS, withBodyDeadline, withDeadline } from "./readDeadline.ts";

class Unavailable extends Error {}
const late = () => new Unavailable();

// Le moteur a accepté la connexion, puis ne répond plus.
const silent = () => new Promise<never>(() => {});

// Laisse passer les promesses en attente, sans avancer l'horloge simulée.
const settle = () => new Promise((resolve) => setImmediate(resolve));

// Un son dont le parcours fait venir les morceaux un à un.
function sound(type = "audio/mpeg") {
  let source: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      source = controller;
    },
  });
  const response = new Response(body, { headers: { "Content-Type": type } });
  if (!source) throw new Error("stream");
  return { response, source };
}

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

test("a sound that keeps coming is never cut, and arrives whole", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { response, source } = sound();
  const read = withBodyDeadline(READ_DEADLINE_MS, async () => response, late);

  // Cinq minutes sur un réseau lent : un morceau toutes les 9 s.
  for (let elapsed = 0; elapsed < 5 * 60_000; elapsed += 9_000) {
    t.mock.timers.tick(9_000);
    source.enqueue(new Uint8Array(1_024));
    await settle();
  }
  source.close();
  const blob = await read;
  assert.equal(blob.size, 34 * 1_024);
  // L'élément audio lit le son par son type, comme avant.
  assert.equal(blob.type, "audio/mpeg");
});

test("a sound that stops coming fails after the delay, and is aborted", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { response, source } = sound();
  let signal: AbortSignal | undefined;
  let failed: unknown;
  const read = withBodyDeadline(
    READ_DEADLINE_MS,
    async (given) => {
      signal = given;
      return response;
    },
    late,
  );
  read.catch((error: unknown) => {
    failed = error;
  });

  await settle();
  source.enqueue(new Uint8Array(1_024));
  await settle();
  // Le moteur se bloque au milieu du son : plus un octet ne vient.
  t.mock.timers.tick(READ_DEADLINE_MS - 1);
  await settle();
  assert.equal(failed, undefined);
  assert.equal(signal?.aborted, false);
  t.mock.timers.tick(1);
  await assert.rejects(read, Unavailable);
  assert.equal(signal?.aborted, true);
});

test("a sound whose answer never comes fails at the delay", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const read = withBodyDeadline(READ_DEADLINE_MS, () => silent(), late);

  t.mock.timers.tick(READ_DEADLINE_MS);
  await assert.rejects(read, Unavailable);
});

test("a sound cut on the way fails like a silent one", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { response, source } = sound();
  const read = withBodyDeadline(READ_DEADLINE_MS, async () => response, late);

  await settle();
  source.enqueue(new Uint8Array(1_024));
  // La connexion tombe au milieu du son.
  source.error(new TypeError("network error"));
  await assert.rejects(read, Unavailable);
});

test("a sound refused by its answer keeps its own error", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  // Une session expirée reste une session expirée, pas un moteur injoignable.
  class Expired extends Error {}
  const read = withBodyDeadline(
    READ_DEADLINE_MS,
    async () => {
      throw new Expired();
    },
    late,
  );

  await assert.rejects(read, Expired);
});
