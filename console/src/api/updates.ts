/**
 * Réglages → Mises à jour (MAJ-07) : ce que dit le moteur, et ce que la page en
 * fait. La console ne touche jamais la machine : « Mettre à jour maintenant »
 * écrit une demande dans le moteur, que la machine prend dans la minute, puis
 * elle y écrit le résultat. Pur : pas de React, testable en node.
 */

import { addDays, parisWall } from "./agendaView.ts";

export const UPDATES_JSON = "/system/updates.json";
export const UPDATES_REQUEST_JSON = "/system/updates/request.json";

export type UpdateRelease = {
  version: string;
  published_at: string | null;
  url: string | null;
  notes: string | null;
  /** Une version X.0.0 au-dessus de la station : elle demande une action d'abord. */
  major: boolean;
  /** Le paragraphe « Mise en service » de ses notes, pour une majeure. */
  action: string | null;
};

export type UpdateRequest = {
  id: string;
  /** pending : la machine ne l'a pas encore lancée ; running : la mise à jour tourne. */
  state: "pending" | "running";
  requested_at: string | null;
  requested_by: string | null;
  from: string | null;
  target: string | null;
  /** Pourquoi elle attend, dit par la machine : un direct, une autre commande. */
  waiting: string | null;
  started_at: string | null;
  seen_at: string | null;
  /** La machine ne l'a pas regardée depuis des minutes : son minuteur ne tourne pas. */
  unseen: boolean;
};

export type UpdateResult =
  | "done"
  | "rolled_back"
  | "failed"
  | "refused"
  | "up_to_date"
  | "withdrawn"
  | "interrupted";

export type UpdateLast = {
  id: string | null;
  result: UpdateResult;
  detail: string | null;
  requested_at: string | null;
  requested_by: string | null;
  finished_at: string | null;
  from: string | null;
  to: string | null;
};

/** Une ligne de updates.log, sur la machine : une mise à jour, d'ici ou de la machine. */
export type UpdateHistoryEntry = {
  started_at: string | null;
  from: string;
  to: string;
  result: "done" | "stopped" | "rolled_back" | "failed" | "rollback" | "rollback_failed" | "other";
  label: string | null;
  detail: string | null;
};

export type UpdateHost = {
  seen_at: string | null;
  /** La machine prend les demandes de la console : station config --console-requests. */
  requests: boolean;
  command: string | null;
  /** Le texte de HOLD, quand il bloque les mises à jour. */
  hold: string | null;
  nightly: "auto" | "manual" | null;
  time: string | null;
  zone: string | null;
};

export type UpdatesState = {
  installed: string | null;
  recorded_at: string | null;
  services: { service: string; image: string | null; version: string | null }[];
  latest: string | null;
  check: { at: string | null; error: string | null; pending: boolean };
  releases: UpdateRelease[];
  major: { version: string; action: string | null; url: string } | null;
  host: UpdateHost | null;
  history: UpdateHistoryEntry[];
  request: UpdateRequest | null;
  last: UpdateLast | null;
  /** Pourquoi le bouton ne demande pas, s'il ne le peut pas : jamais un bouton mort. */
  blocked: { code: string; message: string } | null;
};

/** Le ton d'un état : `info`, une mise à jour à prendre ou qui avance, sans rien d'anormal. */
export type Tone = "ok" | "warn" | "alert" | "off" | "info";
export type Line = { tone: Tone; title: string; detail: string };

/** Où en est une étape d'une mise à jour demandée. */
export type StepState = "done" | "current" | "waiting" | "stuck" | "todo";
export type Step = { label: string; meta: string | null; state: StepState };

/** La phase que dit la carte d'état, en haut de la page : elle choisit son icône. */
export type StatusKind =
  | "available"
  | "uptodate"
  | "blocked"
  | "pending"
  | "waiting"
  | "unseen"
  | "running"
  | "restarting"
  | "unreachable";

/**
 * La carte d'état : une seule phase à la fois, de la version publiée jusqu'à la
 * demande en cours, à la place de cartes empilées qui se répétaient.
 */
