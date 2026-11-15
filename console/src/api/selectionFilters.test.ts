import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_STATE } from "./bankTitles.ts";
import {
  NO_FILTERS,
  filtersFromParams,
  filtersFromTable,
  filtersProblem,
  filtersQuery,
  hasFilter,
  selectionLink,
  suggestedName,
  tableMakesSelection,
  withoutSelectionParams,
} from "./selectionFilters.ts";

test("only the filters chosen go to the engine", () => {
  assert.equal(
    filtersQuery({ ...NO_FILTERS, famille: "jazz", year_from: " 2015 ", collection: "nuit" }),
    "famille=jazz&collection=nuit&year_from=2015",
  );
  assert.equal(filtersQuery(NO_FILTERS), "");
  assert.equal(hasFilter(NO_FILTERS), false);
  assert.equal(hasFilter({ ...NO_FILTERS, artist: " " }), false);
});

test("the years: four digits, in order", () => {
  assert.equal(filtersProblem({ ...NO_FILTERS, year_from: "15" }), "Une année s'écrit en quatre chiffres.");
  assert.equal(
    filtersProblem({ ...NO_FILTERS, year_from: "2020", year_to: "2010" }),
    "L'année de début vient après celle de fin.",
  );
  assert.equal(filtersProblem({ ...NO_FILTERS, year_from: "2010", year_to: "2010" }), "");
});

test("the table's group becomes the selection's filter", () => {
  assert.deepEqual(filtersFromTable({ ranking: "famille", group: "jazz" }), { ...NO_FILTERS, famille: "jazz" });
  assert.deepEqual(filtersFromTable({ ranking: "collection", group: "nuit" }), { ...NO_FILTERS, collection: "nuit" });
  assert.deepEqual(filtersFromTable({ ranking: "etiquette", group: "nuit" }), { ...NO_FILTERS, etiquette: "nuit" });
  assert.equal(tableMakesSelection({ ...DEFAULT_STATE, group: null }), false);
  assert.equal(tableMakesSelection({ ...DEFAULT_STATE, group: "" }), false);
  assert.equal(tableMakesSelection({ ...DEFAULT_STATE, group: "Orage" }), true);
  // Rangée par verdict (FON-80), la table n'en fait pas une sélection : le compositeur ne le filtre pas.
  assert.equal(tableMakesSelection({ ...DEFAULT_STATE, ranking: "fmg", group: "oui" }), false);
  assert.deepEqual(filtersFromTable({ ranking: "fmg", group: "oui" }), NO_FILTERS);
});

test("the link opens a new selection with its filters, once", () => {
  const link = selectionLink({ ...NO_FILTERS, artist: "Madame Orage" });
  assert.equal(link, "/programmation?onglet=categories&nouvelle-selection=1&artist=Madame+Orage");
  const params = new URLSearchParams(link.split("?")[1]);
  assert.deepEqual(filtersFromParams(params), { ...NO_FILTERS, artist: "Madame Orage" });
  assert.equal(withoutSelectionParams(params).toString(), "onglet=categories");
  assert.equal(filtersFromParams(new URLSearchParams("onglet=categories&artist=x")), null);
});

test("a name to start from", () => {
  assert.equal(
    suggestedName({ ...NO_FILTERS, famille: "jazz", year_from: "2015", collection: "nuit" }),
    "Jazz depuis 2015 · nuit",
  );
  assert.equal(
    suggestedName(
      { ...NO_FILTERS, famille: "jazz", collection: "nuit" },
      { famille: () => "Jazz", collection: () => "Nuit" },
    ),
    "Jazz · Nuit",
  );
  assert.equal(suggestedName({ ...NO_FILTERS, year_from: "1990", year_to: "1999" }), "De 1990 à 1999");
  assert.equal(suggestedName({ ...NO_FILTERS, year_to: "1999" }), "Jusqu'à 1999");
  assert.equal(suggestedName(NO_FILTERS), "");
  assert.equal(suggestedName({ ...NO_FILTERS, famille: "jazz", etiquette: "nuit" }), "Jazz, nuit");
  assert.equal(filtersQuery({ ...NO_FILTERS, etiquette: "nuit" }), "etiquette=nuit");
});
