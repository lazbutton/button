import assert from "node:assert/strict";
import test from "node:test";
import { cookieRefused, cookieRefusedMessage } from "./sessionCookie.ts";

class Unauthenticated extends Error {}

const unauthenticated = (caught: unknown) => caught instanceof Unauthenticated;

test("juste après un mot de passe accepté, seul un défaut de session veut dire cookie refusé", async () => {
  assert.equal(await cookieRefused(async () => ({ csrf_token: "t" }), unauthenticated), false);
  assert.equal(await cookieRefused(() => Promise.reject(new Unauthenticated()), unauthenticated), true);
  // Moteur injoignable : la porte de session le dit, comme avant.
  assert.equal(await cookieRefused(() => Promise.reject(new Error("unavailable")), unauthenticated), false);
});

test("en http://, le cookie Secure est refusé : la console s'ouvre en https://", () => {
  assert.equal(
    cookieRefusedMessage("http:", true),
    "Mot de passe accepté, mais le navigateur a refusé le cookie de session : il ne passe qu’en HTTPS. Ouvre la console avec son adresse en https://.",
  );
});

test("un navigateur qui bloque les cookies : les autoriser, en http:// comme en https://", () => {
  const blocked =
    "Mot de passe accepté, mais le navigateur a refusé le cookie de session. Autorise les cookies pour ce site, puis réessaie.";
  assert.equal(cookieRefusedMessage("http:", false), blocked);
  assert.equal(cookieRefusedMessage("https:", false), blocked);
  // En https://, le cookie Secure passe : le message est le même.
  assert.equal(cookieRefusedMessage("https:", true), blocked);
});