export type Status = {
  kind: StatusKind;
  tone: Tone;
  title: string;
  /** Ce qu'il faut en savoir, ou faire : la commande à taper n'y est dite qu'une fois. */
  detail: string | null;
  /** La version de la station et la plus haute publiée : `arrow` les montre côte à côte, quand l'une remplace l'autre. */
  versions: { arrow: [string, string] | null; said: string } | null;
  /** Les étapes d'une demande ouverte. */
  steps: Step[] | null;
  /** « Depuis la demande : 2 min. » */
  since: string | null;
  /** Le geste de la carte : demander la mise à jour, ou retirer la demande. */
  action: "ask" | "withdraw" | null;
};

/**
 * « 2026-11-12T14:03+01:00 », déjà à l'heure de Paris, dit d'après le jour de
 * `now` à Paris, quel que soit le fuseau du navigateur : « aujourd’hui à 14:03 »,
 * « hier à 14:03 », « le 12/11 à 14:03 », et l'année quand ce n'est pas celle-ci.
 */
export function formatWhen(iso: string | null | undefined, now: Date = new Date()): string {
  const found = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso ?? "");
  if (!found) return "le ?";
  const [, year, month, day, hour, minute] = found;
  const at = `${hour}:${minute}`;
  const today = parisWall(now).day;
  const date = `${year}-${month}-${day}`;
  if (date === today) return `aujourd’hui à ${at}`;
  if (date === addDays(today, -1)) return `hier à ${at}`;
  return today.startsWith(`${year}-`) ? `le ${day}/${month} à ${at}` : `le ${day}/${month}/${year} à ${at}`;
}

/** L'heure seule, aujourd'hui : « 14:03 » ; un autre jour, comme formatWhen. */
export function formatClock(iso: string | null | undefined, now: Date = new Date()): string {
  const said = formatWhen(iso, now);
  return said.startsWith("aujourd’hui à ") ? said.slice("aujourd’hui à ".length) : said;
}

/** L'heure seule : « 14:03 ». */
export function formatTime(iso: string | null | undefined): string {
  const found = /T(\d{2}):(\d{2})/.exec(iso ?? "");
  return found ? `${found[1]}:${found[2]}` : "?";
}

function sentence(text: string | null | undefined): string {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return "";
  const capital = trimmed.charAt(0).toLocaleUpperCase("fr-FR") + trimmed.slice(1);
  return /[.!?…:]$/.test(capital) ? capital : `${capital}.`;
}

/** Le temps écoulé depuis une heure de l'API : « moins d’une minute », « 2 min », « 1 h 05 ». */
export function elapsed(iso: string | null | undefined, now: Date = new Date()): string {
  const since = Date.parse(iso ?? "");
  if (!Number.isFinite(since)) return "?";
  const minutes = Math.max(0, Math.floor((now.getTime() - since) / 60_000));
  if (minutes < 1) return "moins d’une minute";
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}

// Le moteur ne rend les notes que de dix versions au plus (NOTES_MAX).
const NOTES_SHOWN = 10;

function versionsOf(state: UpdatesState, kind: "available" | "uptodate" | "blocked", now: Date): Status["versions"] {
  const checked = state.check.at ? `vérifiée ${formatWhen(state.check.at, now)}` : "pas encore vérifiée";
  const installed = state.installed ?? "inconnue";
  if (kind === "available" && state.installed && state.latest) {
    const count = state.releases.length;
    const brought = count >= NOTES_SHOWN ? `au moins ${NOTES_SHOWN} versions` : count > 1 ? `${count} versions` : "";
    return { arrow: [state.installed, state.latest], said: [brought, checked].filter(Boolean).join(" · ") };
  }
  if (kind === "uptodate") return { arrow: null, said: `${installed}, la plus haute version publiée · ${checked}` };
  if (state.latest == null) return { arrow: null, said: `Installée : ${installed}` };
  return { arrow: null, said: `Installée : ${installed} · plus haute publiée : ${state.latest} · ${checked}` };
}

const UNREACHABLE =
  "La page relit son état seule. Si ça dure, regarder sur la machine : sudo station status. Ce qui suit date de la dernière lecture.";

const SAY_AGAIN =
  "La machine réessaie chaque minute : la mise à jour part dès que ni direct ni diffusion de l’Agenda n’est à l’antenne ou ne commence dans les 30 minutes, et qu’aucune autre commande ne tourne sur la machine.";

