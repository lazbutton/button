import assert from "node:assert/strict";
import test from "node:test";
import {
  changedElsewhere,
  changedText,
  formStillShown,
  goneText,
  isGoneRefusal,
  isVersionRefusal,
  keepEdits,
  lostText,
  saveCartSettings,
  unsavedEdits,
  withVersion,
  type CartSaveIo,
} from "./cartSave.ts";
import type { Cart, Sound } from "./types.ts";
import { UNKNOWN_ROUTE_MESSAGE } from "./unknownRoute.ts";

function bac(over: Partial<Cart> = {}): Cart {
  return {
    id: 12,
    version: 3,
    title: "Jingles",
    notes: "",
    mode: "playlist_loop",
    url: null,
    queue: "carts",
    max_duration: null,
    average_duration: 20,
    schedule_mode: "clock",
    schedule_correct: true,
    schedule_summary: "",
    schedule_advanced: false,
    schedule_year: "*",
    schedule_month: "*",
    schedule_day: "*",
    schedule_week: "*",
    schedule_day_of_week: "*",
    schedule_hour: "*",
    schedule_minute: "*",
    schedule_second: "*",
    next_sound_id: null,
    bank_folder: "30-habillage/jingles",
    ident_pads: false,
    sounds: [],
    ...over,
  };
}

/** Ce qu'envoient les réglages du bac (`CartInspector`). */
const SETTINGS = {
  title: "Jingles",
  notes: "Les idents de la matinale",
  mode: "playlist_loop",
  bank_folder: "30-habillage/jingles",
  ident_pads: false,
};

