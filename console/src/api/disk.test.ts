import assert from "node:assert/strict";
import test from "node:test";
import { diskAlert, diskLabel, usedRatio } from "./disk.ts";

const GIB = 1024 ** 3;

test("le libellé est en Go, comme df", () => {
  assert.equal(diskLabel(12 * GIB, 40 * GIB), "12 Go libres sur 40");
  assert.equal(diskLabel(1.5 * GIB, 40 * GIB), "1,5 Go libres sur 40");
});

test("alerte sous 20 % libres", () => {
  assert.equal(diskAlert(7 * GIB, 40 * GIB), true);
  assert.equal(diskAlert(8 * GIB, 40 * GIB), false);
  assert.equal(usedRatio(32 * GIB, 40 * GIB), 0.8);
});
