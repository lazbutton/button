import assert from "node:assert/strict";
import test from "node:test";
import { isUnknownRoute } from "./unknownRoute.ts";

// Ce que répond le moteur à une route .json qu'il ne connaît pas.
const WERKZEUG =
  "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.";

test("a route the engine does not know means an older engine", () => {
  assert.equal(isUnknownRoute(404, WERKZEUG), true);
});

test("a missing resource keeps its own message", () => {
  assert.equal(isUnknownRoute(404, "Émission introuvable."), false);
  assert.equal(isUnknownRoute(404, "Cart 3 not found"), false);
  assert.equal(isUnknownRoute(404, "not_found"), false);
  assert.equal(isUnknownRoute(404, undefined), false);
});

test("only a 404 says so", () => {
  assert.equal(isUnknownRoute(405, WERKZEUG), false);
  assert.equal(isUnknownRoute(500, WERKZEUG), false);
});
