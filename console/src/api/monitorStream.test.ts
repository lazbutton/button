import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { answerWithin, playedSeconds, readStream, type StreamWatch } from "./monitorStream.ts";

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

/** Une demande au serveur du flux, réglée à la main. */
function request<T>() {
  let answer!: (value: T) => void;
  let fail!: (error: unknown) => void;
  const pending = new Promise<T>((resolve, reject) => {
    answer = resolve;
    fail = reject;
  });
  return { pending, answer, fail };
}

test("a server that never answers: the wait gives up after ms", async () => {
  const req = request<string>();
  let gaveUp = 0;
  let settled = false;
  const wait = answerWithin(req.pending, 8000, () => {
    gaveUp += 1;
  });
  void wait.catch(() => undefined).finally(() => {
    settled = true;
  });
  mock.timers.tick(7999);
  await settle();
  assert.equal(gaveUp, 0);
  assert.equal(settled, false);
  mock.timers.tick(1);
  assert.equal(gaveUp, 1);
  await assert.rejects(wait, /timeout/);
});

test("an answer in time goes through, and nothing is given up", async () => {
  const req = request<string>();
  let gaveUp = 0;
  const wait = answerWithin(req.pending, 8000, () => {
    gaveUp += 1;
  });
  mock.timers.tick(7999);
  req.answer("en-têtes");
  assert.equal(await wait, "en-têtes");
  // La réponse arrivée, le délai ne coupe plus rien.
  mock.timers.tick(60_000);
  assert.equal(gaveUp, 0);
});

test("a refusal in time goes through as is", async () => {
  const req = request<string>();
  let gaveUp = 0;
  const wait = answerWithin(req.pending, 8000, () => {
    gaveUp += 1;
  });
  const refused = new TypeError("Failed to fetch");
  req.fail(refused);
  await assert.rejects(wait, (error) => error === refused);
  mock.timers.tick(60_000);
  assert.equal(gaveUp, 0);
});

test("a request cut by the give-up fails late, without surfacing", async () => {
  // L'abandon coupe la demande, qui échoue à son tour, comme un fetch qu'on
  // abandonne : l'attente, elle, a déjà échoué.
  const req = request<string>();
  const wait = answerWithin(req.pending, 8000, () =>
    req.fail(new DOMException("The operation was aborted.", "AbortError")),
  );
  mock.timers.tick(8000);
  await assert.rejects(wait, /timeout/);
});

test("what the element played is the sum of its played ranges", () => {
  const ranges = (...pairs: [number, number][]) => ({
    length: pairs.length,
    start: (i: number) => pairs[i][0],
    end: (i: number) => pairs[i][1],
  });
  assert.equal(playedSeconds(ranges()), 0);
  // Rattraper le direct saute en avant : l'élément a alors deux plages jouées.
  assert.equal(playedSeconds(ranges([0, 1.5], [4, 6])), 3.5);
});
