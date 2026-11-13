import assert from "node:assert/strict";
import test from "node:test";
import { collectionsFolderOf } from "./banks.ts";

test("inbox.json says where a collection is born", () => {
  assert.equal(collectionsFolderOf({ collections: { folder: "collections" } }), "collections");
  assert.equal(collectionsFolderOf({ collections: { folder: " collections " } }), "collections");
});

test("an older catalogue does not say it: the folder it has is used", () => {
  assert.equal(collectionsFolderOf({}), "20-archives");
  assert.equal(collectionsFolderOf(null), "20-archives");
  assert.equal(collectionsFolderOf({ collections: { folder: "" } }), "20-archives");
  assert.equal(collectionsFolderOf({ collections: { folder: 3 } }), "20-archives");
});
