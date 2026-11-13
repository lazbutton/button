import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import {
  BANK_BATCH,
  BankCallError,
  BankUnsupportedError,
  bankFileUrl,
  bankFiles,
  bankLabels,
  bankShelves,
  callProblem,
  changeSummary,
  chunks,
  deleteCollection,
  isAudioName,
  modifiedLabel,
  moveBankFiles,
  removeBankFiles,
  renameCollection,
  renameProblem,
  shelfFacts,
  subfolderOf,
  titlesLabel,
  toggleSelection,
} from "./bankContent.ts";
import type { BankDestination } from "./soundsView.ts";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

type Call = { url: string; method: string; body: unknown };

/** A catalogue that answers each request with the next reply, and notes what it was asked. */
function catalogue(...replies: Array<{ status?: number; body?: unknown } | Error>): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    });
    const reply = replies.shift();
    if (!reply) throw new Error("une requête de trop");
    if (reply instanceof Error) throw reply;
    return new Response(JSON.stringify(reply.body ?? {}), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}

const JAZZ: BankDestination = { id: "jazz", label: "Jazz d'été", group: "archives", folder: "20-archives/jazz" };
const ROTATION: BankDestination = { id: "rotation", label: "Rotation", group: "rotation", folder: "10-rotation" };

test("a refusal says what to do, in the catalogue's words when it has some", () => {
  assert.equal(callProblem(401, "session expirée"), "Session expirée : recharge la page et reconnecte-toi.");
  assert.equal(
    callProblem(403, "droit insuffisant"),
    "Il faut le rôle Programmateur pour changer les titres de la banque.",
  );
  assert.equal(callProblem(403, "réservé à un admin"), "Réservé à un admin.");
  assert.equal(callProblem(403, "requête d'un autre site"), "requête d'un autre site.");
  assert.equal(callProblem(404, "Collection introuvable."), "Collection introuvable.");
  assert.equal(callProblem(409, "Une collection porte déjà ce nom."), "Une collection porte déjà ce nom.");
  // The engine did not answer the catalogue: neither a session nor a right is in question.
  assert.equal(callProblem(502, "automate injoignable"), "Le moteur ne répond pas au catalogue. Réessaie dans un instant.");
  // nginx in front of a catalogue that is down: an HTML page, no word at all.
  for (const status of [502, 503, 504]) {
    assert.equal(callProblem(status, undefined), "Le catalogue ne répond pas. Réessaie dans un instant.");
  }
  assert.equal(callProblem(500, ""), "Le catalogue a refusé la demande.");
});

test("an older catalogue does not know the routes: the view says to update it", async () => {
  assert.equal(callProblem(404, "not_found"), null);
  catalogue({ status: 404, body: { error: "not_found" } }, { status: 404, body: { error: "not_found" } });
  await assert.rejects(bankShelves(), BankUnsupportedError);
  await assert.rejects(removeBankFiles("rotation", ["a.mp3"]), BankUnsupportedError);
});

test("the list asks for a page of a collection", async () => {
  const calls = catalogue(
    { body: { destinations: [{ ...ROTATION, count: 2, bytes: 10 }] } },
    {
      body: {
        destination: JAZZ,
        files: [{ name: "a.mp3", title: "A", artist: "", duration: 3, bytes: 5, modified: "2026-11-13T10:00:00+00:00" }],
        total: 40,
        matched: 1,
        bytes: 900,
        partial: true,
      },
    },
    { body: {} },
  );
  assert.deepEqual(await bankShelves(), [{ ...ROTATION, count: 2, bytes: 10 }]);
  const page = await bankFiles("jazz", { q: "  été ", offset: 100, sort: "recent" });
  assert.equal(calls[1].url, "/library/collection/files.json?id=jazz&limit=100&offset=100&q=%C3%A9t%C3%A9&sort=recent");
  assert.deepEqual([page.total, page.matched, page.partial, page.files.length], [40, 1, true, 1]);
  // A reply with nothing in it is an empty collection, not a crash.
  const empty = await bankFiles("nuit");
  assert.equal(calls[2].url, "/library/collection/files.json?id=nuit&limit=100&offset=0");
  assert.deepEqual([empty.files, empty.total, empty.partial, empty.destination.id], [[], 0, false, "nuit"]);
});

test("a file of the bank plays by its collection and its name", () => {
  assert.equal(
    bankFileUrl("jazz", "Album/Été & nuit #1.mp3"),
    "/library/collection/file?id=jazz&name=Album%2F%C3%89t%C3%A9+%26+nuit+%231.mp3",
  );
});

