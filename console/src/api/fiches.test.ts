import assert from "node:assert/strict";
import test from "node:test";
import {
  NO_FILTERS,
  bankLabel,
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
  // Un moteur sans pochettes (FON-83) ne reçoit rien d'elles ; un moteur qui les connaît, si.
  assert.equal(form.covers, null);
  assert.equal("covers" in settingsBody(form), false);
  const withCovers = settingsForm({ ...SETTINGS, covers: false });
  assert.equal(settingsChanged({ ...withCovers, covers: true }, { ...SETTINGS, covers: false }), true);
  assert.equal(settingsBody({ ...withCovers, covers: true }).covers, true);
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
