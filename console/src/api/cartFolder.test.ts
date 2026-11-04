import assert from "node:assert/strict";
import test from "node:test";
import { cartFolderName, finderRel } from "./cartFolder.ts";

test("the folder of a bac is its number, then its title, as the engine names it", () => {
  assert.equal(cartFolderName(12, "Nouveautes"), "12-Nouveautes");
  // Comme slug_title du moteur : un caractère hors de A-Z, a-z, 0-9, « . », « _ »
  // et « - » devient un tiret, une suite de tels caractères aussi.
  assert.equal(cartFolderName(12, "Nouveautés été"), "12-Nouveaut-s-t");
  assert.equal(cartFolderName(4, "Pubs / Été 2026"), "4-Pubs-t-2026");
  assert.equal(cartFolderName(7, "  _Matinale. "), "7-Matinale");
  assert.equal(cartFolderName(9, "Live_set-2.0"), "9-Live_set-2.0");
  assert.equal(cartFolderName(3, "  "), "3-cart");
  assert.equal(cartFolderName(5, "éé"), "5-cart");
});

test("the station folder and Dropbox show it under Bacs/", () => {
  assert.equal(finderRel(12, "Nouveautés"), "Bacs/12-Nouveaut-s");
});
