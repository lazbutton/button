/**
 * Réglages → Mises à jour (MAJ-07) : ce que dit le moteur, et ce que la page en
 * fait. La console ne touche jamais la machine : « Mettre à jour maintenant »
 * écrit une demande dans le moteur, que la machine prend dans la minute, puis
 * elle y écrit le résultat. Pur : pas de React, testable en node.
 */

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

/** « 2026-11-12T14:03+01:00 », déjà à l'heure de Paris : « 12/11/2026 à 14:03 ». */
export function formatWhen(iso: string | null | undefined): string {
  const found = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso ?? "");
  if (!found) return "?";
  const [, year, month, day, hour, minute] = found;
  return `${day}/${month}/${year} à ${hour}:${minute}`;
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
export function versionLine(state: UpdatesState): Line {
  const installed = state.installed ?? "inconnue";
  const checked = state.check.at ? `vérifiée le ${formatWhen(state.check.at)}` : "pas encore vérifiée";
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
export function requestLine(request: UpdateRequest): Line {
  const asked = `Demandée le ${formatWhen(request.requested_at)}${request.requested_by ? ` par ${request.requested_by}` : ""}`;
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
export function lastLine(last: UpdateLast): Line {
  const when = last.finished_at ? `Le ${formatWhen(last.finished_at)}.` : "";
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

const HISTORY: Record<UpdateHistoryEntry["result"], string> = {
  done: "faite",
  stopped: "arrêtée par l’antenne",
  rolled_back: "annulée, revenue à la version d’avant",
  failed: "échouée",
  rollback: "défaite à la main",
  rollback_failed: "retour arrière échoué",
  other: "",
};

/** Une ligne de updates.log, en français. */
export function historyLine(entry: UpdateHistoryEntry): { when: string; what: string } {
  const result = HISTORY[entry.result] || entry.label || "?";
  return {
    when: formatWhen(entry.started_at),
    what: `${entry.from} → ${entry.to} : ${result}${entry.detail ? `, ${entry.detail}` : ""}`,
  };
}

/**
 * Les mises à jour de la nuit (MAJ-06) ne tournent pas encore : la page dit ce
 * que la machine a réglé, sans interrupteur mort.
 */
export function nightlyLine(host: UpdateHost | null): string {
  const later =
    "Les mises à jour automatiques, chaque nuit, viennent avec une prochaine version de BUTTON. D’ici là : ce bouton, ou sudo station update sur la machine.";
  if (host?.nightly === "auto") {
    return `${later} La machine est réglée pour les prendre, à ${host.time ?? "04:00"} (${host.zone ?? "Europe/Paris"}) : station config --updates manual l’arrêtera.`;
  }
  if (host?.nightly === "manual") {
    return `${later} La machine est réglée pour s’en passer : station config --updates auto les prendra.`;
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
