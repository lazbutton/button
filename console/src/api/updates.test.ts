import assert from "node:assert/strict";
import test from "node:test";
import {
  formatTime,
  formatWhen,
  historyLine,
  lastLine,
  nightlyLine,
  parseInline,
  parseNotes,
  pollDelay,
  readFailureMessage,
  requestLine,
  unreachableLine,
  versionLine,
  type UpdateRequest,
  type UpdatesState,
} from "./updates.ts";

function state(over: Partial<UpdatesState> = {}): UpdatesState {
  return {
    installed: "1.2.0",
    recorded_at: "2026-11-12T04:01+01:00",
    services: [],
    latest: "1.3.0",
    check: { at: "2026-11-12T14:03+01:00", error: null, pending: false },
    releases: [],
    major: null,
    host: {
      seen_at: "2026-11-12T14:02+01:00",
      requests: true,
      command: "1.2.0",
      hold: null,
      nightly: "auto",
      time: "04:00",
      zone: "Europe/Paris",
    },
    history: [],
    request: null,
    last: null,
    blocked: null,
    ...over,
  };
}

function request(over: Partial<UpdateRequest> = {}): UpdateRequest {
  return {
    id: "abcdef012345",
    state: "pending",
    requested_at: "2026-11-12T14:05+01:00",
    requested_by: "admin",
    from: "1.2.0",
    target: "1.3.0",
    waiting: null,
    started_at: null,
    seen_at: null,
    unseen: false,
    ...over,
  };
}

test("une heure de Paris se lit telle quelle, sans fuseau du navigateur", () => {
  assert.equal(formatWhen("2026-11-12T04:00+01:00"), "12/11/2026 à 04:00");
  assert.equal(formatTime("2026-11-12T23:59+01:00"), "23:59");
  assert.equal(formatWhen(null), "?");
  assert.equal(formatTime("pas une heure"), "?");
});

test("la version de la station face à la plus haute publiée", () => {
  const free = versionLine(state());
  assert.equal(free.title, "La 1.3.0 est publiée");
  assert.equal(free.detail, "Installée : 1.2.0. Plus haute publiée : 1.3.0, vérifiée le 12/11/2026 à 14:03.");
  const current = versionLine(state({ latest: "1.2.0", blocked: { code: "up_to_date", message: "…" } }));
  assert.deepEqual([current.tone, current.title], ["ok", "À jour"]);
  const major = versionLine(state({ latest: "2.0.0", blocked: { code: "major", message: "…" } }));
  assert.equal(major.title, "La 2.0.0 est publiée : une majeure");
  assert.match(major.detail, /demande une action à la station/);
  const unknown = versionLine(state({ latest: null, check: { at: null, error: "GitHub répond 503", pending: false } }));
  assert.deepEqual([unknown.tone, unknown.title], ["off", "Version 1.2.0"]);
  assert.equal(unknown.detail, "La plus haute version publiée ne se lit pas : GitHub répond 503.");
  assert.match(versionLine(state({ latest: null, check: { at: null, error: null, pending: true } })).detail, /se lit sur GitHub/);
});

