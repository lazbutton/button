import assert from "node:assert/strict";
import test from "node:test";
import { isPlayoutUnavailable } from "./playoutUnavailable.ts";

test("the engine says its playout did not answer a gesture", () => {
  assert.equal(isPlayoutUnavailable(502, "playout_unavailable"), true);
});

test("any other 502 stays an automate that does not answer", () => {
  assert.equal(isPlayoutUnavailable(502, "scheduler_unavailable"), false);
  assert.equal(isPlayoutUnavailable(502, "<html>\r\n<head><title>502 Bad Gateway</title></head>"), false);
  assert.equal(isPlayoutUnavailable(502, undefined), false);
});

test("the code counts only with its status", () => {
  assert.equal(isPlayoutUnavailable(504, "playout_unavailable"), false);
  assert.equal(isPlayoutUnavailable(400, "playout_unavailable"), false);
});