test("titles leave in batches, and what each batch did adds up", async () => {
  const names = Array.from({ length: BANK_BATCH + 2 }, (_, index) => `${index}.mp3`);
  const calls = catalogue(
    { body: { removed: names.slice(0, BANK_BATCH - 1), failed: [{ name: names[BANK_BATCH - 1], reason: "fichier introuvable" }] } },
    { body: { removed: names.slice(BANK_BATCH), failed: [] } },
  );
  const progress: string[] = [];
  const change = await removeBankFiles("rotation", names, (done, total) => progress.push(`${done}/${total}`));
  assert.deepEqual(calls.map((item) => [item.url, item.method]), [
    ["/library/collection/remove.json", "POST"],
    ["/library/collection/remove.json", "POST"],
  ]);
  assert.deepEqual(calls[0].body, { id: "rotation", names: names.slice(0, BANK_BATCH) });
  assert.deepEqual(calls[1].body, { id: "rotation", names: names.slice(BANK_BATCH) });
  assert.equal(change.done.length, BANK_BATCH + 1);
  assert.deepEqual(change.failed, [{ name: names[BANK_BATCH - 1], reason: "fichier introuvable" }]);
  assert.equal(change.stopped, "");
  assert.deepEqual(progress, [`${BANK_BATCH}/${BANK_BATCH + 2}`, `${BANK_BATCH + 2}/${BANK_BATCH + 2}`]);
});

test("a batch without an answer stops the rest and keeps what was done", async () => {
  const names = Array.from({ length: BANK_BATCH * 3 }, (_, index) => `${index}.mp3`);
  const calls = catalogue({ body: { moved: names.slice(0, BANK_BATCH), failed: [] } }, { status: 504 });
  const change = await moveBankFiles("rotation", "jazz", names);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].body, { id: "rotation", to: "jazz", names: names.slice(0, BANK_BATCH) });
  assert.equal(change.done.length, BANK_BATCH);
  assert.equal(change.stopped, "Le catalogue ne répond pas. Réessaie dans un instant.");

  // No answer in time to a change: it may have been made.
  catalogue(new DOMException("trop long", "TimeoutError"));
  const late = await removeBankFiles("rotation", ["a.mp3"]);
  assert.match(late.stopped, /le geste a peut-être été fait/);
  // The network is down: nothing was sent.
  catalogue(new TypeError("Failed to fetch"));
  assert.equal((await removeBankFiles("rotation", ["a.mp3"])).stopped, "Le catalogue ne répond pas. Réessaie dans un instant.");
});

test("a collection is renamed and deleted by its folder name", async () => {
  const calls = catalogue(
    { body: { destination: { ...JAZZ, label: "Jazz du soir" } } },
    { body: { deleted: "jazz" } },
    { status: 409, body: { error: "La collection contient encore 2 fichiers : retire ou déplace d'abord ses titres." } },
    { status: 403, body: { error: "réservé à un admin" } },
  );
  assert.equal((await renameCollection("jazz", "Jazz du soir")).label, "Jazz du soir");
  await deleteCollection("jazz");
  assert.deepEqual(calls.map((item) => [item.url, item.body]), [
    ["/library/collection/rename.json", { id: "jazz", label: "Jazz du soir" }],
    ["/library/collection/delete.json", { id: "jazz" }],
  ]);
  await assert.rejects(deleteCollection("jazz"), (caught: unknown) => {
    assert.ok(caught instanceof BankCallError);
    assert.equal(caught.status, 409);
    assert.match(caught.message, /contient encore 2 fichiers/);
    return true;
  });
  await assert.rejects(renameCollection("jazz", "X"), /Réservé à un admin\./);
});

test("a title shows its tags, or what its file name says", () => {
  assert.deepEqual(bankLabels({ name: "01.mp3", title: "Le chant des machines", artist: "Ada Lovelace" }), {
    artist: "Ada Lovelace",
    title: "Le chant des machines",
  });
  // No tag: the catalogue sends the name without its extension.
  assert.deepEqual(bankLabels({ name: "Ada - Song.mp3", title: "Ada - Song", artist: "" }), {
    artist: "Ada",
    title: "Song",
  });
  assert.deepEqual(bankLabels({ name: "Album/Bea - Live.flac", title: "", artist: "" }), {
    artist: "Bea",
    title: "Live",
  });
  assert.deepEqual(bankLabels({ name: "notes.txt", title: "notes", artist: "" }), { artist: "", title: "notes" });
});

test("a sound is known by its name, and so is its subfolder", () => {
  assert.equal(isAudioName("Ada - Song.MP3"), true);
  assert.equal(isAudioName("Album/01.flac"), true);
  assert.equal(isAudioName("notes.txt"), false);
  assert.equal(isAudioName("pochette.jpg"), false);
  assert.equal(subfolderOf("Ada - Song.mp3"), "");
  assert.equal(subfolderOf("Concerts/2024/01.wav"), "Concerts/2024");
});