/** Une erreur du moteur telle que `client.ts` la lève : un statut, un message, parfois le champ refusé. */
class EngineError extends Error {
  status: number;
  field?: string;
  constructor(status: number, message: string, field?: string) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

const versionGone = (current: number) =>
  new EngineError(409, `Object changed since version 3; current version is ${current}.`, "version");

/** Un faux moteur : il rend ou refuse chaque envoi dans l'ordre, et note ce qu'il reçoit. */
function engine(answers: (Cart | Error)[], copies: (Cart | null)[]) {
  const sent: Record<string, unknown>[] = [];
  let reads = 0;
  const io: CartSaveIo = {
    put: async (body) => {
      sent.push(body);
      const answer = answers.shift();
      if (!answer) throw new Error("un envoi de trop");
      if (answer instanceof Error) throw answer;
      return answer;
    },
    read: async () => {
      reads += 1;
      const copy = copies.shift();
      if (copy === undefined) throw new Error("une lecture de trop");
      return copy;
    },
    // Les mêmes règles que la page (cartErrors.ts), sur l'erreur du faux moteur.
    refused: (caught) =>
      caught instanceof EngineError && isVersionRefusal(caught.status, caught.field, caught.message),
    gone: (caught) => caught instanceof EngineError && isGoneRefusal(caught.status, caught.message),
  };
  return { io, sent, reads: () => reads };
}

const son = (id: number) => ({ id, rank: id, title: `son ${id}` }) as Sound;

test("saving a bac sends the version its typing started from", async () => {
  const read = bac();
  const saved = bac({ version: 4, notes: SETTINGS.notes });
  const moteur = engine([saved], []);
  assert.deepEqual(await saveCartSettings(read, SETTINGS, moteur.io), { status: "saved", cart: saved });
  assert.deepEqual(moteur.sent, [{ ...SETTINGS, version: 3 }]);
  assert.equal(moteur.reads(), 0);
  // Un moteur qui ne rend pas la version d'un bac ne la compare pas : rien à envoyer.
  assert.deepEqual(withVersion(SETTINGS, { version: undefined }), SETTINGS);
});

test("a relay's address and duration go with its version too", async () => {
  const read = bac({ mode: "relay", url: "https://radio.example/live.mp3", max_duration: 3600, version: 7 });
  const moteur = engine([bac({ mode: "relay", version: 8 })], []);
  await saveCartSettings(read, { url: "https://radio.example/autre.mp3", max_duration: 1800 }, moteur.io);
  assert.deepEqual(moteur.sent, [{ url: "https://radio.example/autre.mp3", max_duration: 1800, version: 7 }]);
});

test("a refusal says the bac was modified elsewhere, and what", async () => {
  const read = bac();
  // L'autre onglet a changé le nom, que la page renvoie tel qu'elle l'a lu.
  const fresh = bac({ version: 4, title: "Jingles matin" });
  const moteur = engine([versionGone(4)], [fresh]);
  const result = await saveCartSettings(read, SETTINGS, moteur.io);
  assert.deepEqual(result, { status: "changed", settings: ["title"], cart: fresh });
  // Rien n'est renvoyé : le nom de l'autre onglet n'est pas écrasé.
  assert.equal(moteur.sent.length, 1);
  assert.equal(
    changedText(["title"]),
    "Ce bac vient d'être modifié ailleurs : le nom. La page s'est mise à jour, et tes changements restent à l'écran : vérifie-les, puis enregistre.",
  );
});

test("a bac changed elsewhere, but not in what the page sends, is saved again with its new version", async () => {
  const read = bac({ sounds: [son(1)] });
  // Un son ajouté ailleurs, et la durée du bac recalculée par les pages HTMX ; ou un tirage, sur un moteur plus ancien.
  const fresh = bac({ version: 4, sounds: [son(1), son(2)], average_duration: 35, next_sound_id: 2 });
  const saved = bac({ version: 5, notes: SETTINGS.notes, sounds: [son(1), son(2)] });
  const moteur = engine([versionGone(4), saved], [fresh]);
  assert.deepEqual(await saveCartSettings(read, SETTINGS, moteur.io), { status: "saved", cart: saved });
  assert.deepEqual(moteur.sent, [
    { ...SETTINGS, version: 3 },
    { ...SETTINGS, version: 4 },
  ]);
});

test("the same change made elsewhere is no conflict", async () => {
  const read = bac();
  const fresh = bac({ version: 4, notes: SETTINGS.notes });
  const saved = bac({ version: 5, notes: SETTINGS.notes });
  const moteur = engine([versionGone(4), saved], [fresh]);
  assert.equal((await saveCartSettings(read, SETTINGS, moteur.io)).status, "saved");
  assert.equal(moteur.sent.length, 2);
});

test("a bac read again while the person types: what they typed and someone else changed is refused", async () => {
  // A ouvre le bac (v3) et tape des notes. B enregistre d'autres notes (v4). A désactive un son :
  // la page relit le bac, v4, avec les notes de B ; le formulaire garde celles de A, et la v3.
  const typingStarted = bac();
  const readAgain = bac({ version: 4, notes: "Les notes de B" });
  const sent = { ...SETTINGS, notes: "Les notes de A" };
  const moteur = engine([versionGone(4)], [readAgain]);
  assert.deepEqual(await saveCartSettings(typingStarted, sent, moteur.io), {
    status: "changed",
    settings: ["notes"],
    cart: readAgain,
  });
  assert.deepEqual(moteur.sent, [{ ...sent, version: 3 }]);
});

test("a bac read again while the person types: a change elsewhere they did not touch is kept", async () => {
  // B a changé le nom. Relu par la page, le formulaire de A l'a pris : A le renvoie tel quel.
  const typingStarted = bac();
  const readAgain = bac({ version: 4, title: "Jingles matin" });
  const sent = { ...SETTINGS, title: "Jingles matin", notes: "Les notes de A" };
  const saved = bac({ version: 5, title: "Jingles matin", notes: "Les notes de A" });
  const moteur = engine([versionGone(4), saved], [readAgain]);
  assert.deepEqual(await saveCartSettings(typingStarted, sent, moteur.io), { status: "saved", cart: saved });
  assert.deepEqual(
    moteur.sent.map((body) => body.version),
    [3, 4],
  );
});

test("a second refusal is said, without a third try", async () => {
  const read = bac();
  const last = bac({ version: 5 });
  const moteur = engine([versionGone(4), versionGone(5)], [bac({ version: 4 }), last]);
  assert.deepEqual(await saveCartSettings(read, SETTINGS, moteur.io), {
    status: "changed",
    settings: [],
    cart: last,
  });
  assert.equal(moteur.sent.length, 2);
  assert.equal(moteur.reads(), 2);
  assert.equal(
    changedText([]),
    "Ce bac vient d'être modifié ailleurs. La page s'est mise à jour, et tes changements restent à l'écran : vérifie-les, puis enregistre.",
  );
});

test("a bac deleted elsewhere is gone, whether before the save or before it is read again", async () => {
  const deleted = engine([new EngineError(404, "Cart 12 not found")], []);
  assert.deepEqual(await saveCartSettings(bac(), SETTINGS, deleted.io), { status: "gone" });
  assert.equal(deleted.reads(), 0);
  const meanwhile = engine([versionGone(4)], [null]);
  assert.deepEqual(await saveCartSettings(bac(), SETTINGS, meanwhile.io), { status: "gone" });
});

test("another refusal goes up as it is, without reading the bac again", async () => {
  // Un nom déjà pris est aussi un 409, sans le champ version ; un moteur trop ancien pour la route, un 404.
  for (const refusal of [
    new EngineError(409, "Cart Jingles matin already exists"),
    new EngineError(404, UNKNOWN_ROUTE_MESSAGE),
    new EngineError(400, "Please provide a title"),
  ]) {
    const moteur = engine([refusal], []);
    await assert.rejects(saveCartSettings(bac(), SETTINGS, moteur.io), refusal);
    assert.equal(moteur.reads(), 0);
  }
});

test("only a version refusal is one, and only a bac that no longer exists is gone", () => {
  assert.equal(isVersionRefusal(409, "version", "Object changed since version 3; current version is 4."), true);
  // Un moteur qui ne nommerait pas le champ : le message suffit.
  assert.equal(isVersionRefusal(409, undefined, "Object changed since version 3; current version is 4."), true);
  assert.equal(isVersionRefusal(409, undefined, "Cart Jingles already exists"), false);
  assert.equal(isVersionRefusal(409, undefined, "Une horloge utilise ce bac."), false);
  // Une version illisible est une erreur de saisie, pas un changement ailleurs.
  assert.equal(isVersionRefusal(400, "version", "invalid version"), false);
  assert.equal(isGoneRefusal(404, "Cart 12 not found"), true);
  assert.equal(isGoneRefusal(404, UNKNOWN_ROUTE_MESSAGE), false);
  assert.equal(isGoneRefusal(409, "Cart 12 not found"), false);
});

test("what the engine sends back empty reads like what the page sends empty", () => {
  const read = bac({ bank_folder: null, ident_pads: undefined, url: null, max_duration: null, notes: "" });
  const fresh = bac({ version: 4, bank_folder: "", ident_pads: false, url: null, max_duration: null });
  const sent = { title: "Jingles", notes: "", mode: "playlist_loop", bank_folder: "", ident_pads: false };
  assert.deepEqual(changedElsewhere(read, fresh, sent), []);
  // Un réglage que la page n'envoie pas ne compte pas : l'éditeur du relais n'envoie ni le nom ni les notes.
  const relay = bac({ mode: "relay", url: "https://radio.example/a.mp3", max_duration: 600 });
  const renamed = { ...relay, version: 4, title: "Relais du soir", notes: "Partenaire" };
  assert.deepEqual(changedElsewhere(relay, renamed, { url: "https://radio.example/b.mp3", max_duration: 600 }), []);
  assert.deepEqual(
    changedElsewhere(relay, { ...renamed, max_duration: 1800 }, { url: "https://radio.example/b.mp3", max_duration: 600 }),
    ["max_duration"],
  );
});

test("the message names every setting changed elsewhere", () => {
  const read = bac();
  const fresh = bac({ version: 4, title: "Jingles matin", notes: "Autre", mode: "random" });
  const settings = changedElsewhere(read, fresh, SETTINGS);
  assert.deepEqual(settings, ["title", "notes", "mode"]);
  assert.match(changedText(settings), /^Ce bac vient d'être modifié ailleurs : le nom, les notes et la lecture\. /);
  assert.match(changedText(["notes", "ident_pads"]), /ailleurs : les notes et les pads d'idents\. /);
});

test("a bac no longer on screen is named in the message, which says nothing was saved", () => {
  assert.equal(
    lostText("Chroniques", ["notes"]),
    "« Chroniques » vient d'être modifié ailleurs : les notes. Tes changements n'y ont pas été enregistrés.",
  );
  assert.equal(
    lostText("Relais du soir", []),
    "« Relais du soir » vient d'être modifié ailleurs. Tes changements n'y ont pas été enregistrés.",
  );
});

test("a bac deleted elsewhere is named once the page shows another", () => {
  assert.equal(goneText(null), "Ce bac n'existe plus : il a peut-être été supprimé.");
  assert.equal(
    goneText("Chroniques"),
    "« Chroniques » n'existe plus : il a peut-être été supprimé. Tes changements n'y ont pas été enregistrés.",
  );
});

test("a refusal is shown by the form that saved, only while it is on screen", () => {
  const files = { mode: "playlist_loop" as const };
  const relay = { mode: "relay" as const };
  assert.equal(formStillShown("settings", 12, files, { id: 12, settings: true }), true);
  // Les réglages fermés pendant l'enregistrement, ou un autre bac choisi : la page le dit.
  assert.equal(formStillShown("settings", 12, files, { id: 12, settings: false }), false);
  assert.equal(formStillShown("settings", 12, files, { id: 13, settings: true }), false);
  assert.equal(formStillShown("relay", 12, relay, { id: 12, settings: false }), true);
  // Le relais, devenu ailleurs un bac de sons : son éditeur quitte la page.
  assert.equal(formStillShown("relay", 12, files, { id: 12, settings: true }), false);
  assert.equal(formStillShown("relay", 12, relay, { id: null, settings: false }), false);
});

test("a bac read again keeps what the person typed, and takes the rest from the engine", () => {
  const before = { title: "Jingles", notes: "", mode: "playlist_loop" };
  const current = { title: "Jingles", notes: "Les idents de la matinale", mode: "playlist_loop" };
  // L'autre onglet a changé le nom et les notes.
  const fresh = { title: "Jingles matin", notes: "Autre", mode: "playlist_loop" };
  assert.deepEqual(keepEdits(current, before, fresh), {
    title: "Jingles matin",
    notes: "Les idents de la matinale",
    mode: "playlist_loop",
  });
  // Une saisie revenue à la valeur lue suit le moteur.
  assert.deepEqual(keepEdits(before, before, fresh), fresh);
});

test("a form keeps the version its typing started from while something typed is not saved", () => {
  const before = { title: "Jingles", notes: "" };
  // Rien de tapé : le bac relu devient la base.
  assert.equal(unsavedEdits(before, before, { title: "Jingles matin", notes: "" }), false);
  // Des notes tapées, que le bac relu n'a pas : la base reste.
  assert.equal(unsavedEdits({ title: "Jingles", notes: "A" }, before, { title: "Jingles", notes: "" }), true);
  assert.equal(unsavedEdits({ title: "Jingles", notes: "A" }, before, { title: "Jingles", notes: "B" }), true);
  // Le bac relu porte ce qui a été tapé, comme après un enregistrement : plus rien à garder.
  assert.equal(unsavedEdits({ title: "Jingles", notes: "A" }, before, { title: "Jingles", notes: "A" }), false);
});
