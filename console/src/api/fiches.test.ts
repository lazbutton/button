import assert from "node:assert/strict";
import test from "node:test";
import {
  NO_FILTERS,
  bankLabel,
  fichesErrorText,
  eraseQuestion,
  queryExamples,
  verdictShare,
  chunks,
  decidedMessage,
  propositionStatus,
  sureShown,
  levelChips,
  count,
  duration,
  durationGap,
  fichesQuery,
  fieldValue,
  levelColor,
  platformName,
  progressLine,
  settingsBody,
  settingsChanged,
  settingsForm,
  type FichesSettings,
} from "./fiches.ts";

const SETTINGS: FichesSettings = {
  enabled: false,
  verdict: false,
  acoustid_key_set: true,
  sources: { tidal: false, apple_music: false, bandcamp: false, tidal_key_set: false },
  sent: "l’artiste…",
};

test("la requête ne porte que les filtres choisis, et la suite", () => {
  assert.equal(fichesQuery(NO_FILTERS), "");
  assert.equal(
    fichesQuery({ ...NO_FILTERS, level: "à revoir", bank: "jazz", q: "  nina  " }, 50),
    "?level=%C3%A0+revoir&bank=jazz&q=nina&offset=50",
  );
  assert.equal(fichesQuery({ ...NO_FILTERS, state: "écrite" }, 0), "?state=%C3%A9crite");
});

test("l'avancement se dit en clair", () => {
  const progress = { library: 7123, searched: 4210, remaining_hours: 3.2 };
  assert.equal(count(7123), "7 123");
  assert.equal(progressLine({ enabled: true, progress }), "4 210 titres cherchés sur 7 123, encore 3 h environ.");
  assert.equal(
    progressLine({ enabled: true, progress: { ...progress, remaining_hours: 0.4 } }),
    "4 210 titres cherchés sur 7 123, encore moins d’une heure.",
  );
  assert.equal(
    progressLine({ enabled: true, progress: { ...progress, remaining_hours: 40 } }),
    "4 210 titres cherchés sur 7 123, encore 2 jours environ.",
  );
  assert.equal(
    progressLine({ enabled: true, progress: { ...progress, remaining_hours: null } }),
    "4 210 titres cherchés sur 7 123, recherche en cours.",
  );
  assert.equal(progressLine({ enabled: false, progress }), "4 210 titres cherchés sur 7 123. La recherche est coupée.");
  assert.equal(
    progressLine({ enabled: false, progress: { library: 7123, searched: 0, remaining_hours: null } }),
    "Aucun titre cherché sur 7\u202f123. La recherche est coupée.",
  );
  assert.equal(
    progressLine({ enabled: true, progress: { library: 1, searched: 1, remaining_hours: null } }),
    "1 titre cherché sur 1 : toute la banque est passée.",
  );
});

test("les valeurs, les durées et les niveaux se lisent", () => {
  assert.equal(fieldValue("year", "0"), "—");
  assert.equal(fieldValue("album", ""), "—");
  assert.equal(fieldValue("year", "1965"), "1965");
  assert.equal(duration(172.4), "2:52");
  assert.equal(duration(null), "—");
  assert.equal(durationGap(172, 175), "+3 s");
  assert.equal(durationGap(175, 172), "−3 s");
  assert.equal(durationGap(172, 172.2), "même durée");
  assert.equal(durationGap(null, 172), "");
  assert.equal(levelColor("sûr"), "green");
  assert.equal(levelColor("à revoir"), "orange");
  assert.equal(levelColor("introuvable"), "gray");
  assert.equal(platformName("Deezer", "Tidal, puis Deezer par l'ISRC"), "Deezer");
  assert.equal(platformName("", "MusicBrainz, par l'empreinte"), "MusicBrainz");
});

