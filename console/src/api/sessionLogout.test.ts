import assert from "node:assert/strict";
import test from "node:test";
import { READ_DEADLINE_MS } from "./readDeadline.ts";
import { closeSession } from "./sessionLogout.ts";

// Le moteur a accepté la connexion, puis ne répond plus.
const silent = () => new Promise<never>(() => {});

// Laisse passer les promesses en attente, sans avancer l'horloge simulée.
const settle = () => new Promise((resolve) => setImmediate(resolve));

test("a logout that never answers is given up at the read deadline, and did not reach the engine", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  let closed: boolean | undefined;
  void closeSession((given) => {
    signal = given;
    return silent();
  }).then((value) => {
    closed = value;
  });

  t.mock.timers.tick(READ_DEADLINE_MS - 1);
  await settle();
  // « Se déconnecter » attend encore le moteur.
  assert.equal(closed, undefined);
  t.mock.timers.tick(1);
  await settle();
  assert.equal(closed, false);
  assert.equal(signal?.aborted, true);
});

test("the engine's answer closes the session, even an error", async () => {
  // Le moteur renvoie vers /login : en redirect « manual », une réponse opaque, de statut 0.
  assert.equal(await closeSession(async () => ({ status: 0 })), true);
  // La session était déjà close.
  assert.equal(await closeSession(async () => ({ status: 401 })), true);
  // Le moteur a reçu la demande : la console ne sait pas mieux.
  assert.equal(await closeSession(async () => ({ status: 500 })), true);
});

test("a logout that does not reach the engine says so", async () => {
  // Moteur arrêté, ou qui tarde, derrière nginx.
  for (const status of [502, 503, 504]) {
    assert.equal(await closeSession(async () => ({ status })), false, String(status));
  }
  // Connexion refusée.
  assert.equal(await closeSession(() => Promise.reject(new TypeError("Failed to fetch"))), false);
});
