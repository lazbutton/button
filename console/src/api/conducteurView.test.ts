import assert from "node:assert/strict";
import test from "node:test";
import type { RundownItem } from "./types";
import {
  clockIdOf,
  cutLabel,
  kindClass,
  kindName,
  lineCopy,
  lineCut,
  lineEnd,
  lineOrigin,
  lineStatus,
  lineTime,
  lineWall,
  linesToRepair,
  nextClock,
  planEnd,
  reasonLabel,
  repairNotice,
  rundownEntries,
  secondsUntil,
  untilLabel,
  withoutClosedTwins,
  type RundownLine,
} from "./conducteurView.ts";

function line(overrides: Partial<RundownItem>): RundownItem {
  return {
    at: "2026-11-10T11:36:14",
    kind: "musique",
    when: "sequential",
    resource: "Fréquence Libre — Signal faible",
    queue: "autodj",
    status: "prévu",
    status_code: "planned",
    clock: "Horloge des parcours",
    daypart: "10:00–18:00",
    origin: "clock",
    ...overrides,
  };
}

test("une heure sans fuseau se lit telle quelle : elle est déjà à Paris", () => {
  assert.deepEqual(lineWall("2026-11-10T11:36:14.043509"), {
    day: "2026-11-10",
    hour: "11",
    minute: "36",
    second: "14",
  });
  assert.deepEqual(lineTime("2026-11-10T09:05"), { clock: "09:05", seconds: ":00" });
});

test("une heure avec fuseau, bâtie par la console, passe à l'heure de Paris", () => {
  assert.deepEqual(lineTime("2026-11-10T10:36:14.000Z"), { clock: "11:36", seconds: ":14" });
  assert.deepEqual(lineTime("2026-07-01T22:30:00+02:00"), { clock: "22:30", seconds: ":00" });
  assert.equal(lineWall(new Date("2026-11-10T23:30:00Z"))?.day, "2026-11-11");
});

test("une heure illisible donne un tiret, pas une erreur", () => {
  assert.equal(lineWall("bientôt"), null);
  assert.deepEqual(lineTime(""), { clock: "—", seconds: "" });
});

test("le temps d'ici une heure du conducteur se compte à Paris", () => {
  const now = new Date("2026-11-10T11:34:00+01:00");
  assert.equal(secondsUntil("2026-11-10T12:00:00", now), 26 * 60);
  assert.equal(secondsUntil("2026-11-11T00:30:00", now), 12 * 3600 + 56 * 60);
  assert.equal(secondsUntil("bientôt", now), null);
});

test("le temps d'ici une heure dite", () => {
  assert.equal(untilLabel(0), "maintenant");
  assert.equal(untilLabel(26 * 60), "dans 26 min");
  assert.equal(untilLabel(3900), "dans 1 h 05");
});

test("le type d'une ligne, dit comme dans les heures types", () => {
  assert.equal(kindName("musique"), "Titre");
  assert.equal(kindName("son"), "Programme");
  assert.equal(kindName("emission"), "Émission");
  assert.equal(kindName("autre"), "Son");
  assert.equal(kindClass("pub"), "pub");
  assert.equal(kindClass("autre"), "son");
});

test("un titre de la rotation : titre, artiste, et sa sélection pour origine", () => {
  const item = line({ title: "Signal faible", artist: "Fréquence Libre", category: "Rotation" });
  assert.deepEqual(lineCopy(item), { title: "Signal faible", artist: "Fréquence Libre" });
  assert.equal(lineOrigin(item), "Rotation");
});

test("un son de bac : le bac va dans l'origine, pas à la place de l'artiste", () => {
  const item = line({
    kind: "jingle",
    queue: "jingles",
    resource: "Jingle aigu",
    title: "Jingle aigu",
    artist: "Jingles",
    cart: "Jingles",
  });
  assert.deepEqual(lineCopy(item), { title: "Jingle aigu", artist: "" });
  assert.equal(lineOrigin(item), "Jingles");
});

test("l'origine d'une ligne du pupitre, de l'Agenda ou d'un direct", () => {
  assert.equal(lineOrigin(line({ origin: "desk", category: "Rotation" })), "Pupitre");
  assert.equal(lineOrigin(line({ origin: "agenda", kind: "emission", queue: "stream" })), "Agenda");
  assert.equal(lineOrigin(line({ origin: "live", queue: "stream", kind: "son" })), "Direct");
});

test("un bac sans son : la ligne porte le nom du bac, une seule fois", () => {
  const item = line({
    kind: "jingle",
    queue: "jingles",
    resource: "Jingles du soir",
    cart: "Jingles du soir",
    status: "manquant",
    status_code: "failed",
    reason: "cart introuvable",
  });
  assert.deepEqual(lineCopy(item), { title: "Jingles du soir", artist: "" });
  assert.equal(lineOrigin(item), "");
  assert.deepEqual(lineStatus(item, "later"), {
    label: "Manquant",
    tone: "danger",
    detail: "bac introuvable ou sans son",
  });
});

