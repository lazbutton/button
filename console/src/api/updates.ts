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

export type Tone = "ok" | "warn" | "alert" | "off";
export type Line = { tone: Tone; title: string; detail: string };

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

/** Le haut de la page : la version de la station face à la plus haute publiée. */
export function versionLine(state: UpdatesState, now: Date = new Date()): Line {
  const installed = state.installed ?? "inconnue";
  const checked = state.check.at ? `vérifiée ${formatWhen(state.check.at, now)}` : "pas encore vérifiée";
  if (state.latest == null) {
    const why = state.check.error
      ? `La plus haute version publiée ne se lit pas : ${sentence(state.check.error)}`
      : "La plus haute version publiée se lit sur GitHub…";
    return { tone: "off", title: `Version ${installed}`, detail: why };
  }
  const versions = `Installée : ${installed}. Plus haute publiée : ${state.latest}, ${checked}.`;
  switch (state.blocked?.code) {
    case "up_to_date":
      return { tone: "ok", title: "À jour", detail: versions };
    case "major":
      return {
        tone: "warn",
        title: `La ${state.latest} est publiée : une majeure`,
        detail: `${versions} Elle demande une action à la station avant de la prendre : voir plus bas.`,
      };
    case "main":
      return { tone: "off", title: "La station suit main", detail: versions };
    default:
      return { tone: "warn", title: `La ${state.latest} est publiée`, detail: versions };
  }
}

const SAY_AGAIN =
  "La machine réessaie chaque minute : la mise à jour part dès que ni direct ni diffusion de l’Agenda n’est à l’antenne ou ne commence dans les 30 minutes, et qu’aucune autre commande ne tourne sur la machine.";

/** La demande ouverte : où elle en est, en une phrase, puis ce qu'il faut en savoir. */
export function requestLine(request: UpdateRequest, now: Date = new Date()): Line {
  const asked = `Demandée ${formatWhen(request.requested_at, now)}${request.requested_by ? ` par ${request.requested_by}` : ""}`;
  const toward = request.target ? `, vers la ${request.target}` : "";
  if (request.state === "running") {
    return {
      tone: "warn",
      title: `En cours depuis ${formatTime(request.started_at)}${toward}`,
      detail:
        "Une sauvegarde d’abord, puis les images, pendant que l’antenne joue, puis le redémarrage : l’antenne se coupe quelques secondes, et la console perd le contact avec le moteur le temps qu’il redémarre. La page reprend seule.",
    };
  }
  if (request.unseen) {
    return {
      tone: "alert",
      title: "La machine ne prend pas la demande",
      detail: `${asked}${toward}. La machine ne l’a pas regardée depuis ${formatTime(request.seen_at ?? request.requested_at)} : son minuteur ne tourne peut-être plus. Sur la machine : sudo station status. La demande peut se retirer.`,
    };
  }
  if (request.waiting) {
    return { tone: "warn", title: "En attente", detail: `${sentence(request.waiting)} ${SAY_AGAIN}` };
  }
  return {
    tone: "warn",
    title: `Demandée${toward}`,
    detail: `${asked}. La machine la prend dans la minute.`,
  };
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
        detail: said(
          `La mise à jour${last.to ? ` vers la ${last.to}` : ""} a échoué, et la station est revenue seule à la version d’avant${detail ? ` : ${detail.charAt(0).toLocaleLowerCase("fr-FR")}${detail.slice(1)}` : "."} Les mises à jour sont bloquées sur la machine : une fois la cause trouvée, sudo station unhold les débloque.`,
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

/** Ce que la page dit quand le moteur ne répond pas : pendant une mise à jour, c'est attendu. */
export function unreachableLine(state: UpdatesState | null): Line {
  if (state?.request?.state === "running") {
    return {
      tone: "warn",
      title: "La station redémarre",
      detail:
        "La mise à jour recrée les services du moteur : la console a perdu le contact avec lui. La page reprend seule dès qu’il répond, et dit le résultat.",
    };
  }
  return {
    tone: "alert",
    title: "Le moteur ne répond pas",
    detail:
      "La page relit son état seule. Si ça dure, regarder sur la machine : sudo station status. Ce qui suit date de la dernière lecture.",
  };
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
