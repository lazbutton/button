import assert from "node:assert/strict";
import test from "node:test";
import { anchorHint, deskAlert, mmss, ownsSpace, previewUrl, progressLabel, spaceSkips, SKIP_GUARD_MS } from "./antenneDesk.ts";

const free = { tag: "DIV", role: null, editable: false };

test("Space skips on the page, never on a control", () => {
  assert.equal(spaceSkips({ target: free, repeat: false, lastSkipAt: 0, now: 10_000 }), true);
  assert.equal(spaceSkips({ target: null, repeat: false, lastSkipAt: 0, now: 10_000 }), true);
  for (const tag of ["BUTTON", "input", "A", "TEXTAREA", "SELECT"]) {
    assert.equal(spaceSkips({ target: { tag, role: null, editable: false }, repeat: false, lastSkipAt: 0, now: 10_000 }), false, tag);
  }
  assert.equal(spaceSkips({ target: { tag: "DIV", role: "tab", editable: false }, repeat: false, lastSkipAt: 0, now: 10_000 }), false);
  assert.equal(spaceSkips({ target: { tag: "DIV", role: null, editable: true }, repeat: false, lastSkipAt: 0, now: 10_000 }), false);
});

test("controls own Space", () => {
  assert.equal(ownsSpace(null), false);
  assert.equal(ownsSpace(free), false);
  assert.equal(ownsSpace({ tag: "button", role: null, editable: false }), true);
  assert.equal(ownsSpace({ tag: "LI", role: "option", editable: false }), true);
});

test("holding or hammering Space passes one title only", () => {
  assert.equal(spaceSkips({ target: free, repeat: true, lastSkipAt: 0, now: 10_000 }), false);
  assert.equal(spaceSkips({ target: free, repeat: false, lastSkipAt: 10_000, now: 10_000 + SKIP_GUARD_MS - 1 }), false);
  assert.equal(spaceSkips({ target: free, repeat: false, lastSkipAt: 10_000, now: 10_000 + SKIP_GUARD_MS }), true);
});

test("times", () => {
  assert.equal(mmss(67), "1:07");
  assert.equal(mmss(3725), "1:02:05");
  assert.equal(progressLabel(67, 227), "1:07 / 3:47");
  assert.equal(progressLabel(300, 227), "3:47 / 3:47");
});

test("next anchor countdown, within the hour", () => {
  const now = new Date("2026-10-12T10:52:40Z");
  assert.equal(anchorHint({ at: "2026-10-12T11:00:00Z", minute: 0 }, now), "Ancre :00 dans 7:20");
  assert.equal(anchorHint({ at: "2026-10-12T10:52:40Z", minute: 20 }, now), "Ancre :20 maintenant");
  assert.equal(anchorHint({ at: "2026-10-12T12:00:00Z", minute: 0 }, now), null);
  assert.equal(anchorHint({ at: "pas une date" }, now), null);
  assert.equal(anchorHint(null, now), null);
});

test("alert only when something is wrong", () => {
  assert.equal(deskAlert({ tone: "on", label: "En onde", cause: "" }), null);
  assert.equal(deskAlert({ tone: "direct", label: "Direct", cause: "" }), null);
  const silence = deskAlert({ tone: "silence", label: "Silence 12 s", cause: "" });
  assert.equal(silence?.title, "Silence à l’antenne");
  assert.equal(silence?.live, "12 s");
  const icecast = deskAlert({ tone: "problem", label: "Problème", cause: "Sortie Icecast coupée" });
  assert.equal(icecast?.tone, "problem");
  assert.match(icecast?.help ?? "", /flux public/);
});

test("preview url escapes the id", () => {
  assert.equal(previewUrl("a/b c"), "/library/media/a%2Fb%20c");
});
