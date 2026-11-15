import assert from "node:assert/strict";
import test from "node:test";
import type { BankHealth, HealthTitle, SpellingGroup } from "./bankHealth.ts";
import {
  clearLine,
  copiesLine,
  duplicateLabel,
  guessLine,
  modelLabel,
  numberedAction,
  numberedLot,
  numberedSplit,
  numbersLine,
  renameLine,
  REVIEW_COUNT_PATH,
  spellingAction,
  spellingLot,
  spellingsLine,
  tableOfDuplicate,
  tasksCount,
  tasksOf,
} from "./bankTasks.ts";

function title(id: number, more: Partial<HealthTitle> = {}): HealthTitle {
  return {
    id,
    title: "Estuaire",
    artist: "Les Marées Hautes",
    album: "Delta",
    year: 2020,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    duration: 200,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
    ...more,
  };
}

/** Une banque où rien ne cloche ; chaque test y ajoute ce qu'il compte. */
function healthy(): BankHealth {
  return {
    model: "artiste-titre",
    figures: { titles: 93, complete: 0, families: [], without_family: 93 },
    spellings: { count: 0, titles: 0, groups: [] },
    duplicates: { count: 0, titles: 0, groups: [] },
    misnamed: { count: 0, titles: [] },
    numbered: { count: 0, titles: [] },
    incomplete: {
      count: 93,
      fields: [
        { field: "title", count: 0 },
        { field: "artist", count: 0 },
        { field: "album", count: 40 },
        { field: "year", count: 60 },
        { field: "genre", count: 12 },
        { field: "famille", count: 93 },
      ],
    },
    archive: { count: 0, titles: [] },
    unindexed: { count: 0, paths: [] },
  };
}

const ANA = [
  title(1, { artist: "01", title: "01 - Ana - Fado", path: "10-rotation/01 - Ana - Fado.mp3", guess: { artist: "Ana", title: "Fado" } }),
  title(2, { artist: "02", title: "Mar", path: "10-rotation/02 - Ana - Mar.mp3", guess: { artist: "Ana", title: "Mar" } }),
  title(3, { artist: "03", title: "Rio", path: "10-rotation/03 - Rio.mp3", guess: null }),
];

test("a bank where nothing is wrong has nothing to tidy, even with empty optional fields", () => {
  const tasks = tasksOf(healthy(), 0, "artiste-titre");
  // Ni l'album, ni l'année, ni la famille : rien de cela ne se voit à l'antenne.
  assert.deepEqual(tasks, []);
  assert.equal(tasksCount(tasks), 0);
  assert.equal(
    clearLine(healthy()),
    "Rien à signaler : doublons, orthographe des artistes, artistes et titres manquants, numéros pris pour artiste, fichiers hors de la bibliothèque.",
  );
});

test("the tasks come in order, what the antenna shows first, the file names last and optional", () => {
  const health = healthy();
  health.unindexed = { count: 1, paths: ["10-rotation/abime.mp3"] };
  health.numbered = { count: 3, titles: ANA };
  health.incomplete.fields = health.incomplete.fields.map((row) =>
    row.field === "artist" ? { ...row, count: 4 } : row.field === "title" ? { ...row, count: 1 } : row,
  );
  health.spellings = { count: 2, titles: 5, groups: [] };
  health.duplicates = { count: 1, titles: 2, groups: [] };
  health.archive = { count: 2, titles: [] };
  health.misnamed = { count: 81, titles: [] };

  const tasks = tasksOf(health, 12, "artiste-titre");

  assert.deepEqual(
    tasks.map((task) => task.title),
    [
      "1 fichier n'est pas dans la bibliothèque",
      "3 titres ont un numéro pour artiste",
      "4 titres sans artiste",
      "1 fiche sans titre",
      "12 titres ont des corrections trouvées en ligne",
      "2 artistes s'écrivent de plusieurs façons",
      "1 titre est en double",
      "2 fiches portent le genre « Archive »",
      "81 fichiers ne s'appellent pas « Artiste - Titre »",
    ],
  );
  assert.deepEqual(
    tasks.filter((task) => task.optional).map((task) => task.key),
    ["names"],
  );
  // L'onglet compte les tâches, sans le facultatif.
  assert.equal(tasksCount(tasks), 8);
  assert.equal(tasks[1].why, "L'antenne affiche « 01 », « 02 »… à la place de l'artiste.");
  assert.equal(tasks[0].why.startsWith("Il ne passe pas à l'antenne."), true);
  assert.equal(clearLine(health), null);
});