/** Pourquoi le bouton ne demande pas, par code du moteur : le titre de la carte, et son ton. Le moteur en dit la raison. */
const BLOCKED: Record<string, { tone: Tone; title: (state: UpdatesState) => string }> = {
  hold: { tone: "warn", title: () => "Mises à jour bloquées sur la machine" },
  // La première majeure que la mise à jour passe, pas forcément la plus haute publiée.
  major: { tone: "warn", title: (state) => `La ${state.major?.version ?? state.latest} demande une action d’abord` },
  requests_off: { tone: "warn", title: () => "Demandes de la console coupées" },
  host_silent: { tone: "alert", title: () => "La machine ne donne plus de nouvelles" },
  no_host: { tone: "off", title: () => "La machine ne prend pas encore les demandes" },
  main: { tone: "off", title: () => "La station suit main" },
  unknown_version: { tone: "off", title: () => "Version de la station inconnue" },
  latest_unknown: { tone: "off", title: (state) => `Version ${state.installed ?? "inconnue"}` },
};

/**
 * La carte d'état : ce que la page dit d'abord. Une demande ouverte l'emporte,
 * puis un moteur qui ne répond pas, puis ce que dit le moteur du bouton : à
 * prendre, à jour, ou pourquoi il ne demande pas. `restarted` : la page a vu le
 * moteur se taire pendant cette demande, le redémarrage est passé.
 */
export function statusOf(
  state: UpdatesState,
  { unreachable = false, restarted = false, now = new Date() }: { unreachable?: boolean; restarted?: boolean; now?: Date } = {},
): Status {
  if (state.request) return requestStatus(state.request, unreachable, restarted, now);
  const quiet = { steps: null, since: null };
  if (unreachable) {
    return {
      ...quiet,
      kind: "unreachable",
      tone: "alert",
      title: "Le moteur ne répond pas",
      detail: UNREACHABLE,
      versions: null,
      action: null,
    };
  }
  const blocked = state.blocked;
  if (blocked == null && state.latest != null) {
    return {
      ...quiet,
      kind: "available",
      tone: "info",
      title: `La ${state.latest} est disponible`,
      detail: null,
      versions: versionsOf(state, "available", now),
      action: "ask",
    };
  }
  if (blocked?.code === "up_to_date") {
    return { ...quiet, kind: "uptodate", tone: "ok", title: "À jour", detail: null, versions: versionsOf(state, "uptodate", now), action: null };
  }
  const known = BLOCKED[blocked?.code ?? "latest_unknown"];
  const unread = state.check.error
    ? `La plus haute version publiée ne se lit pas : ${sentence(state.check.error)}`
    : "La plus haute version publiée se lit sur GitHub…";
  return {
    ...quiet,
    kind: "blocked",
    tone: known?.tone ?? "warn",
    title: known ? known.title(state) : "La mise à jour ne part pas d’ici",
    detail: blocked?.message ?? unread,
    versions: versionsOf(state, "blocked", now),
    action: null,
  };
}

function requestStatus(request: UpdateRequest, unreachable: boolean, restarted: boolean, now: Date): Status {
  const toward = request.target ? `, vers la ${request.target}` : "";
  const base = {
    versions: null,
    steps: stepsOf(request, unreachable, restarted, now),
    since: `Depuis la demande : ${elapsed(request.requested_at, now)}.`,
  };
  if (request.state === "running") {
    return unreachable
      ? {
          ...base,
          kind: "restarting",
          tone: "info",
          title: "La station redémarre",
          detail:
            "La mise à jour recrée les services du moteur : la console a perdu le contact avec lui. La page reprend seule dès qu’il répond, et dit le résultat.",
          action: null,
        }
      : {
          ...base,
          kind: "running",
          tone: "info",
          title: `En cours depuis ${formatTime(request.started_at)}${toward}`,
          detail: "Au redémarrage, la console perd le contact avec le moteur quelques instants : la page reprend seule.",
          action: null,
        };
  }
  // Muet avant que la machine ne la lance : rien d'attendu, la page le dit, avec les étapes qu'elle connaissait.
  if (unreachable) {
    return { ...base, kind: "unreachable", tone: "alert", title: "Le moteur ne répond pas", detail: UNREACHABLE, action: null };
  }
  if (request.unseen) {
    return {
      ...base,
      kind: "unseen",
      tone: "alert",
      title: "La machine ne prend pas la demande",
      detail: `La machine ne l’a pas regardée depuis ${formatTime(request.seen_at ?? request.requested_at)} : son minuteur ne tourne peut-être plus. Sur la machine : sudo station status. La demande peut se retirer.`,
      action: "withdraw",
    };
  }
  if (request.waiting) {
    return {
      ...base,
      kind: "waiting",
      tone: "info",
      title: "En attente",
      detail: `${sentence(request.waiting)} ${SAY_AGAIN}`,
      action: "withdraw",
    };
  }
  return { ...base, kind: "pending", tone: "info", title: `Demandée${toward}`, detail: null, action: "withdraw" };
}