test("un bac en relais : la ligne dit qu'une heure type ne le lance pas", () => {
  const item = line({
    kind: "pub",
    when: "anchored",
    queue: "carts",
    resource: "Radio Zef",
    cart: "Radio Zef",
    status: "échec",
    status_code: "failed",
    reason: "bac en relais",
  });
  assert.deepEqual(lineCopy(item), { title: "Radio Zef", artist: "" });
  assert.deepEqual(lineStatus(item, "later"), {
    label: "Manquant",
    tone: "danger",
    detail: "bac en relais : une heure type ne le lance pas",
  });
  assert.deepEqual(linesToRepair([item]), [item]);
});

test("une sélection sans titre : la ligne le dit, et garde sa sélection pour origine", () => {
  const item = line({
    resource: "musique manquante",
    status: "manquant",
    reason: "aucun titre Beets",
    category: "Nouveautés",
  });
  delete item.status_code;
  assert.deepEqual(lineCopy(item), { title: "Titre manquant", artist: "" });
  assert.equal(lineOrigin(item), "Nouveautés");
  assert.equal(lineStatus(item, "next")?.detail, "aucun titre dans la sélection");
  // À son heure, elle reste « Manquant » : le bandeau la compte et y mène.
  assert.equal(lineStatus(item, "now")?.label, "Manquant");
});

test("« prévu » ne se dit pas : seule une ligne qui sort de l'ordinaire a une mention", () => {
  assert.equal(lineStatus(line({}), "later"), null);
  assert.equal(lineStatus(line({ status: "joué", status_code: "played" }), "past"), null);
  assert.deepEqual(lineStatus(line({}), "now"), { label: "À l’antenne", tone: "live" });
});

test("une ligne envoyée au playout dit « Déjà partie », comme au pupitre", () => {
  const sent = line({ status: "envoyé", status_code: "sent" });
  assert.deepEqual(lineStatus(sent, "next"), { label: "Déjà partie", tone: "plain" });
  // Passée, elle n'a plus rien à dire.
  assert.equal(lineStatus(sent, "past"), null);
});

test("secours, sautée, remplacée : la mention et sa raison en mots de la console", () => {
  assert.equal(lineStatus(line({ status: "secours", status_code: "rescue" }), "later")?.label, "Secours");
  assert.deepEqual(
    lineStatus(line({ status: "sauté", status_code: "skipped", reason: "file vidée" }), "past"),
    { label: "Sautée", tone: "plain", detail: "file vidée" },
  );
  assert.equal(
    lineStatus(line({ status: "sauté", status_code: "skipped", reason: "dépassé par une ancre dure" }), "later")
      ?.detail,
    "une coupure pile suit de près",
  );
  assert.equal(lineStatus(line({ status: "remplacé", status_code: "replaced" }), "past")?.label, "Remplacée");
});

test("les raisons du moteur se traduisent ; une raison inconnue reste lisible", () => {
  assert.equal(reasonLabel("retiré de la file"), "retirée au pupitre");
  assert.equal(reasonLabel("commande expirée"), "le playout ne l’a pas prise à temps");
  assert.equal(reasonLabel("glissement"), "");
  assert.equal(reasonLabel(null), "");
  assert.equal(reasonLabel("autre chose"), "autre chose");
});

test("une coupure dit sa minute et son mode, comme dans l'heure type", () => {
  const pile = line({ when: "anchored", minute: 0, sync: "dure", kind: "jingle" });
  assert.deepEqual(lineCut(pile), { label: "Coupure :00", tone: "plain", detail: "coupe pile" });
  assert.equal(lineCut(line({ when: "anchored", minute: 30, sync: "molle" }))?.detail, "attend la fin");
  assert.equal(lineCut(line({})), null);
  assert.equal(cutLabel({ minute: 5, sync: "dure" }), ":05 · coupe pile");
  assert.equal(cutLabel({ minute: null, sync: null }), "");
});

test("une émission de l'Agenda dit si c'est un direct ou un set, et jusqu'à quand", () => {
  const live = line({
    kind: "emission",
    when: "anchored",
    origin: "agenda",
    queue: "stream",
    at: "2026-11-10T23:30:00",
    duration: 3600,
  });
  const set = line({ kind: "emission", when: "anchored", origin: "agenda", queue: "carts" });
  assert.deepEqual(lineCut(live), { label: "Direct", tone: "plain", detail: "jusqu’à 00:30" });
  assert.deepEqual(lineCut(set), { label: "Set", tone: "plain", detail: undefined });
  assert.equal(lineEnd(line({ duration: 0 })), null);
});

test("une ligne close et son double encore prévu : la close reste seule", () => {
  const played = line({ id: "a", at: "2026-11-10T11:33:10", status: "joué", status_code: "played" });
  const twin = line({ id: "a", at: "2026-11-10T11:33:10.043509" });
  const next = line({ id: "b", at: "2026-11-10T11:36:14" });
  assert.deepEqual(withoutClosedTwins([played, twin, next]), [played, next]);
  // Relancé, un titre joué deux fois garde ses deux lignes.
  const again = line({ id: "a", at: "2026-11-10T11:50:00", status: "joué", status_code: "played" });
  assert.deepEqual(withoutClosedTwins([played, again]), [played, again]);
  // Rien à écarter : la même liste, pour ne rien redessiner.
  const plain = [next];
  assert.equal(withoutClosedTwins(plain), plain);
});