test("une clé ne repart jamais telle qu'elle est gardée", () => {
  const form = settingsForm(SETTINGS);
  assert.equal(settingsChanged(form, SETTINGS), false);
  assert.deepEqual(settingsBody(form), {
    enabled: false,
    verdict: false,
    tidal: false,
    apple_music: false,
    bandcamp: false,
  });
  const typed = { ...form, enabled: true, acoustid_key: " cle ", tidal_client_id: "id" };
  assert.equal(settingsChanged(typed, SETTINGS), true);
  assert.deepEqual(settingsBody(typed), {
    enabled: true,
    verdict: false,
    tidal: false,
    apple_music: false,
    bandcamp: false,
    acoustid_key: "cle",
    tidal_client_id: "id",
  });
  const cleared = settingsBody({ ...form, clearAcoustid: true, acoustid_key: "x", clearTidal: true });
  assert.equal(cleared.acoustid_key, "");
  assert.equal(cleared.tidal_client_id, "");
  assert.equal(cleared.tidal_client_secret, "");
});

test("la tête dit les niveaux à relire, puis les introuvables et les erreurs", () => {
  assert.deepEqual(
    levelChips({
      levels: [
        { value: "sûr", count: 3 },
        { value: "à revoir", count: 0 },
      ],
      statuses: { trouvé: 3, introuvable: 2, erreur: 1 },
    }),
    [
      { value: "sûr", count: 3 },
      { value: "introuvable", count: 2 },
      { value: "erreur", count: 1 },
    ],
  );
  assert.deepEqual(levelChips({ levels: [], statuses: {} }), []);
  assert.equal(bankLabel("rotation"), "Rotation");
  assert.equal(bankLabel("20-archives/Jazz"), "20-archives/Jazz");
});

const DECIDED = { accepted: 0, refused: 0, written: 0, waiting: [], failed: [], stale: 0, entry: null };

test("un geste se dit en clair, avec son ton", () => {
  assert.deepEqual(decidedMessage({ ...DECIDED, accepted: 3, written: 3, entry: 4 }), {
    text: "3 propositions écrites.",
    tone: "success",
  });
  assert.deepEqual(decidedMessage({ ...DECIDED, refused: 1 }), { text: "1 proposition refusée.", tone: "success" });
  assert.deepEqual(
    decidedMessage({
      ...DECIDED,
      accepted: 2,
      written: 1,
      waiting: [{ id: 3, label: "Nina Simone – Sinnerman", code: "queued", reason: "Il est en file." }],
    }),
    { text: "1 proposition écrite. « Nina Simone – Sinnerman » s'écrira après son passage à l'antenne.", tone: "info" },
  );
  assert.equal(
    decidedMessage({ ...DECIDED, accepted: 1, waiting: [{ id: 3, label: "", code: "busy", reason: "" }] }).text,
    "La bibliothèque est occupée : les valeurs acceptées s'écriront dans un instant.",
  );
  assert.deepEqual(
    decidedMessage({
      ...DECIDED,
      accepted: 2,
      failed: [
        { id: 3, label: "Brume", code: "read_only", reason: "Le moteur n'a pas le droit d'écrire son fichier." },
        { id: 4, label: "Dune", code: "missing", reason: "Son fichier a disparu du disque." },
      ],
    }),
    {
      text: "« Brume » n'a pas pu s'écrire : Le moteur n'a pas le droit d'écrire son fichier. Et 1 autre titre.",
      tone: "error",
    },
  );
  assert.deepEqual(decidedMessage({ ...DECIDED, accepted: 1, stale: 1 }), {
    text: "1 proposition a changé depuis : le titre sera cherché de nouveau.",
    tone: "info",
  });
});

test("l'état d'une proposition se lit, reportée comme en erreur", () => {
  assert.equal(propositionStatus({ state: "proposée", error: "" }), null);
  assert.deepEqual(propositionStatus({ state: "acceptée", error: "Il est à l'antenne." }), {
    label: "Reportée",
    color: "orange",
    note: "Il est à l'antenne.",
  });
  assert.equal(propositionStatus({ state: "acceptée", error: "" })?.label, "Acceptée");
  assert.equal(propositionStatus({ state: "écrite", error: "" })?.label, "Écrite");
  assert.equal(propositionStatus({ state: "en erreur", error: "" })?.note, "Elle n'a pas pu s'écrire.");
  assert.equal(propositionStatus({ state: "refusée", error: "" })?.label, "Refusée");
});