/**
 * Les étapes d'une demande, d'après ce que dit le moteur : demandée, prise par
 * la machine, puis la sauvegarde et les images, pendant que l'antenne joue,
 * puis le redémarrage, que la page voit au silence du moteur, et le résultat.
 */
export function stepsOf(request: UpdateRequest, unreachable = false, restarted = false, now: Date = new Date()): Step[] {
  const running = request.state === "running";
  const restarting = running && (unreachable || restarted);
  const taken: Step = running
    ? { label: "Prise par la machine", meta: request.started_at ? formatClock(request.started_at, now) : null, state: "done" }
    : request.unseen
      ? { label: "Prise par la machine", meta: "pas encore : la machine ne la regarde pas", state: "stuck" }
      : request.waiting
        ? { label: "Prise par la machine", meta: "en attente", state: "waiting" }
        : { label: "Prise par la machine", meta: "dans la minute", state: "current" };
  return [
    {
      label: "Demandée",
      meta: `${formatClock(request.requested_at, now)}${request.requested_by ? `, par ${request.requested_by}` : ""}`,
      state: "done",
    },
    taken,
    {
      label: "Sauvegarde et images",
      meta: "pendant que l’antenne joue",
      state: !running ? "todo" : restarting ? "done" : "current",
    },
    { label: "Redémarrage et contrôle", meta: "l’antenne se coupe quelques secondes", state: restarting ? "current" : "todo" },
    { label: "Résultat", meta: null, state: "todo" },
  ];
}

/** La dernière demande close : son résultat, et quoi faire ensuite. */
export function lastLine(last: UpdateLast, now: Date = new Date()): Line {
  const when = last.finished_at ? sentence(formatWhen(last.finished_at, now)) : "";
  const detail = sentence(last.detail);
  const said = (text: string) => [when, text].filter(Boolean).join(" ");
  switch (last.result) {
    case "done":
      return {
        tone: "ok",
        title: last.from && last.to ? `Faite : de ${last.from} à ${last.to}` : "Faite",
        detail: said(detail || "Le contrôle passe."),
      };
    case "rolled_back":
      return {
        tone: "alert",
        title: last.from ? `Annulée : la station est revenue en ${last.from}` : "Annulée",
        // HOLD, que pose le retour arrière, et sa commande : la carte d'état les dit.
        detail: said(
          `La mise à jour${last.to ? ` vers la ${last.to}` : ""} a échoué, et la station est revenue seule à la version d’avant${detail ? ` : ${detail.charAt(0).toLocaleLowerCase("fr-FR")}${detail.slice(1)}` : "."}`,
        ),
      };
    case "failed":
      return { tone: "alert", title: "Échouée", detail: said(detail) };
    case "refused":
      return { tone: "warn", title: "Refusée par la machine", detail: said(detail) };
    case "up_to_date":
      return { tone: "ok", title: "Rien à faire : la station était à jour", detail: said(detail) };
    case "withdrawn":
      return { tone: "off", title: "Retirée", detail: said(detail) };
    case "interrupted":
      return { tone: "alert", title: "Interrompue", detail: said(detail) };
  }
}

/**
 * Ce que dit chaque résultat de updates.log, et son ton. Le détail de la ligne
 * dit déjà « pendant le contrôle ; revenue en 1.2.0 », ou « à la main » : le
 * résultat ne le redit pas, et `alone` le remplace quand la ligne n'en a pas.
 */
const HISTORY: Record<UpdateHistoryEntry["result"], { tone: Tone; label: string; alone?: string }> = {
  done: { tone: "ok", label: "faite" },
  stopped: { tone: "warn", label: "arrêtée par l’antenne" },
  rolled_back: { tone: "alert", label: "annulée", alone: "Revenue à la version d’avant." },
  failed: { tone: "alert", label: "échouée" },
  rollback: { tone: "warn", label: "retour arrière", alone: "Fait à la main." },
  rollback_failed: { tone: "alert", label: "retour arrière échoué" },
  other: { tone: "off", label: "" },
};

