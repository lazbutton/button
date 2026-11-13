import assert from "node:assert/strict";
import test from "node:test";
import { identCart, isHabillageCart, relayUrlOk, cartMatchesBacFilter, habillageFoldersOf } from "./cartFlags.ts";
import type { Cart } from "./types.ts";

test("ident pads follow the flag, then a cart still named Jingles", () => {
  const named = { id: 1, title: "Jingles", ident_pads: false } as Cart;
  const flagged = { id: 2, title: "Virgules", ident_pads: true } as Cart;
  assert.equal(identCart([named, flagged])?.id, 2);
  assert.equal(identCart([named])?.id, 1);
  assert.equal(identCart([])?.id, undefined);
});

test("habillage is a bank folder, relay urls need a path", () => {
  assert.equal(isHabillageCart({ bank_folder: "30-habillage/ids" } as Cart), true);
  assert.equal(isHabillageCart({ bank_folder: "10-rotation" } as Cart), false);
  assert.equal(relayUrlOk("https://radio.exemple/flux.mp3"), true);
  assert.equal(relayUrlOk("https://radio.exemple"), false);
  assert.equal(relayUrlOk("notaurl"), false);
});

test("bac filters keep each cart once in the visible list", () => {
  const file = { mode: "playlist_loop", bank_folder: "" } as Cart;
  const jingle = { mode: "random", bank_folder: "30-habillage/jingles" } as Cart;
  const relay = { mode: "relay", bank_folder: "" } as Cart;
  assert.equal(cartMatchesBacFilter(jingle, "tous"), true);
  assert.equal(cartMatchesBacFilter(jingle, "fichiers"), true);
  assert.equal(cartMatchesBacFilter(jingle, "habillage"), true);
  assert.equal(cartMatchesBacFilter(jingle, "relais"), false);
  assert.equal(cartMatchesBacFilter(file, "habillage"), false);
  assert.equal(cartMatchesBacFilter(file, "fichiers"), true);
  assert.equal(cartMatchesBacFilter(relay, "fichiers"), false);
  assert.equal(cartMatchesBacFilter(relay, "relais"), true);
});

test("the engine says a bac is habillage; an older engine leaves its path to read", () => {
  assert.equal(isHabillageCart({ bank_folder: "ailleurs/x", bank_zone: "habillage" } as Cart), true);
  assert.equal(isHabillageCart({ bank_folder: "30-habillage/ids", bank_zone: "bacs" } as Cart), false);
  assert.equal(isHabillageCart({ bank_folder: "", bank_zone: null } as Cart), false);
  assert.equal(isHabillageCart({ bank_folder: "30-habillage/ids" } as Cart), true);
});

test("the folders of habillage come from the engine, else the ones an older engine has", () => {
  assert.deepEqual(habillageFoldersOf({ habillage: ["habillage/jingles", "habillage/sfx"] }), [
    "habillage/jingles",
    "habillage/sfx",
  ]);
  const older = habillageFoldersOf({});
  assert.equal(older.length, 6);
  assert.deepEqual(habillageFoldersOf(null), older);
  assert.deepEqual(habillageFoldersOf({ habillage: [] }), older);
});