test("une demande ouverte dit où elle en est, et pourquoi elle attend", () => {
  const fresh = requestLine(request());
  assert.equal(fresh.title, "Demandée, vers la 1.3.0");
  assert.equal(fresh.detail, "Demandée le 12/11/2026 à 14:05 par admin. La machine la prend dans la minute.");
  const waiting = requestLine(request({ waiting: "QG, un direct, en cours jusqu'à 22:00" }));
  assert.equal(waiting.title, "En attente");
  assert.match(waiting.detail, /^QG, un direct, en cours jusqu'à 22:00\. La machine réessaie chaque minute/);
  const running = requestLine(request({ state: "running", started_at: "2026-11-12T14:06+01:00" }));
  assert.equal(running.title, "En cours depuis 14:06, vers la 1.3.0");
  assert.match(running.detail, /perd le contact avec le moteur/);
  // La machine ne la regarde pas : jamais un échec silencieux.
  const unseen = requestLine(request({ unseen: true }));
  assert.equal(unseen.tone, "alert");
  assert.match(unseen.detail, /ne l’a pas regardée depuis 14:05 : son minuteur ne tourne peut-être plus/);
});

test("la dernière demande : son résultat, et quoi faire ensuite", () => {
  const base = {
    id: "abcdef012345",
    requested_at: "2026-11-12T14:05+01:00",
    requested_by: "admin",
    finished_at: "2026-11-12T14:09+01:00",
    from: "1.2.0",
    to: "1.3.0",
  };
  const done = lastLine({ ...base, result: "done", detail: "redémarrée et contrôlée en 18 s" });
  assert.deepEqual([done.tone, done.title], ["ok", "Faite : de 1.2.0 à 1.3.0"]);
  assert.equal(done.detail, "Le 12/11/2026 à 14:09. Redémarrée et contrôlée en 18 s.");
  const back = lastLine({ ...base, result: "rolled_back", detail: "pendant le contrôle ; revenue en 1.2.0" });
  assert.deepEqual([back.tone, back.title], ["alert", "Annulée : la station est revenue en 1.2.0"]);
  assert.match(back.detail, /vers la 1\.3\.0 a échoué, et la station est revenue seule à la version d’avant : pendant le contrôle ; revenue en 1\.2\.0\./);
  assert.match(back.detail, /sudo station unhold/);
  assert.equal(lastLine({ ...base, result: "failed", detail: "Rien n'a changé." }).detail, "Le 12/11/2026 à 14:09. Rien n'a changé.");
  assert.equal(lastLine({ ...base, result: "refused", detail: "HOLD" }).title, "Refusée par la machine");
  assert.equal(lastLine({ ...base, result: "withdrawn", detail: "Retirée par admin." }).tone, "off");
  assert.equal(lastLine({ ...base, result: "interrupted", detail: "" }).detail, "Le 12/11/2026 à 14:09.");
});

test("updates.log, en français", () => {
  assert.deepEqual(
    historyLine({
      started_at: "2026-11-12T04:00+01:00",
      from: "1.1.0",
      to: "1.2.0",
      result: "done",
      label: "faite",
      detail: "redémarrée et contrôlée en 21 s",
    }),
    { when: "12/11/2026 à 04:00", what: "1.1.0 → 1.2.0 : faite, redémarrée et contrôlée en 21 s" },
  );
  assert.equal(
    historyLine({ started_at: null, from: "1.2.0", to: "1.1.0", result: "other", label: "nouveau", detail: null }).what,
    "1.2.0 → 1.1.0 : nouveau",
  );
});

test("la nuit : ce que la machine a réglé, sans interrupteur", () => {
  assert.match(nightlyLine(state().host), /réglée pour les prendre, à 04:00 \(Europe\/Paris\)/);
  assert.match(nightlyLine(null), /^Les mises à jour automatiques, chaque nuit, viennent avec une prochaine version/);
  assert.match(nightlyLine({ ...state().host!, nightly: "manual" }), /station config --updates auto/);
});

test("la page se relit vite tant qu'une demande est ouverte, ou que le moteur redémarre", () => {
  assert.equal(pollDelay(state({ request: request() }), false), 5_000);
  assert.equal(pollDelay(state(), true), 10_000);
  assert.equal(pollDelay(state(), false), 60_000);
  assert.equal(pollDelay(null, false), 60_000);
  assert.equal(unreachableLine(state({ request: request({ state: "running" }) })).title, "La station redémarre");
  assert.equal(unreachableLine(state()).tone, "alert");
});

test("les notes : paragraphes, listes, gras, code et liens, sans HTML", () => {
  const blocks = parseNotes(
    [
      "**Mise en service.** Poser `ICECAST_MOUNT` dans `.env`. Voir",
      "[docs/deploiement.md](https://github.com/lazbutton/button/blob/v1.0.0/docs/deploiement.md).",
      "",
      "- Une ligne,",
      "  sur deux.",
      "- Un lien [relatif](docs/x.md), et <b>rien</b> d'autre.",
      "### Console",
      "```",
      "sudo station update",
      "```",
    ].join("\n"),
  );
  assert.equal(blocks.length, 4);
  assert.deepEqual(blocks[0], {
    kind: "paragraph",
    inlines: [
      { kind: "strong", text: "Mise en service." },
      { kind: "text", text: " Poser " },
      { kind: "code", text: "ICECAST_MOUNT" },
      { kind: "text", text: " dans " },
      { kind: "code", text: ".env" },
      { kind: "text", text: ". Voir " },
      { kind: "link", text: "docs/deploiement.md", href: "https://github.com/lazbutton/button/blob/v1.0.0/docs/deploiement.md" },
      { kind: "text", text: "." },
    ],
  });
  assert.deepEqual(blocks[1], {
    kind: "list",
    items: [
      [{ kind: "text", text: "Une ligne, sur deux." }],
      [
        { kind: "text", text: "Un lien " },
        { kind: "text", text: "relatif" },
        { kind: "text", text: ", et <b>rien</b> d'autre." },
      ],
    ],
  });
  assert.deepEqual(blocks[2], { kind: "heading", inlines: [{ kind: "text", text: "Console" }] });
  assert.deepEqual(blocks[3], { kind: "code", text: "sudo station update" });
  assert.deepEqual(parseNotes(null), []);
  assert.deepEqual(parseInline("[x](javascript:alert(1))"), [
    { kind: "text", text: "x" },
    { kind: "text", text: ")" },
  ]);
});

test("une erreur du moteur se dit comme telle, jamais comme un moteur muet", () => {
  assert.match(readFailureMessage(500, "server_error"), /^Le moteur n’a pas pu lire les mises à jour \(erreur 500\)/);
  assert.equal(readFailureMessage(409, "Une mise à jour est déjà demandée."), "Une mise à jour est déjà demandée.");
  assert.equal(readFailureMessage(0, ""), "La page des mises à jour ne se lit pas. Réessaie dans un instant.");
});
