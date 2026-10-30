import assert from "node:assert/strict";
import test from "node:test";
import { isEngineUnreachable, isUnreachableStatus } from "./engineUnreachable.ts";

// La page de nginx devant un moteur arrêté, dont client.ts garde le début.
const NGINX_502 = "<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>";
const NGINX_504 = "<html>\r\n<head><title>504 Gateway Time-out</title></head>\r\n<body>\r\n<center><h1>504 Gateway Time-out</h1></center>";

test("nginx in front of a stopped or stuck engine means the automate does not answer", () => {
  assert.equal(isEngineUnreachable(502, NGINX_502), true);
  assert.equal(isEngineUnreachable(504, NGINX_504), true);
});

test("a gateway status says so, whatever the body", () => {
  for (const status of [502, 503, 504]) {
    assert.equal(isEngineUnreachable(status, undefined), true, String(status));
    assert.equal(isEngineUnreachable(status, "Bad Gateway"), true, String(status));
  }
  // Le moteur lui-même : son scheduler, ou son disque, ne répond pas.
  assert.equal(isEngineUnreachable(502, "scheduler_unavailable"), true);
  assert.equal(isEngineUnreachable(503, "disque illisible"), true);
});

test("an error page in HTML is never a message to show", () => {
  assert.equal(isEngineUnreachable(500, "<!doctype html>\n<html lang=en>\n<title>500 Internal Server Error</title>"), true);
  assert.equal(isEngineUnreachable(404, "<html>\r\n<head><title>404 Not Found</title></head>"), true);
});

test("the engine's own errors keep their message", () => {
  assert.equal(isEngineUnreachable(400, "Le titre est obligatoire."), false);
  assert.equal(isEngineUnreachable(404, "The requested URL was not found on the server."), false);
  assert.equal(isEngineUnreachable(409, "Un bac porte déjà ce nom."), false);
  assert.equal(isEngineUnreachable(500, "server_error"), false);
});

test("on /login, a refused password stays refused, even in HTML", () => {
  for (const status of [502, 503, 504]) assert.equal(isUnreachableStatus(status), true, String(status));
  // Le moteur refuse le mot de passe par une page <pre> : 401, ou 400 s'il manque.
  assert.equal(isUnreachableStatus(401), false);
  assert.equal(isUnreachableStatus(400), false);
});