/**
 * Une ligne de updates.log, en français : les versions et le résultat, avec son
 * ton, puis quand, et ce que la machine en a dit.
 */
export function historyLine(entry: UpdateHistoryEntry, now: Date = new Date()): Line {
  const said = HISTORY[entry.result];
  const result = said.label || entry.label || "?";
  const when = entry.started_at ? sentence(formatWhen(entry.started_at, now)) : "";
  return {
    tone: said.tone,
    title: `${entry.from} → ${entry.to} : ${result}`,
    detail: [when, sentence(entry.detail) || said.alone].filter(Boolean).join(" "),
  };
}

/**
 * Les mises à jour de la nuit (MAJ-06) ne tournent pas encore : la carte de la
 * machine le dit, avec ce qu'elle a réglé, sans interrupteur mort.
 */
export function nightlyLine(host: UpdateHost | null): string {
  const later =
    "Les mises à jour de la nuit viennent avec une prochaine version de BUTTON. D’ici là : ce bouton, ou sudo station update sur la machine.";
  if (host?.nightly === "auto") {
    return `${later} La machine est réglée pour les prendre à ${host.time ?? "04:00"} (${host.zone ?? "Europe/Paris"}) : sudo station config --updates manual l’arrêtera.`;
  }
  if (host?.nightly === "manual") {
    return `${later} La machine est réglée pour s’en passer : sudo station config --updates auto les prendra.`;
  }
  return later;
}

/**
 * Tous les combien relire la page : vite tant qu'une demande est ouverte, ou que
 * le moteur ne répond plus pendant une mise à jour ; sinon, une fois la minute.
 */
export function pollDelay(state: UpdatesState | null, unreachable: boolean): number {
  if (state?.request) return 5_000;
  if (unreachable) return 10_000;
  return 60_000;
}

/**
 * Une lecture refusée autrement que par la session, le droit ou un moteur trop
 * ancien : ce que la page en dit. Une erreur du moteur n'est pas un moteur qui
 * ne répond pas, et son « server_error » ne s'affiche pas tel quel.
 */
export function readFailureMessage(status: number, message: string): string {
  if (status >= 500) {
    return `Le moteur n’a pas pu lire les mises à jour (erreur ${status}). Si ça dure, voir ses journaux sur la machine : sudo station logs radiotomate-interface.`;
  }
  const said = message.trim();
  return said && status > 0 ? said : "La page des mises à jour ne se lit pas. Réessaie dans un instant.";
}

// --- Les notes de version : un peu de Markdown, rendu sans HTML ---

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "strong"; text: string }
  | { kind: "code"; text: string }
  /** Une commande à taper sur la machine : elle ne se coupe qu'entre ses mots. */
  | { kind: "command"; text: string }
  | { kind: "link"; text: string; href: string };

export type NoteBlock =
  | { kind: "paragraph"; inlines: Inline[] }
  | { kind: "heading"; inlines: Inline[] }
  | { kind: "list"; items: Inline[][] }
  | { kind: "code"; text: string };

const INLINE = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\))/g;

