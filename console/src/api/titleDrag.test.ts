import assert from "node:assert/strict";
import test from "node:test";
import { decodeIds, draggedIds, dropAction, dropHint, encodeIds, takesTitles } from "./titleDrag.ts";

test("a drag takes the selection when the row is in it, else the row alone", () => {
  assert.deepEqual(draggedIds(2, new Set([1, 2, 3])), [1, 2, 3]);
  assert.deepEqual(draggedIds(4, new Set([1, 2])), [4]);
  assert.deepEqual(decodeIds(encodeIds([3, 5])), [3, 5]);
  assert.deepEqual(decodeIds("des fichiers"), []);
  assert.deepEqual(decodeIds('[1, "x", 2.5]'), [1]);
});

test("a group with a name takes titles; « Sans … » and the whole bank do not", () => {
  assert.equal(takesTitles("famille", "jazz"), true);
  assert.equal(takesTitles("famille", ""), false);
  assert.equal(takesTitles("collection", null), false);
  // Les étiquettes de la station (FON-74) ne sont pas une cible de dépôt.
  assert.equal(takesTitles("etiquette", "nuit"), false);
});

test("on a family, the lot of fiches; on a collection, a move from one collection", () => {
  const nuit = [{ collection: "nuit" }, { collection: "nuit" }];
  assert.deepEqual(dropAction("famille", "jazz", "Jazz", nuit), { kind: "edit", field: "famille", value: "jazz" });
  assert.deepEqual(dropAction("artist", "Orage", "Orage", nuit), { kind: "edit", field: "artist", value: "Orage" });
  assert.deepEqual(dropAction("collection", "concerts", "Concerts", nuit), { kind: "move", from: "nuit", to: "concerts" });
});

test("a refused target says why", () => {
  assert.equal(dropAction("collection", "nuit", "Nuit", [{ collection: "nuit" }]).kind, "refuse");
  assert.match(
    (dropAction("collection", "nuit", "Nuit", [{ collection: "rotation" }, { collection: "concerts" }]) as { reason: string }).reason,
    /plusieurs collections/,
  );
  assert.match((dropAction("album", "", "Sans album", [{ collection: "nuit" }]) as { reason: string }).reason, /un groupe qui a un nom/);
});

test("the group says what a drop does", () => {
  assert.equal(dropHint("collection", "Nuit"), "Déposer pour déplacer vers « Nuit »");
  assert.equal(dropHint("famille", "Jazz"), "Déposer pour leur donner la famille « Jazz »");
});
