import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import {
  BANK_BATCH,
  BankCallError,
  BankUnsupportedError,
  bankShelves,
  callProblem,
  changeSummary,
  chunks,
  deleteCollection,
  MAYBE_DONE,
  moveBankFiles,
  moveNote,
  removeNote,
  removeBankFiles,
  renameCollection,
  renameProblem,
  titlesLabel,
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
  assert.equal(
    callProblem(502, "automate injoignable", true),
    "Le moteur ne répond pas au catalogue. Réessaie dans un instant.",
  );
  // nginx in front of a catalogue that is down: an HTML page, no word at all.
  for (const status of [502, 503, 504]) {
    assert.equal(callProblem(status, undefined), "Le catalogue ne répond pas. Réessaie dans un instant.");
    // A change sent: nginx gave up waiting, or the catalogue dropped it half way.
    assert.equal(callProblem(status, undefined, true), MAYBE_DONE);
  }
  assert.equal(callProblem(500, ""), "Le catalogue a refusé la demande.");
});

test("an older catalogue does not know the routes: the view says to update it", async () => {
  assert.equal(callProblem(404, "not_found"), null);
  catalogue({ status: 404, body: { error: "not_found" } }, { status: 404, body: { error: "not_found" } });
  await assert.rejects(bankShelves(), BankUnsupportedError);
  await assert.rejects(removeBankFiles("rotation", ["a.mp3"]), BankUnsupportedError);
});

test("the collections are read from the catalogue", async () => {
  catalogue({ body: { destinations: [{ ...ROTATION, count: 2, bytes: 10 }] } }, { body: {} });
  assert.deepEqual(await bankShelves(), [{ ...ROTATION, count: 2, bytes: 10 }]);
  // A reply with nothing in it is no collection, not a crash.
  assert.deepEqual(await bankShelves(), []);
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
  // nginx stopped waiting: the second batch may have been moved, in part or in full.
  assert.equal(change.stopped, MAYBE_DONE);

  // No answer in time to a change: it may have been made.
  catalogue(new DOMException("trop long", "TimeoutError"));
  const late = await removeBankFiles("rotation", ["a.mp3"]);
  assert.match(late.stopped, /le geste a peut-être été fait/);
  // The network is down: nothing was sent.
  catalogue(new TypeError("Failed to fetch"));
  assert.equal((await removeBankFiles("rotation", ["a.mp3"])).stopped, "Le catalogue ne répond pas. Réessaie dans un instant.");
});

test("what the catalogue had no time for goes first in the next batch", async () => {
  const names = ["a.wav", "b.wav", "c.wav", "d.wav"];
  const calls = catalogue(
    { body: { moved: ["a.wav"], failed: [], left: ["b.wav", "c.wav", "d.wav"] } },
    { body: { moved: ["b.wav", "c.wav"], failed: [{ name: "d.wav", reason: "déjà dans Rotation" }], left: [] } },
  );
  const progress: string[] = [];
  const change = await moveBankFiles("jazz", "rotation", names, (done, total) => progress.push(`${done}/${total}`));
  assert.deepEqual(
    calls.map((item) => (item.body as { names: string[] }).names),
    [names, ["b.wav", "c.wav", "d.wav"]],
  );
  assert.deepEqual(change, {
    done: ["a.wav", "b.wav", "c.wav"],
    failed: [{ name: "d.wav", reason: "déjà dans Rotation" }],
    stopped: "",
  });
  assert.deepEqual(progress, ["1/4", "4/4"]);

  // A catalogue that does nothing at all: no endless loop.
  catalogue({ body: { moved: [], failed: [], left: ["a.wav"] } });
  assert.equal(
    (await moveBankFiles("jazz", "rotation", ["a.wav"])).stopped,
    "Le catalogue n'a rien pu faire de ces titres. Réessaie dans un instant.",
  );
});

test("a collection is renamed and deleted by its folder name", async () => {
  const calls = catalogue(
    { body: { destination: { ...JAZZ, label: "Jazz du soir" } } },
    { body: { deleted: "jazz", trashed: 2 } },
    { status: 409, body: { error: "La collection contient encore 2 fichiers : retire ou déplace d'abord ses titres." } },
    { status: 403, body: { error: "réservé à un admin" } },
  );
  assert.equal((await renameCollection("jazz", "Jazz du soir")).label, "Jazz du soir");
  // The hidden files it kept went to the trash: the console says how many.
  assert.equal(await deleteCollection("jazz"), 2);
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

test("counts and sizes read in French", () => {
  assert.equal(titlesLabel(0), "Aucun titre");
  assert.equal(titlesLabel(1), "1 titre");
  assert.equal(titlesLabel(240), "240 titres");
  assert.deepEqual(chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(chunks([], 2), []);
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

test("the move window says whether a title keeps what it is", () => {
  // The engine moves it (ARC-09): it keeps its fiche, its place, its subfolder.
  assert.match(moveNote(1, "Jazz", true), /^Il garde sa fiche, son volume mesuré, son sous-dossier/);
  assert.match(moveNote(3, "Jazz", true), /^Ils gardent leur fiche/);
  assert.doesNotMatch(moveNote(3, "Jazz", true), /ne le trouvera plus/);
  // The catalogue moves it, as before: Beets reads it again, the Agenda loses it.
  assert.equal(
    moveNote(1, "Jazz", false),
    "L'auto-DJ le retrouve dans Jazz au prochain passage de l'indexation, environ une minute : Beets le relit " +
      "comme un titre nouveau. Une diffusion de l'Agenda qui joue un de ces fichiers ne le trouvera plus.",
  );
  assert.match(moveNote(2, "Rotation", false), /les retrouve dans Rotation .* des titres nouveaux/);
});

test("« Retirer » dit si le retrait se note au journal, et s'annule", () => {
  assert.match(removeNote(1, true), /Le retrait se note dans Sons → Journal, d'où il s'annule pendant 30 jours/);
  assert.match(removeNote(1, true), /À l'antenne ou en file, il reste où il est/);
  assert.match(removeNote(3, true), /^Les fichiers partent dans la corbeille de la banque/);
  // Le catalogue retire, comme avant : l'indexation les laisse partir à son tour suivant.
  assert.match(removeNote(2, false), /après le prochain passage de l'indexation/);
  assert.doesNotMatch(removeNote(2, false), /Journal/);
});