/** Le gras, le code et les liens d'une ligne. Un lien qui n'est pas en http(s) reste du texte. */
export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const found of text.matchAll(INLINE)) {
    const at = found.index ?? 0;
    if (at > last) out.push({ kind: "text", text: text.slice(last, at) });
    if (found[2] != null) out.push({ kind: "strong", text: found[2] });
    else if (found[3] != null) out.push({ kind: "code", text: found[3] });
    else if (/^https?:\/\//.test(found[5] ?? "")) out.push({ kind: "link", text: found[4] ?? "", href: found[5] ?? "" });
    else out.push({ kind: "text", text: found[4] ?? "" });
    last = at + found[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

/**
 * Les notes d'une version, telles que version.yml les publie : la partie de
 * CHANGELOG.md, en paragraphes, listes à tirets, titres et blocs de code.
 */
export function parseNotes(notes: string | null | undefined): NoteBlock[] {
  const blocks: NoteBlock[] = [];
  let paragraph: string[] = [];
  let items: string[] = [];
  let code: string[] | null = null;
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", inlines: parseInline(paragraph.join(" ")) });
    if (items.length) blocks.push({ kind: "list", items: items.map(parseInline) });
    paragraph = [];
    items = [];
  };
  for (const raw of (notes ?? "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (/^\s*(```|~~~)/.test(line)) {
      if (code == null) {
        flush();
        code = [];
      } else {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      }
      continue;
    }
    if (code != null) {
      code.push(raw);
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    const item = /^\s{0,3}[-*]\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ kind: "heading", inlines: parseInline(heading[1]) });
    } else if (item) {
      if (paragraph.length) {
        blocks.push({ kind: "paragraph", inlines: parseInline(paragraph.join(" ")) });
        paragraph = [];
      }
      items.push(item[1]);
    } else if (items.length && /^\s/.test(line)) {
      items[items.length - 1] += ` ${line.trim()}`;
    } else {
      if (items.length) {
        blocks.push({ kind: "list", items: items.map(parseInline) });
        items = [];
      }
      paragraph.push(line.trim());
    }
  }
  if (code != null) blocks.push({ kind: "code", text: code.join("\n") });
  flush();
  return blocks;
}

/**
 * Les notes d'une version en deux. D'abord ce qu'il faut savoir avant de la
 * prendre : la tête des notes, qui dit ce que la version demande à la station
 * (docs/developpement.md, « Publier une version »). Puis le détail des
 * changements, à déplier : de la première liste, avec le titre qui la précède,
 * jusqu'à la fin. Sans liste, tout se lit d'emblée.
 */
export function splitNotes(blocks: NoteBlock[]): { lead: NoteBlock[]; detail: NoteBlock[]; changes: number } {
  let cut = blocks.findIndex((block) => block.kind === "list");
  if (cut < 0) return { lead: blocks, detail: [], changes: 0 };
  if (cut > 0 && blocks[cut - 1].kind === "heading") cut -= 1;
  const detail = blocks.slice(cut);
  const changes = detail.reduce((count, block) => count + (block.kind === "list" ? block.items.length : 0), 0);
  return { lead: blocks.slice(0, cut), detail, changes };
}

/** Ce qui déplie le détail d'une version, nommée : la page en montre plusieurs. */
export function detailLabel(version: string, changes: number): string {
  return `Le détail de la ${version} : ${changes} changement${changes > 1 ? "s" : ""}`;
}

/** Correctif, mineure ou majeure, d'après le numéro : la règle des versions, dans docs/developpement.md. */
export function releaseKind(version: string): "correctif" | "mineure" | "majeure" | null {
  const found = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  if (!found) return null;
  if (found[3] !== "0") return "correctif";
  return found[2] !== "0" ? "mineure" : "majeure";
}

/** Ce que dit la carte des notes, d'après le nombre de versions que la mise à jour apporte. */
export function notesIntro(releases: UpdateRelease[]): string {
  if (!releases.length) return "Aucune version plus récente que celle de la station.";
  if (releases.length === 1) return `Ce que la ${releases[0].version} apporte.`;
  return `Les ${releases.length} versions que la mise à jour apporte, de la plus récente à la plus ancienne.`;
}

// --- Les commandes à taper sur la machine ---

/**
 * Une commande de la machine dans un texte de la page ou du moteur : station,
 * avec ou sans sudo, l'une de ses commandes, ses options et leur valeur, et le
 * service que lit logs. La suite de la phrase n'en fait pas partie : « sudo
 * station unhold les débloque ».
 */
const COMMAND =
  /(?<![\w-])(?:sudo )?station (?:update|rollback|unhold|hold|status|config|logs|backup|restore|requests)(?![\w-])(?: --[a-z][a-z-]*(?: (?:yes|no|auto|manual)(?![\w-]))?)*(?: (?:radiotomate-[a-z]+|console|catalog|nowplaying|icecast|tusd)(?![\w-]))?/g;

/** Un texte de la page, ses commandes à taper sur la machine en police de code. */
export function withCommands(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const found of text.matchAll(COMMAND)) {
    const at = found.index ?? 0;
    if (at > last) out.push({ kind: "text", text: text.slice(last, at) });
    out.push({ kind: "command", text: found[0] });
    last = at + found[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}