test("one of each says it in the singular", () => {
  const health = healthy();
  health.misnamed = { count: 1, titles: [] };
  health.spellings = { count: 1, titles: 2, groups: [] };
  const tasks = tasksOf(health, 1, "titre");
  assert.deepEqual(
    tasks.map((task) => task.title),
    [
      "1 titre a des corrections trouvées en ligne",
      "1 artiste s'écrit de plusieurs façons",
      "1 fichier ne s'appelle pas « Titre »",
    ],
  );
  assert.equal(tasks[2].why.startsWith("Son nom ne change rien à l'antenne."), true);
});

test("without the health, only the corrections found online; an older engine has no numbered titles", () => {
  assert.deepEqual(
    tasksOf(null, 3, "artiste-titre").map((task) => task.key),
    ["review"],
  );
  assert.deepEqual(tasksOf(null, null, "artiste-titre"), []);
  const older = healthy();
  delete older.numbered;
  assert.deepEqual(tasksOf(older, null, "artiste-titre"), []);
  assert.match(clearLine(older) ?? "", /numéros pris pour artiste/);
});

test("a track number taken for the artist is corrected after the file's name", () => {
  assert.equal(numbersLine(ANA), "« 01 », « 02 »…");
  assert.equal(numbersLine(ANA.slice(0, 1)), "« 01 »");
  assert.equal(guessLine(ANA[0]), "01 - Ana - Fado.mp3 → Ana – Fado");
  assert.equal(guessLine(ANA[2]), "03 - Rio.mp3");
  assert.deepEqual(
    numberedSplit(ANA).bare.map((item) => item.id),
    [3],
  );
  // Seuls les titres que leur nom renseigne ; ce que la console a montré part avec.
  assert.deepEqual(numberedLot(ANA).titles, [
    { id: 1, values: { artist: "Ana", title: "Fado" }, expected: { artist: "01", title: "01 - Ana - Fado" } },
    { id: 2, values: { artist: "Ana", title: "Mar" }, expected: { artist: "02", title: "Mar" } },
  ]);
  assert.equal(numberedAction(1), "Corriger d'après son nom");
  assert.equal(numberedAction(2), "Corriger les 2 d'après leur nom");
});

test("an artist written several ways takes the spelling chosen, on the titles that lack it", () => {
  const group: SpellingGroup = {
    key: "lesmareeshautes",
    spellings: [
      { value: "Les Marées Hautes", count: 2 },
      { value: "les marees hautes", count: 1 },
    ],
    suggested: "Les Marées Hautes",
    count: 3,
    titles: [title(1), title(2), title(3, { artist: "les marees hautes" })],
  };
  assert.equal(spellingsLine(group), "Les Marées Hautes (2) · les marees hautes (1)");
  assert.deepEqual(spellingLot(group, "Les Marées Hautes").titles, [
    { id: 3, values: { artist: "Les Marées Hautes" }, expected: { artist: "les marees hautes" } },
  ]);
  assert.equal(spellingLot(group, "les marees hautes").titles.length, 2);
  assert.equal(spellingAction("Les Marées Hautes", 1), "Écrire « Les Marées Hautes » sur 1 titre");
  assert.equal(spellingAction("les marees hautes", 2), "Écrire « les marees hautes » sur 2 titres");
});

test("the lines that name a file, a duplicate and a model", () => {
  assert.equal(renameLine(title(3, { path: "20-archives/nuit/03_un.mp3", to: "Ada - Un.mp3" })), "03_un.mp3 → Ada - Un.mp3");
  assert.equal(modelLabel("artiste-album-titre"), "Artiste - Album - Titre");
  const group = { label: "Orage - Avant", titles: [title(8, { artist: "Orage", title: "Avant" }), title(9)] };
  assert.equal(duplicateLabel(group), "Orage – Avant");
  assert.equal(
    copiesLine({ label: "", titles: [title(8), title(9, { zone: "collections", collection: "nuit", path: "20-archives/nuit/9.flac" })] }),
    "8.mp3 (Rotation), 9.flac (nuit)",
  );
  assert.deepEqual(tableOfDuplicate(group), { q: "Avant" });
  assert.equal(REVIEW_COUNT_PATH, "/fiches.json?limit=1");
});
