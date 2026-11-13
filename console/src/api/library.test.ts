import assert from "node:assert/strict";
import test from "node:test";
import { TAB_QUERY, deskKindFromHit, legacyRetry, type LibraryHit } from "./library.ts";

const hit = (fields: Partial<LibraryHit>): LibraryHit => ({
  id: "a",
  path: "x/a.mp3",
  title: "A",
  artist: "",
  kind: "son",
  duration: 0,
  ...fields,
});

test("the tabs ask the catalogue without naming a folder of the bank", () => {
  assert.deepEqual(TAB_QUERY.archives, { zone: "collections" });
  assert.deepEqual(TAB_QUERY.habillage, { zone: "habillage", habillage: "beds,stings,sfx" });
  for (const query of Object.values(TAB_QUERY)) {
    for (const value of Object.values(query)) assert.doesNotMatch(value, /\//);
  }
});

test("an older catalogue, which ignores zone, is asked again by folder", () => {
  // It answers without the filters it took.
  assert.deepEqual(legacyRetry("archives", undefined), { top: "20-archives" });
  assert.ok(legacyRetry("habillage", undefined)?.folder);
  // A catalogue that took them is not asked again, nor a tab without a folder.
  assert.equal(legacyRetry("archives", ["zone"]), null);
  assert.equal(legacyRetry("musique", undefined), null);
  assert.equal(legacyRetry("all", undefined), null);
});

test("a title of the rotation is music on the desk", () => {
  assert.equal(deskKindFromHit(hit({ zone: "rotation", grouping: "" })), "musique");
  assert.equal(deskKindFromHit(hit({ grouping: "rotation" })), "musique");
  assert.equal(deskKindFromHit(hit({ zone: "collections", grouping: "jazz", folder: "10-rotation" })), "son");
  assert.equal(deskKindFromHit(hit({ kind: "jingle", zone: "rotation" })), "jingle");
  // An older catalogue says no zone: its folder is read.
  assert.equal(deskKindFromHit(hit({ folder: "10-rotation/vrac" })), "musique");
  assert.equal(deskKindFromHit(hit({ folder: "20-archives/jazz" })), "son");
});
