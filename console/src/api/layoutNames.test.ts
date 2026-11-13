import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  LEGACY_HABILLAGE_FOLDERS,
  legacyCartIdFromPath,
  legacyIsHabillageFolder,
  legacyIsRotationFolder,
} from "./legacyLayout.ts";

const SRC = fileURLToPath(new URL("..", import.meta.url));
// The folders of the bank on a station's disk. The console reads them only in
// legacyLayout.ts, for an engine or a catalogue that does not say what a bac or
// a title is yet (ADR 0019).
const FOLDERS = /(00-inbox|10-rotation|20-archives|30-habillage|40-emissions|50-carts|90-trash)/;
// The demo data play the engine and the catalogue: they may name paths.
const SERVER_SIDE = ["mock/"];
// A comment, in a page another session works on: it goes with that work.
const KNOWN = ["pages/ImporterPage.tsx"];

function sources(folder: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) found.push(...sources(path));
    else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.ts$/.test(entry.name)) found.push(path);
  }
  return found;
}

test("the console names no folder of the bank, but in legacyLayout.ts", () => {
  const strays: string[] = [];
  for (const path of sources(SRC)) {
    const rel = relative(SRC, path).split("\\").join("/");
    if (rel === "api/legacyLayout.ts" || KNOWN.includes(rel)) continue;
    if (SERVER_SIDE.some((prefix) => rel.startsWith(prefix))) continue;
    readFileSync(path, "utf8")
      .split("\n")
      .forEach((line, index) => {
        if (FOLDERS.test(line)) strays.push(`${rel}:${index + 1}: ${line.trim()}`);
      });
  }
  assert.deepEqual(strays, []);
});

test("an older engine's path still says a bac of habillage, and the bac of a sound", () => {
  assert.equal(legacyIsHabillageFolder("30-habillage/jingles"), true);
  assert.equal(legacyIsHabillageFolder("50-carts/4"), false);
  assert.equal(legacyIsHabillageFolder(null), false);
  assert.equal(LEGACY_HABILLAGE_FOLDERS.every(legacyIsHabillageFolder), true);
  assert.equal(legacyCartIdFromPath("/media/50-carts/4/a.mp3"), 4);
  assert.equal(legacyCartIdFromPath("/media/30-habillage/jingles/a.mp3"), 0);
  assert.equal(legacyCartIdFromPath(""), 0);
});

test("an older catalogue's folder still says a title of the rotation", () => {
  assert.equal(legacyIsRotationFolder("10-rotation"), true);
  assert.equal(legacyIsRotationFolder("10-rotation/vrac"), true);
  assert.equal(legacyIsRotationFolder("20-archives/jazz"), false);
  assert.equal(legacyIsRotationFolder(undefined), false);
});
