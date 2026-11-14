import assert from "node:assert/strict";
import test from "node:test";
import {
  detailLabel,
  elapsed,
  formatClock,
  formatTime,
  formatWhen,
  historyLine,
  lastLine,
  nightlyLine,
  notesIntro,
  parseInline,
  parseNotes,
  pollDelay,
  readFailureMessage,
  releaseKind,
  splitNotes,
  statusOf,
  stepsOf,
  withCommands,
  type UpdateRelease,
  type UpdateRequest,
  type UpdatesState,
} from "./updates.ts";

/** Le 12 novembre 2026 à 15:00, à Paris : « aujourd’hui » pour les heures des exemples. */
const NOW = new Date("2026-11-12T15:00:00+01:00");

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

test("une heure de Paris se lit telle quelle, et se dit d'après le jour de Paris", () => {
  assert.equal(formatWhen("2026-11-12T04:00+01:00", NOW), "aujourd’hui à 04:00");
  assert.equal(formatWhen("2026-11-11T23:59+01:00", NOW), "hier à 23:59");
  assert.equal(formatWhen("2026-11-02T08:15+01:00", NOW), "le 02/11 à 08:15");
  assert.equal(formatWhen("2025-12-31T23:00+01:00", NOW), "le 31/12/2025 à 23:00");
  // 23:30 en UTC, 00:30 à Paris : aujourd'hui est le 13, quel que soit le fuseau de la machine.
  const night = new Date("2026-11-12T23:30:00Z");
  assert.equal(formatWhen("2026-11-13T00:10+01:00", night), "aujourd’hui à 00:10");
  assert.equal(formatWhen("2026-11-12T23:50+01:00", night), "hier à 23:50");
  // Le 1er janvier : hier est l'an passé, et une date plus ancienne dit son année.
  const newYear = new Date("2027-01-01T10:00:00+01:00");
  assert.equal(formatWhen("2026-12-31T22:00+01:00", newYear), "hier à 22:00");
  assert.equal(formatWhen("2026-12-30T22:00+01:00", newYear), "le 30/12/2026 à 22:00");
  assert.equal(formatTime("2026-11-12T23:59+01:00"), "23:59");
  assert.equal(formatClock("2026-11-12T14:05+01:00", NOW), "14:05");
  assert.equal(formatClock("2026-11-11T14:05+01:00", NOW), "hier à 14:05");
  assert.equal(formatWhen(null, NOW), "le ?");
  assert.equal(formatTime("pas une heure"), "?");
});

test("la carte d'état : une version à prendre, à jour, ou pourquoi le bouton ne demande pas", () => {
  const releases = ["1.3.0", "1.2.1"].map((version) => ({ version, published_at: null, url: null, notes: null, major: false, action: null }));
  const free = statusOf(state({ releases }), { now: NOW });
  assert.deepEqual([free.kind, free.tone, free.title, free.action], ["available", "info", "La 1.3.0 est disponible", "ask"]);
  assert.deepEqual(free.versions, { arrow: ["1.2.0", "1.3.0"], said: "2 versions · vérifiée aujourd’hui à 14:03" });
  assert.equal(statusOf(state(), { now: NOW }).versions?.said, "vérifiée aujourd’hui à 14:03");
  // À jour : pas de bouton, il ne pourrait rien demander.
  const current = statusOf(state({ installed: "1.3.0", blocked: { code: "up_to_date", message: "…" } }), { now: NOW });
  assert.deepEqual([current.kind, current.tone, current.title, current.action], ["uptodate", "ok", "À jour", null]);
  assert.equal(current.versions?.said, "1.3.0, la plus haute version publiée · vérifiée aujourd’hui à 14:03");
  // Bloquée : le titre d'après le code, la raison et la commande d'après le moteur, une fois.
  const hold = statusOf(state({ blocked: { code: "hold", message: "Bloquées (HOLD) : sudo station unhold." } }), { now: NOW });
  assert.deepEqual([hold.kind, hold.tone, hold.title, hold.detail, hold.action], [
    "blocked",
    "warn",
    "Mises à jour bloquées sur la machine",
    "Bloquées (HOLD) : sudo station unhold.",
    null,
  ]);
  assert.equal(hold.versions?.said, "Installée : 1.2.0 · plus haute publiée : 1.3.0 · vérifiée aujourd’hui à 14:03");
  const major = statusOf(state({ latest: "2.0.0", blocked: { code: "major", message: "…" } }), { now: NOW });
  assert.equal(major.title, "La 2.0.0 demande une action d’abord");
  const passed = { version: "2.0.0", action: null, url: "https://github.com/lazbutton/button/releases/tag/v2.0.0" };
  assert.equal(
    statusOf(state({ latest: "2.1.0", major: passed, blocked: { code: "major", message: "…" } })).title,
    "La 2.0.0 demande une action d’abord",
  );
  assert.equal(statusOf(state({ blocked: { code: "host_silent", message: "…" } })).tone, "alert");
  assert.equal(statusOf(state({ blocked: { code: "nouveau", message: "Une raison." } })).title, "La mise à jour ne part pas d’ici");
  const unknown = statusOf(state({ latest: null, check: { at: null, error: "GitHub répond 503", pending: false } }));
  assert.deepEqual([unknown.tone, unknown.title], ["off", "Version 1.2.0"]);
  assert.equal(unknown.detail, "La plus haute version publiée ne se lit pas : GitHub répond 503.");
  // Le moteur qui ne répond pas l'emporte sur ce qu'il disait.
  const silent = statusOf(state(), { unreachable: true, now: NOW });
  assert.deepEqual([silent.kind, silent.tone, silent.action], ["unreachable", "alert", null]);
  assert.match(silent.detail ?? "", /sudo station status/);
});