test("un lot ne prend que les propositions sûres à relire, par gestes de 500", () => {
  const prop = (id: number, level: string, state = "proposée") => ({
    id,
    field: "album",
    before: "",
    value: "x",
    level,
    why: "",
    source: "",
    state,
    error: "",
  });
  assert.deepEqual(
    sureShown([
      { id: 1, propositions: [prop(1, "sûr"), prop(2, "à revoir")] },
      { id: 2, propositions: [prop(3, "sûr", "écrite")] },
      { id: 3, propositions: [prop(4, "sûr"), prop(5, "sûr")] },
    ]),
    { ids: [1, 4, 5], titles: 2 },
  );
  assert.deepEqual(chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.equal(chunks(Array.from({ length: 1001 }, (_, i) => i)).length, 3);
});

test("la part des « oui » se lit parmi les verdicts connus, en titres", () => {
  assert.equal(verdictShare(undefined), "");
  assert.equal(verdictShare({ oui: 0, mixte: 0, non: 0 }), "");
  assert.equal(
    verdictShare({ oui: 140, mixte: 30, non: 170 }),
    "Verdict connu pour 340 titres : 140 « oui » (41 %), 30 mixtes, 170 « non ».",
  );
  assert.equal(verdictShare({ oui: 1 }), "Verdict connu pour 1 titre : 1 « oui » (100 %).");
});

test("l'aide de la requête dit la famille, et le verdict s'il est allumé", () => {
  assert.equal(queryExamples(false, true), "Exemples : grouping:matinale · genres:Jazz");
  assert.equal(queryExamples(true, false), "Exemples : grouping:matinale · genres:Jazz · famille:jazz");
  assert.equal(queryExamples(true, true), "Exemples : grouping:matinale · genres:Jazz · famille:jazz · fmg:oui");
});

test("effacer les verdicts nomme d'abord les sélections qui se videront", () => {
  assert.equal(
    eraseQuestion({ titles: 2, waiting: 1, selections: [{ id: 1, name: "Femmes", query: "fmg:oui", count: 12 }] }),
    "La sélection « Femmes » (12 titres) lit le verdict : elle se videra. Le verdict et sa source s'effacent de 2 titres de la bibliothèque, et 1 verdict en attente part. Les fichiers ne changent pas. Un titre cherché de nouveau, verdict allumé, retrouvera sa proposition.",
  );
  assert.match(
    eraseQuestion({
      titles: 1,
      waiting: 0,
      selections: [
        { id: 1, name: "Femmes", query: "fmg:oui", count: 1 },
        { id: 2, name: "Mixte", query: "fmg:mixte", count: null },
      ],
    }),
    /^Ces sélections lisent le verdict, et se videront : « Femmes » \(1 titre\), « Mixte »\./,
  );
  assert.match(eraseQuestion({ titles: 0, waiting: 0, selections: [] }), /^Aucune sélection ne lit le verdict\./);
});

test("une erreur se dit en clair, jamais par le nom technique du client", () => {
  const named = (name: string, message: string) => Object.assign(new Error(message), { name });
  assert.equal(
    fichesErrorText(named("ApiUnavailableError", "unavailable"), "x"),
    "L’automate ne répond pas. Réessaie dans un instant.",
  );
  assert.equal(fichesErrorText(named("ApiAuthError", "auth"), "x"), "Session expirée : reconnecte-toi.");
  assert.equal(
    fichesErrorText(named("ApiForbiddenError", "forbidden"), "x", "Réservé à un admin."),
    "Réservé à un admin.",
  );
  assert.equal(
    fichesErrorText(named("ApiRequestError", "Ce titre n'a pas encore de fiche."), "x"),
    "Ce titre n'a pas encore de fiche.",
  );
  assert.equal(fichesErrorText("rien", "Réessaie."), "Réessaie.");
});
