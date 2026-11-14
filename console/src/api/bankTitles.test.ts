import assert from "node:assert/strict";
import test from "node:test";
import type { BankShelf } from "./bankContent.ts";
import {
  DEFAULT_COLUMNS,
  DEFAULT_STATE,
  cleanColumns,
  columnsFor,
  moveColumn,
  sameAsView,
  stateOfView,
  tableMinWidth,
  toggleColumn,
  viewNameProblem,
  type SavedView,
  ficheState,
  filterGroups,
  groupLabel,
  groupsOf,
  nameInShelf,
  nextSort,
  rankingsFor,
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
  const state = {
    ranking: "artist" as const,
    group: "Orage",
    q: "ciel",
    sort: "year" as const,
    order: "desc" as const,
    columns: DEFAULT_COLUMNS,
  };
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
    titlesQuery({ ...DEFAULT_STATE, ranking: "famille", group: "", sort: "title" }),
    "?famille=&sort=title&order=asc&limit=100&facets=famille",
  );
  assert.equal(
    titlesQuery({ ...DEFAULT_STATE, ranking: "artist", q: " été ", sort: "year", order: "desc" }, 200),
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

test("the columns shown go in the address only when they are not all there", () => {
  const state = { ...DEFAULT_STATE, columns: cleanColumns(["artist", "title", "year"]) };
  const params = writeState(new URLSearchParams(), state);
  assert.equal(params.get("colonnes"), "artist,title,year");
  assert.deepEqual(readState(params).columns, ["artist", "title", "year"]);
  assert.equal(writeState(new URLSearchParams(), DEFAULT_STATE).has("colonnes"), false);
});

test("columns read from anywhere keep the known ones once, and the title", () => {
  assert.deepEqual(cleanColumns(["year", "taille", "year", "artist"]), ["title", "year", "artist"]);
  assert.deepEqual(cleanColumns("title"), DEFAULT_COLUMNS);
  assert.deepEqual(readState(new URLSearchParams("colonnes=")).columns, ["title"]);
});

test("a column hides, comes back at its own place, and moves; the title stays", () => {
  const some = toggleColumn(toggleColumn(DEFAULT_COLUMNS, "album"), "genre");
  assert.deepEqual(some, ["title", "artist", "famille", "etiquettes", "year", "duration", "fiche"]);
  assert.deepEqual(toggleColumn(some, "album"), [
    "title",
    "artist",
    "album",
    "famille",
    "etiquettes",
    "year",
    "duration",
    "fiche",
  ]);
  assert.equal(toggleColumn(some, "title"), some);
  assert.deepEqual(moveColumn(["title", "artist", "year"], "year", -1), ["title", "year", "artist"]);
  assert.deepEqual(moveColumn(["title", "artist"], "title", -1), ["title", "artist"]);
});

test("an engine before FON-74: no tags to range by, nor their column", () => {
  assert.deepEqual(rankingsFor(true), ["collection", "artist", "famille", "album", "etiquette"]);
  assert.deepEqual(rankingsFor(false), ["collection", "artist", "famille", "album"]);
  assert.deepEqual(columnsFor(["title", "etiquettes", "year"], false), ["title", "year"]);
  assert.deepEqual(columnsFor(["title", "etiquettes"], true), ["title", "etiquettes"]);
  assert.equal(
    titlesQuery({ ...DEFAULT_STATE, ranking: "etiquette", group: "nuit" }),
    "?etiquette=nuit&sort=artist&order=asc&limit=100&facets=etiquette",
  );
});

test("the table's room follows its columns", () => {
  assert.equal(tableMinWidth(DEFAULT_COLUMNS, false), 73.15);
  assert.equal(tableMinWidth(["title", "famille"], true), 28.25);
});

const jazz: SavedView = {
  id: 3,
  name: "Jazz à relire",
  state: { ranking: "famille", group: "jazz", q: "", sort: "year", order: "desc", columns: ["title", "year"] },
  modified: "2026-11-14T10:00+01:00",
};

test("a view opens its table, whatever an older view lacks", () => {
  assert.deepEqual(stateOfView(jazz), { ranking: "famille", group: "jazz", q: "", sort: "year", order: "desc", columns: ["title", "year"] });
  assert.deepEqual(stateOfView({ ...jazz, state: { ranking: "genre" as never } }), DEFAULT_STATE);
});

test("a view is the same until the table changes, a text with spaces aside", () => {
  const shown = stateOfView(jazz);
  assert.equal(sameAsView({ ...shown, q: "  " }, jazz), true);
  assert.equal(sameAsView({ ...shown, order: "asc" }, jazz), false);
  assert.equal(sameAsView({ ...shown, columns: ["year", "title"] }, jazz), false);
});

test("a view's name: given, short, not taken by another view of the account", () => {
  assert.equal(viewNameProblem("  ", [jazz]), "Donne un nom à la vue.");
  assert.equal(viewNameProblem("x".repeat(61), [jazz]), "Un nom de vue tient en 60 signes.");
  assert.equal(viewNameProblem(" Jazz   à relire ", [jazz]), "Tu as déjà une vue « Jazz à relire ».");
  assert.equal(viewNameProblem("Jazz à relire", [jazz], 3), "");
});
