import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { readStream, type StreamWatch } from "./monitorStream.ts";

beforeEach(() => mock.timers.enable({ apis: ["setTimeout", "Date"] }));
afterEach(() => mock.timers.reset());

/** Une connexion au flux, remplie à la main. `cut` l'interrompt comme l'abandon d'un fetch. */
function connection() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    reader: body.getReader(),
    send: (bytes = 417) => controller.enqueue(new Uint8Array(bytes)),
    close: () => controller.close(),
    cut: () => controller.error(new DOMException("The operation was aborted.", "AbortError")),
  };
}

/** Laisse readStream lire ce qui attend. */
const settle = () => new Promise((resolve) => setImmediate(resolve));

function watched(conn: ReturnType<typeof connection>, over: Partial<StreamWatch> = {}) {
  const seen = { chunks: 0, steady: 0, stalls: 0 };
  const end = readStream(conn.reader, {
    stallMs: 8000,
    steadyMs: 3000,
    alive: () => true,
    stall: () => {
      seen.stalls += 1;
      conn.cut();
    },
    onChunk: () => {
      seen.chunks += 1;
    },
    onSteady: () => {
      seen.steady += 1;
    },
    ...over,
  });
  return { seen, end };
}

test("a server that closes right away: the connection did not hold", async () => {
  const conn = connection();
  const { seen, end } = watched(conn);
  conn.send();
  conn.send();
  conn.close();
  assert.deepEqual(await end, { closed: true, steady: false });
  assert.equal(seen.chunks, 2);
  assert.equal(seen.steady, 0);
  // La connexion finie, sa garde ne coupe plus rien.
  mock.timers.tick(60_000);
  assert.equal(seen.stalls, 0);
});

test("a stream that keeps flowing holds after steadyMs, and is never cut", async () => {
  const conn = connection();
  const { seen, end } = watched(conn);
  for (let ms = 0; ms < 20_000; ms += 100) {
    conn.send();
    await settle();
    assert.equal(seen.steady, ms < 3000 ? 0 : 1, `à ${ms} ms`);
    mock.timers.tick(100);
  }
  assert.equal(seen.stalls, 0);
  conn.close();
  assert.deepEqual(await end, { closed: true, steady: true });
});

test("a stream that stops flowing is cut after stallMs", async () => {
  const conn = connection();
  const { seen, end } = watched(conn);
  conn.send();
  await settle();
  mock.timers.tick(4000);
  // Un paquet vide n'apporte aucun octet.
  conn.send(0);
  await settle();
  mock.timers.tick(3999);
  assert.equal(seen.stalls, 0);
  mock.timers.tick(1);
  assert.equal(seen.stalls, 1);
  assert.deepEqual(await end, { closed: false, steady: false });
});

test("a server that answers, then never sends a byte, is cut too", async () => {
  const conn = connection();
  const { seen, end } = watched(conn);
  mock.timers.tick(8000);
  assert.equal(seen.stalls, 1);
  assert.deepEqual(await end, { closed: false, steady: false });
  assert.equal(seen.chunks, 0);
});

test("a stream that held, then broke, says it had held", async () => {
  const conn = connection();
  const { end } = watched(conn);
  for (let ms = 0; ms <= 5000; ms += 500) {
    conn.send();
    await settle();
    mock.timers.tick(500);
  }
  conn.cut();
  assert.deepEqual(await end, { closed: false, steady: true });
});

test("reading stops once the casque gave up on the connection", async () => {
  const conn = connection();
  let chunks = 0;
  const { end } = watched(conn, {
    alive: () => chunks === 0,
    onChunk: () => {
      chunks += 1;
    },
  });
  conn.send();
  conn.send();
  assert.deepEqual(await end, { closed: false, steady: false });
  assert.equal(chunks, 1);
});
