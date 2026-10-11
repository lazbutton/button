import assert from "node:assert/strict";
import test from "node:test";
import {
  agoLabel,
  bacCounts,
  bacKind,
  bankFolderOf,
  bankProblem,
  destinationLabel,
  filterDestinations,
  type BankDestination,
  formatBytes,
  formatClock,
  formatSpan,
  groupBacs,
  percentOf,
  relayHost,
  tusReason,
  tusRetryable,
} from "./soundsView.ts";
import type { Cart } from "./types.ts";

const bac = (id: number, mode: Cart["mode"], bank_folder: string | null = null) =>
  ({ id, title: `B${id}`, mode, bank_folder, sounds: [] }) as unknown as Cart;

test("a bac is files, station imaging or a relay", () => {
  assert.equal(bacKind(bac(1, "random", "30-habillage/jingles")), "habillage");
  assert.equal(bacKind(bac(2, "playlist_loop")), "fichiers");
  assert.equal(bacKind(bac(3, "relay", "30-habillage/jingles")), "relais");
});

test("counts and groups follow the filter of the list", () => {
  const carts = [bac(1, "random", "30-habillage/ids"), bac(2, "playlist"), bac(3, "relay"), bac(4, "random")];
  assert.deepEqual(bacCounts(carts), { tous: 4, fichiers: 3, habillage: 1, relais: 1 });
  assert.deepEqual(
    groupBacs(carts).map((group) => [group.kind, group.carts.map((cart) => cart.id)]),
    [
      ["habillage", [1]],
      ["fichiers", [2, 4]],
      ["relais", [3]],
    ],
  );
  assert.deepEqual(groupBacs([]), []);
});

test("durations read like a music library", () => {
  assert.equal(formatClock(227), "3:47");
  assert.equal(formatClock(3750), "1:02:30");
  assert.equal(formatClock(0), "0:00");
  assert.equal(formatSpan(31), "31 s");
  assert.equal(formatSpan(3134), "52 min");
  assert.equal(formatSpan(3600), "1 h");
  assert.equal(formatSpan(11100), "3 h 05");
});

test("sizes, hosts, destinations and progress", () => {
  assert.equal(formatBytes(512), "512 o");
  assert.equal(formatBytes(48_200_000), "46 Mo");
  assert.equal(formatBytes(1_610_612_736), "1,5 Go");
  assert.equal(relayHost("https://radio.exemple/flux.mp3"), "radio.exemple");
  assert.equal(relayHost("pas une url"), "");
  assert.equal(percentOf(31, 48), 65);
  assert.equal(percentOf(5, 0), 0);
});

test("relative times stay short", () => {
  const now = Date.parse("2026-10-11T12:00:00Z");
  assert.equal(agoLabel("2026-10-11T11:59:30Z", now), "à l'instant");
  assert.equal(agoLabel("2026-10-11T11:48:00Z", now), "il y a 12 min");
  assert.equal(agoLabel("2026-10-11T09:00:00Z", now), "il y a 3 h");
  assert.equal(agoLabel("pas une date", now), "");
});

test("a refused upload says why, in the catalogue's words", () => {
  const refused =
    "tus: unexpected response while creating upload, originated from request (method: POST, url: http://127.0.0.1:5175/tus/, response code: 400, response text: déjà dans la banque, request id: n/a)";
  assert.equal(tusReason(refused), "déjà dans la banque");
  assert.equal(
    tusReason(
      "tus: unexpected response while creating upload, originated from request (method: POST, url: /tus/, response code: 413, response text: , request id: n/a)",
    ),
    "fichier trop lourd",
  );
  assert.equal(tusReason("This looks like a network error, the endpoint might be blocked."), "connexion coupée");
  assert.equal(tusReason("autre chose"), "envoi interrompu");
  assert.equal(tusReason(null), "");
});

test("only a cut upload offers a retry", () => {
  assert.equal(tusRetryable("… response code: 400, response text: quota dépassé, request id: n/a)"), false);
  assert.equal(tusRetryable("… response code: 413, response text: , request id: n/a)"), false);
  assert.equal(tusRetryable("… response code: 502, response text: , request id: n/a)"), true);
  assert.equal(tusRetryable("This looks like a network error"), true);
});

const banks: BankDestination[] = [
  { id: "rotation", label: "Rotation", group: "rotation", folder: "10-rotation" },
  { id: "ntf1", label: "NTF 1", group: "archives", folder: "20-archives/ntf1" },
  { id: "jazz", label: "Archives jazz été", group: "archives", folder: "20-archives/jazz" },
];

test("banks come from the catalogue and read by name", () => {
  assert.equal(destinationLabel(banks, "ntf1"), "NTF 1");
  assert.equal(destinationLabel(banks, "autre"), "autre");
  assert.deepEqual(
    filterDestinations(banks, "ete jaz").map((item) => item.id),
    ["jazz"],
  );
  assert.deepEqual(
    filterDestinations(banks, "archives/ntf").map((item) => item.id),
    ["ntf1"],
  );
  assert.equal(filterDestinations(banks, "  ").length, 3);
});

test("a new bank gets a folder and is checked like the catalogue does", () => {
  assert.equal(bankFolderOf("  Archives Jazz été 2024 !"), "archives-jazz-ete-2024");
  assert.equal(bankFolderOf("x".repeat(50)).length, 40);
  const problem = (label: string, folder: string) => {
    const found = bankProblem(banks, label, folder);
    return found ? `${found.field}: ${found.message}` : "";
  };
  assert.equal(problem("Reggae", "reggae"), "");
  assert.match(problem("", "vide"), /^label: .*nom/);
  assert.match(problem("Autre", "ntf1"), /^folder: .*existe déjà/);
  assert.match(problem("archives JAZZ ete", "jazz2"), /^label: .*porte déjà/);
  assert.match(problem("Musique", "rotation"), /^folder: .*réservé/);
  assert.match(problem("Jazz live", "Jazz Live"), /^folder: .*minuscules/i);
});
