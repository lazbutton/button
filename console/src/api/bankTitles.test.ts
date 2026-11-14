import assert from "node:assert/strict";
import test from "node:test";
import type { BankShelf } from "./bankContent.ts";
import {
  DEFAULT_STATE,
  ficheState,
  filterGroups,
  groupLabel,
  groupsOf,
  nameInShelf,
  nextSort,
  readState,
  titlesCount,
  titlesQuery,
  writeState,
  type BankFacet,
} from "./bankTitles.ts";

const shelf = (id: string, label: string, folder: string, count = 0): BankShelf => ({
  id,
  label,
  group: id === "rotation" ? "rotation" : "archives",
  folder,
  count,
  bytes: 0,
});

test("the address keeps the ranking, the group and the order", () => {
  const state = { ranking: "artist" as const, group: "Orage", q: "ciel", sort: "year" as const, order: "desc" as const };
  const params = writeState(new URLSearchParams("vue=contenu"), state);
  assert.equal(params.toString(), "vue=contenu&ranger=artist&groupe=Orage&tri=year&ordre=desc&q=ciel");
  assert.deepEqual(readState(params), state);
});

test("an empty group is the titles without that field, not the whole bank", () => {
  const params = writeState(new URLSearchParams(), { ...DEFAULT_STATE, ranking: "famille", group: "" });
  assert.equal(params.toString(), "ranger=famille&groupe=");
  assert.equal(readState(params).group, "");
  assert.equal(readState(new URLSearchParams("ranger=famille")).group, null);
});

test("a link of the former view still opens its collection", () => {
  assert.deepEqual(readState(new URLSearchParams("collection=jazz")), { ...DEFAULT_STATE, group: "jazz" });
  assert.equal(readState(new URLSearchParams("ranger=nimporte&tri=taille")).ranking, "collection");
  assert.equal(readState(new URLSearchParams("tri=taille")).sort, "artist");
});

test("the query asks for the group's filter and the facets of the ranking", () => {
  assert.equal(
    titlesQuery({ ranking: "famille", group: "", q: "", sort: "title", order: "asc" }),
    "?famille=&sort=title&order=asc&limit=100&facets=famille",
  );
  assert.equal(
    titlesQuery({ ranking: "artist", group: null, q: " été ", sort: "year", order: "desc" }, 200),
    "?q=%C3%A9t%C3%A9&sort=year&order=desc&offset=200&limit=100&facets=artist",
  );
});

test("a column sorts, then the other way; numbers start with the largest", () => {
  assert.deepEqual(nextSort(DEFAULT_STATE, "artist"), { sort: "artist", order: "desc" });
  assert.deepEqual(nextSort(DEFAULT_STATE, "title"), { sort: "title", order: "asc" });
  assert.deepEqual(nextSort(DEFAULT_STATE, "year"), { sort: "year", order: "desc" });
});

test("ranged by collection, every collection is there with its name, rotation first", () => {
  const facets: BankFacet[] = [
    { value: "nuit", label: "nuit", count: 2 },
    { value: "rotation", label: "rotation", count: 5 },
    { value: "vieux", label: "vieux", count: 1 },
    { value: "", label: "", count: 3 },
  ];
  const shelves = [shelf("nuit", "Nuit", "20-archives/nuit"), shelf("rotation", "Rotation", "10-rotation"), shelf("vide", "Vide", "20-archives/vide")];
  assert.deepEqual(groupsOf("collection", facets, shelves), [
    { value: "rotation", label: "Rotation", count: 5 },
    { value: "nuit", label: "Nuit", count: 2 },
    { value: "vide", label: "Vide", count: 0 },
    { value: "vieux", label: "vieux", count: 1 },
    { value: "", label: "", count: 3 },
  ]);
  assert.equal(groupsOf("artist", facets, shelves), facets);
});

test("the groups filter forgets accents, and names the empty group", () => {
  const groups: BankFacet[] = [
    { value: "Zéphyr", label: "Zéphyr", count: 1 },
    { value: "Orage", label: "Orage", count: 2 },
    { value: "", label: "", count: 1 },
  ];
  assert.deepEqual(
    filterGroups(groups, "zeph", "artist").map((group) => group.value),
    ["Zéphyr"],
  );
  assert.deepEqual(
    filterGroups(groups, "sans", "artist").map((group) => group.value),
    [""],
  );
  assert.equal(groupLabel("artist", null, groups), "Toute la banque");
  assert.equal(groupLabel("famille", "", groups), "Sans famille");
  assert.equal(groupLabel("artist", "Orage", groups), "Orage");
});

test("the Fiche column says what is left to fill", () => {
  assert.deepEqual(ficheState([]), { complete: true, label: "Complète", detail: "Tous les champs de la fiche sont remplis." });
  assert.deepEqual(ficheState(["genre"]), { complete: false, label: "1 champ vide", detail: "Genre à remplir." });
  assert.equal(ficheState(["album", "year", "famille"]).detail, "Album, année et famille à remplir.");
});

test("a title's name below its collection, for the catalogue", () => {
  const nuit = shelf("nuit", "Nuit", "20-archives/nuit");
  assert.equal(nameInShelf({ path: "20-archives/nuit/sub/a.mp3" }, nuit), "sub/a.mp3");
  assert.equal(nameInShelf({ path: "20-archives/nuits/a.mp3" }, nuit), null);
  assert.equal(nameInShelf({ path: "10-rotation/a.mp3" }, shelf("rotation", "Rotation", "10-rotation/")), "a.mp3");
});

test("a count of titles, in French", () => {
  assert.equal(titlesCount(0), "Aucun titre");
  assert.equal(titlesCount(1), "1 titre");
  assert.match(titlesCount(7000), /^7\s000 titres$/);
});
