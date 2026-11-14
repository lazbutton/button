import assert from "node:assert/strict";
import test from "node:test";
import { listenLink, listenLinkBody, listenLinkChanged, listenLinkForm } from "./listenLink.ts";
import type { LiveSnapshot, ListenLinkSettings } from "./types.ts";

const OFF: ListenLinkSettings = { enabled: false, url: null, key_set: false };
const playing = (extra: Partial<LiveSnapshot> = {}): LiveSnapshot => ({ status: "playing", title: "Titre", ...extra });

test("le lien du titre en cours : une adresse web sûre, d'un relevé frais", () => {
  const url = "https://liens.radio.example/l/abc123";
  assert.equal(listenLink(playing({ listen_url: url }), false), url);
  assert.equal(listenLink(playing(), false), null);
  assert.equal(listenLink(null, false), null);
  // Le dernier titre connu d'un moteur muet n'est plus celui du moment.
  assert.equal(listenLink(playing({ listen_url: url }), true), null);
  assert.equal(listenLink({ status: "offline", listen_url: url }, false), null);
});

test("jamais un lien qui n'est pas une adresse web", () => {
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "/relatif", "https://a b.example", ""]) {
    assert.equal(listenLink(playing({ listen_url: bad }), false), null, bad);
  }
});

test("le formulaire ne relit jamais la clé", () => {
  const form = listenLinkForm({ enabled: true, url: "https://liens.radio.example", key_set: true });
  assert.deepEqual(form, { enabled: true, url: "https://liens.radio.example", key: "", clearKey: false });
  assert.equal(listenLinkChanged(form, { enabled: true, url: "https://liens.radio.example", key_set: true }), false);
  // Sans saisie, le PUT ne dit rien de la clé : le moteur la garde.
  assert.deepEqual(listenLinkBody(form), { enabled: true, url: "https://liens.radio.example" });
});

test("une clé saisie part, une clé effacée part vide", () => {
  const settings = { ...OFF, key_set: true };
  const typed = { ...listenLinkForm(settings), key: " change-me " };
  assert.equal(listenLinkChanged(typed, settings), true);
  assert.equal(listenLinkBody(typed).key, "change-me");
  const cleared = { ...listenLinkForm(settings), clearKey: true };
  assert.equal(listenLinkChanged(cleared, settings), true);
  assert.equal(listenLinkBody(cleared).key, "");
});

test("allumer ou changer l'adresse est une modification", () => {
  const form = listenLinkForm(OFF);
  assert.equal(listenLinkChanged(form, OFF), false);
  assert.equal(listenLinkChanged({ ...form, enabled: true }, OFF), true);
  assert.equal(listenLinkChanged({ ...form, url: "https://liens.radio.example" }, OFF), true);
});