test("une demande ouverte : où elle en est, ses étapes, et depuis quand", () => {
  const fresh = statusOf(state({ request: request() }), { now: NOW });
  assert.deepEqual([fresh.kind, fresh.tone, fresh.title, fresh.action], ["pending", "info", "Demandée, vers la 1.3.0", "withdraw"]);
  assert.equal(fresh.since, "Depuis la demande : 55 min.");
  assert.deepEqual(
    fresh.steps?.map((step) => [step.label, step.state, step.meta]),
    [
      ["Demandée", "done", "14:05, par admin"],
      ["Prise par la machine", "current", "dans la minute"],
      ["Sauvegarde et images", "todo", "pendant que l’antenne joue"],
      ["Redémarrage et contrôle", "todo", "l’antenne se coupe quelques secondes"],
      ["Résultat", "todo", null],
    ],
  );
  const waiting = statusOf(state({ request: request({ waiting: "QG, un direct, en cours jusqu'à 22:00" }) }), { now: NOW });
  assert.deepEqual([waiting.kind, waiting.title, waiting.action], ["waiting", "En attente", "withdraw"]);
  assert.match(waiting.detail ?? "", /^QG, un direct, en cours jusqu'à 22:00\. La machine réessaie chaque minute/);
  assert.equal(waiting.steps?.[1].state, "waiting");
  // La machine ne la regarde pas : jamais un échec silencieux.
  const unseen = statusOf(state({ request: request({ unseen: true }) }), { now: NOW });
  assert.deepEqual([unseen.kind, unseen.tone, unseen.steps?.[1].state], ["unseen", "alert", "stuck"]);
  assert.match(unseen.detail ?? "", /ne l’a pas regardée depuis 14:05 : son minuteur ne tourne peut-être plus/);
  // Lancée : plus de retrait, la sauvegarde et les images d'abord.
  const started = request({ state: "running", started_at: "2026-11-12T14:06+01:00" });
  const running = statusOf(state({ request: started }), { now: NOW });
  assert.deepEqual([running.kind, running.title, running.action], ["running", "En cours depuis 14:06, vers la 1.3.0", null]);
  assert.deepEqual(running.steps?.map((step) => step.state), ["done", "done", "current", "todo", "todo"]);
  assert.equal(running.steps?.[1].meta, "14:06");
  // Le moteur se tait pendant la demande : c'est le redémarrage, attendu.
  const restarting = statusOf(state({ request: started }), { unreachable: true, now: NOW });
  assert.deepEqual([restarting.kind, restarting.title], ["restarting", "La station redémarre"]);
  assert.deepEqual(restarting.steps?.map((step) => step.state), ["done", "done", "done", "current", "todo"]);
  // Muet avant que la machine ne la lance : ce n'est pas un redémarrage, la page le dit.
  const silent = statusOf(state({ request: request() }), { unreachable: true, now: NOW });
  assert.deepEqual([silent.kind, silent.tone, silent.title, silent.action], ["unreachable", "alert", "Le moteur ne répond pas", null]);
  assert.equal(silent.steps?.[1].state, "current");
  // Revenu, le moteur dit encore la demande en cours : la page ne recule pas d'une étape.
  assert.deepEqual(stepsOf(started, false, true, NOW).map((step) => step.state), ["done", "done", "done", "current", "todo"]);
});

test("le temps écoulé depuis une heure de l'API", () => {
  assert.equal(elapsed("2026-11-12T14:59:30+01:00", NOW), "moins d’une minute");
  assert.equal(elapsed("2026-11-12T14:58+01:00", NOW), "2 min");
  assert.equal(elapsed("2026-11-12T13:55+01:00", NOW), "1 h 05");
  assert.equal(elapsed("2026-11-12T15:01+01:00", NOW), "moins d’une minute");
  assert.equal(elapsed(null, NOW), "?");
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
  const done = lastLine({ ...base, result: "done", detail: "redémarrée et contrôlée en 18 s" }, NOW);
  assert.deepEqual([done.tone, done.title], ["ok", "Faite : de 1.2.0 à 1.3.0"]);
  assert.equal(done.detail, "Aujourd’hui à 14:09. Redémarrée et contrôlée en 18 s.");
  assert.equal(
    lastLine({ ...base, finished_at: "2026-11-02T14:09+01:00", result: "done", detail: null }, NOW).detail,
    "Le 02/11 à 14:09. Le contrôle passe.",
  );
  const back = lastLine({ ...base, result: "rolled_back", detail: "pendant le contrôle ; revenue en 1.2.0" });
  assert.deepEqual([back.tone, back.title], ["alert", "Annulée : la station est revenue en 1.2.0"]);
  assert.match(back.detail, /vers la 1\.3\.0 a échoué, et la station est revenue seule à la version d’avant : pendant le contrôle ; revenue en 1\.2\.0\.$/);
  // HOLD et sa commande : la carte d'état les dit, une fois.
  assert.doesNotMatch(back.detail, /unhold/);
  assert.equal(lastLine({ ...base, result: "failed", detail: "Rien n'a changé." }, NOW).detail, "Aujourd’hui à 14:09. Rien n'a changé.");
  assert.equal(lastLine({ ...base, result: "refused", detail: "HOLD" }).title, "Refusée par la machine");
  assert.equal(lastLine({ ...base, result: "withdrawn", detail: "Retirée par admin." }).tone, "off");
  assert.equal(lastLine({ ...base, result: "interrupted", detail: "" }, NOW).detail, "Aujourd’hui à 14:09.");
});

test("updates.log, en français : le résultat et son ton, puis quand, et ce qu'en dit la machine", () => {
  const entry = { started_at: "2026-11-12T04:00+01:00", from: "1.1.0", to: "1.2.0", label: null, detail: null };
  assert.deepEqual(historyLine({ ...entry, result: "done", label: "faite", detail: "redémarrée et contrôlée en 21 s" }, NOW), {
    tone: "ok",
    title: "1.1.0 → 1.2.0 : faite",
    detail: "Aujourd’hui à 04:00. Redémarrée et contrôlée en 21 s.",
  });
  const stopped = historyLine(
    { ...entry, started_at: "2026-11-11T21:30+01:00", result: "stopped", detail: "QG, un direct, en cours jusqu'à 22:00" },
    NOW,
  );
  assert.deepEqual([stopped.tone, stopped.title], ["warn", "1.1.0 → 1.2.0 : arrêtée par l’antenne"]);
  assert.equal(stopped.detail, "Hier à 21:30. QG, un direct, en cours jusqu'à 22:00.");
  // Le détail dit déjà où la station est revenue : le résultat ne le redit pas.
  const back = historyLine({ ...entry, result: "rolled_back", detail: "pendant le contrôle ; revenue en 1.1.0, base remise" }, NOW);
  assert.deepEqual([back.tone, back.title], ["alert", "1.1.0 → 1.2.0 : annulée"]);
  assert.equal(back.detail, "Aujourd’hui à 04:00. Pendant le contrôle ; revenue en 1.1.0, base remise.");
  assert.equal(historyLine({ ...entry, result: "rolled_back" }, NOW).detail, "Aujourd’hui à 04:00. Revenue à la version d’avant.");
  assert.equal(historyLine({ ...entry, result: "failed", detail: "pendant les images" }, NOW).tone, "alert");
  const undone = historyLine({ ...entry, from: "1.2.0", to: "1.1.0", result: "rollback", detail: "à la main" }, NOW);
  assert.deepEqual([undone.tone, undone.title, undone.detail], ["warn", "1.2.0 → 1.1.0 : retour arrière", "Aujourd’hui à 04:00. À la main."]);
  assert.equal(historyLine({ ...entry, result: "rollback_failed", detail: "pendant le contrôle" }, NOW).title, "1.1.0 → 1.2.0 : retour arrière échoué");
  const other = historyLine({ started_at: null, from: "1.2.0", to: "1.1.0", result: "other", label: "nouveau", detail: null }, NOW);
  assert.deepEqual(other, { tone: "off", title: "1.2.0 → 1.1.0 : nouveau", detail: "" });
});

test("la nuit : ce que la machine a réglé, sans interrupteur", () => {
  assert.match(nightlyLine(state().host), /réglée pour les prendre à 04:00 \(Europe\/Paris\) : sudo station config --updates manual l’arrêtera\.$/);
  assert.match(nightlyLine(null), /^Les mises à jour de la nuit viennent avec une prochaine version de BUTTON\./);
  assert.match(nightlyLine({ ...state().host!, nightly: "manual" }), /sudo station config --updates auto les prendra\.$/);
});

test("la page se relit vite tant qu'une demande est ouverte, ou que le moteur redémarre", () => {
  assert.equal(pollDelay(state({ request: request() }), false), 5_000);
  assert.equal(pollDelay(state(), true), 10_000);
  assert.equal(pollDelay(state(), false), 60_000);
  assert.equal(pollDelay(null, false), 60_000);
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

function release(version: string, notes: string | null = null): UpdateRelease {
  return { version, published_at: null, url: null, notes, major: false, action: null };
}

test("les notes d'une version : ce qu'elle demande d'abord, le détail à déplier", () => {
  const notes = parseNotes(
    [
      "Une mineure : rien d'autre que la mise à jour habituelle. Le schéma de la base reste en v18 : aucune migration.",
      "",
      "**Ce qui change à l'antenne.** Le conducteur suit l'antenne.",
      "",
      "- Corrigé : un jingle passait trop tôt.",
      "- Corrigé : des sons en double.",
      "",
      "Un dernier mot.",
      "",
      "- Et un troisième changement.",
    ].join("\n"),
  );
  const split = splitNotes(notes);
  assert.deepEqual(
    split.lead.map((block) => block.kind),
    ["paragraph", "paragraph"],
  );
  assert.deepEqual(
    split.detail.map((block) => block.kind),
    ["list", "paragraph", "list"],
  );
  assert.equal(split.changes, 3);
  assert.equal(detailLabel("1.4.0", split.changes), "Le détail de la 1.4.0 : 3 changements");
  assert.equal(detailLabel("1.0.1", 1), "Le détail de la 1.0.1 : 1 changement");
  // Le titre qui annonce la liste part avec elle.
  const titled = splitNotes(parseNotes("Un correctif.\n\n### Console\n- Un.\n### Moteur\n- Deux.\n- Trois."));
  assert.deepEqual(
    [titled.lead.length, titled.detail.map((block) => block.kind), titled.changes],
    [1, ["heading", "list", "heading", "list"], 3],
  );
  // Sans liste, rien à déplier ; une liste seule se déplie toute.
  assert.deepEqual(splitNotes(parseNotes("Un paragraphe.\n\nUn autre.")).detail, []);
  assert.equal(splitNotes(parseNotes("- Seul changement.")).lead.length, 0);
  assert.deepEqual(splitNotes([]), { lead: [], detail: [], changes: 0 });
});

test("correctif, mineure ou majeure, d'après le numéro", () => {
  assert.equal(releaseKind("1.0.1"), "correctif");
  assert.equal(releaseKind("1.4.0"), "mineure");
  assert.equal(releaseKind("0.2.0"), "mineure");
  assert.equal(releaseKind("2.0.0"), "majeure");
  assert.equal(releaseKind("main"), null);
  assert.equal(notesIntro([]), "Aucune version plus récente que celle de la station.");
  assert.equal(notesIntro([release("1.4.0")]), "Ce que la 1.4.0 apporte.");
  assert.equal(
    notesIntro([release("1.4.0"), release("1.3.0"), release("1.2.0")]),
    "Les 3 versions que la mise à jour apporte, de la plus récente à la plus ancienne.",
  );
});

test("les commandes à taper sur la machine, en police de code, sans la suite de la phrase", () => {
  const code = (text: string) => withCommands(text).filter((item) => item.kind === "command").map((item) => item.text);
  assert.deepEqual(withCommands("Sur la machine : sudo station update --major."), [
    { kind: "text", text: "Sur la machine : " },
    { kind: "command", text: "sudo station update --major" },
    { kind: "text", text: "." },
  ]);
  assert.deepEqual(code("Pour les rallumer : sudo station config --console-requests yes."), ["sudo station config --console-requests yes"]);
  assert.deepEqual(code("une fois la cause trouvée, sudo station unhold les débloque."), ["sudo station unhold"]);
  assert.deepEqual(code("voir ses journaux : sudo station logs radiotomate-interface."), ["sudo station logs radiotomate-interface"]);
  assert.deepEqual(code("comme sudo station update : une sauvegarde d’abord"), ["sudo station update"]);
  assert.deepEqual(code("à 04:00 : sudo station config --updates manual l’arrêtera."), ["sudo station config --updates manual"]);
  // Le mot « station » dans une phrase n'est pas une commande.
  assert.deepEqual(code("La station suit main. La commande station, ou sa commande, date d'avant ce bouton."), []);
  assert.deepEqual(code("La station revient seule à la sienne."), []);
  assert.deepEqual(withCommands("Rien à taper."), [{ kind: "text", text: "Rien à taper." }]);
  assert.deepEqual(withCommands(""), []);
});