test("counts and sizes read in French", () => {
  assert.equal(titlesLabel(0), "Aucun titre");
  assert.equal(titlesLabel(1), "1 titre");
  assert.equal(titlesLabel(240), "240 titres");
  assert.equal(shelfFacts({ count: 0, bytes: 0 }), "Vide");
  assert.equal(shelfFacts({ count: 1, bytes: 3 * 1024 * 1024 }), "1 titre · 3,0 Mo");
  assert.deepEqual(chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(chunks([], 2), []);
});

test("a date is close, then a day, then a day with its year", () => {
  const now = new Date("2026-11-13T12:00:00Z").getTime();
  assert.equal(modifiedLabel("2026-11-13T11:58:00+00:00", now), "il y a 2 min");
  assert.equal(modifiedLabel("2026-11-13T09:00:00+00:00", now), "il y a 3 h");
  assert.equal(modifiedLabel("2026-03-02T09:00:00+00:00", now), "2 mars");
  assert.equal(modifiedLabel("2024-03-02T09:00:00+00:00", now), "2 mars 2024");
  assert.equal(modifiedLabel("pas une date", now), "");
});

test("Shift takes every title between two clicks", () => {
  const order = ["a", "b", "c", "d", "e"];
  const one = toggleSelection(order, new Set(), null, "b", false);
  assert.deepEqual([...one], ["b"]);
  assert.deepEqual([...toggleSelection(order, one, "b", "d", true)].sort(), ["b", "c", "d"]);
  assert.deepEqual([...toggleSelection(order, one, "d", "a", true)].sort(), ["a", "b", "c", "d"]);
  // A second click lets go; Shift without a first click is a plain click.
  assert.deepEqual([...toggleSelection(order, one, "b", "b", false)], []);
  assert.deepEqual([...toggleSelection(order, new Set(), null, "c", true)], ["c"]);
  // The last title clicked left the list: a plain click again.
  assert.deepEqual([...toggleSelection(order, one, "parti", "e", true)].sort(), ["b", "e"]);
});

test("a change says what it did, and to which collections, in sentences", () => {
  assert.deepEqual(changeSummary("removed", { done: ["a"], failed: [], stopped: "" }, "Rotation"), {
    text: "1 titre retiré de « Rotation ».",
    tone: "success",
  });
  assert.deepEqual(changeSummary("moved", { done: ["a", "b"], failed: [], stopped: "" }, "Rotation", "Jazz d'été"), {
    text: "2 titres déplacés de « Rotation » vers « Jazz d'été ».",
    tone: "success",
  });
  const mixed = changeSummary(
    "moved",
    {
      done: ["a"],
      failed: [
        { name: "b", reason: "déjà dans Jazz d'été" },
        { name: "c", reason: "déjà dans Jazz d'été" },
        { name: "d", reason: "fichier introuvable" },
      ],
      stopped: "",
    },
    "Rotation",
    "Jazz d'été",
  );
  assert.deepEqual(mixed, {
    text: "1 titre déplacé de « Rotation » vers « Jazz d'été ». 3 titres refusés : déjà dans Jazz d'été, fichier introuvable.",
    tone: "error",
  });
  assert.deepEqual(
    changeSummary("removed", { done: [], failed: [], stopped: "Le catalogue ne répond pas." }, "Rotation"),
    { text: "Le catalogue ne répond pas.", tone: "error" },
  );
  assert.deepEqual(
    changeSummary("removed", { done: ["a"], failed: [], stopped: "Le catalogue ne répond pas." }, "Rotation"),
    { text: "1 titre retiré de « Rotation ». Arrêt avant la fin. Le catalogue ne répond pas.", tone: "error" },
  );
  assert.equal(
    changeSummary("removed", { done: [], failed: [], stopped: "" }, "Rotation").text,
    "Rien n'a changé dans « Rotation ».",
  );
});

test("a new name follows the rules of the first", () => {
  const list = [ROTATION, JAZZ, { ...JAZZ, id: "nuit", label: "Nuit" }];
  assert.equal(renameProblem(list, "jazz", "  "), "Donne un nom à la collection.");
  assert.equal(renameProblem(list, "jazz", "x".repeat(61)), "Nom trop long : 60 caractères au plus.");
  assert.equal(renameProblem(list, "jazz", "rotation"), "« Rotation » est réservé à la musique de l'auto-DJ.");
  assert.equal(renameProblem(list, "jazz", "NUIT"), "Une collection porte déjà ce nom.");
  // Its own name, written another way, is not a clash.
  assert.equal(renameProblem(list, "jazz", "Jazz d'ete"), "");
  assert.equal(renameProblem(list, "jazz", "Jazz du soir"), "");
});