function lines(...items: Array<[string, Partial<RundownItem>?]>): RundownLine[] {
  return items.map(([at, extra], index) => ({
    item: line({ id: `id-${index}`, at, ...extra }),
    role: "later",
  }));
}

test("le déroulé se découpe en heures, avec une marque devant la première ligne", () => {
  const entries = rundownEntries(
    lines(["2026-11-10T11:55:00"], ["2026-11-10T11:58:00"], ["2026-11-10T12:01:00"]),
    "2026-11-10",
  );
  assert.deepEqual(
    entries.map((entry) => (entry.type === "mark" ? `[${entry.mark.hour}]` : entry.line.item.at.slice(11, 16))),
    ["[11 h]", "11:55", "11:58", "[12 h]", "12:01"],
  );
});

test("après minuit, la marque dit « demain » ; avant, « hier »", () => {
  const entries = rundownEntries(
    lines(["2026-11-09T23:58:00"], ["2026-11-10T23:59:00"], ["2026-11-11T00:02:00"]),
    "2026-11-10",
  );
  const marks = entries.flatMap((entry) => (entry.type === "mark" ? [entry.mark] : []));
  assert.deepEqual(
    marks.map((mark) => [mark.hour, mark.day]),
    [
      ["23 h", "hier"],
      ["23 h", ""],
      ["0 h", "demain"],
    ],
  );
});

test("une heure type qui commence se marque, même en cours d'heure ; la première non", () => {
  const entries = rundownEntries(
    lines(
      ["2026-11-10T17:58:00"],
      ["2026-11-10T18:00:00"],
      ["2026-11-10T18:04:00", { origin: "desk", clock: "" }],
      ["2026-11-10T18:30:00", { clock: "Soirée", daypart: "18:30–23:00" }],
    ),
    "2026-11-10",
  );
  const marks = entries.flatMap((entry) => (entry.type === "mark" ? [entry.mark] : []));
  assert.deepEqual(
    marks.map((mark) => [mark.hour, mark.newHour, mark.clock, mark.daypart, mark.at]),
    [
      ["17 h", true, "", "", "17:58"],
      ["18 h", true, "", "", "18:00"],
      ["18 h", false, "Soirée", "18:30–23:00", "18:30"],
    ],
  );
});

test("un titre relancé garde son identifiant : sa clé reste unique", () => {
  const twice = rundownEntries(
    [
      { item: line({ id: "same", at: "2026-11-10T11:00:00" }), role: "past" },
      { item: line({ id: "same", at: "2026-11-10T11:00:00" }), role: "past" },
    ],
    "2026-11-10",
  );
  const keys = twice.map((entry) => entry.key);
  assert.equal(new Set(keys).size, keys.length);
});

test("les lignes à réparer, et le bandeau qui les annonce", () => {
  const items = [
    line({}),
    line({ status: "manquant", status_code: "failed", kind: "jingle" }),
    line({ status: "échec", status_code: "failed" }),
    line({ status: "secours", status_code: "rescue" }),
  ];
  assert.equal(linesToRepair(items).length, 2);
  assert.deepEqual(repairNotice(2, "17:35", true), {
    title: "2 lignes à réparer d’ici 17:35",
    help: "Leur bac ou leur sélection ne donne aucun son.",
  });
  assert.deepEqual(repairNotice(1, null, false), {
    title: "1 ligne à réparer",
    help: "Son bac ou sa sélection ne donne aucun son. Un programmateur peut la réparer ici.",
  });
  assert.equal(repairNotice(0, "17:35", true), null);
});

test("la prochaine heure type ne se lit que sur les lignes de l'heure type", () => {
  const upcoming = [
    line({ origin: "desk", clock: "" }),
    line({ origin: "agenda", kind: "emission", clock: "Agenda" }),
    line({}),
    line({ at: "2026-11-10T18:00:00", clock: "Soirée", daypart: "18:00–23:00", clock_id: 7 }),
  ];
  assert.deepEqual(nextClock(upcoming, "Horloge des parcours"), {
    name: "Soirée",
    at: "2026-11-10T18:00:00",
    daypart: "18:00–23:00",
  });
  assert.equal(nextClock(upcoming.slice(0, 3), "Horloge des parcours"), null);
  assert.equal(clockIdOf(upcoming, "Soirée"), 7);
  assert.equal(clockIdOf(upcoming, ""), null);
});

test("le conducteur va jusqu'à l'heure de sa dernière ligne", () => {
  assert.equal(planEnd([line({}), line({ at: "2026-11-10T17:35:12" })]), "17:35");
  assert.equal(planEnd([]), null);
});
