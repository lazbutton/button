/**
 * Les fiches de la bibliothèque (FON-26) : ce que la recherche propose, à relire, et
 * ses réglages. En lecture : rien ne s'accepte encore (FON-27).
 * Pur : pas de React, testable en node.
 */

export const FICHES_JSON = "/fiches.json";
export const FICHES_SETTINGS_JSON = "/fiches/reglages.json";
export const FICHES_DECISIONS_JSON = "/fiches/decisions.json";
/** Ce qu'un geste prend au plus, comme le moteur. */
export const MAX_DECISIONS = 500;

export function revertPath(id: number): string {
  return `/fiches/propositions/${id}/revenir.json`;
}

export function searchAgainPath(beetsId: number): string {
  return `/fiches/${beetsId}/rechercher.json`;
}

export type FichesCount = { value: string; count: number };

export type FicheProposition = {
  id: number;
  field: string;
  before: string;
  value: string;
  level: string;
  why: string;
  source: string;
  state: string;
  /** Acceptée, pourquoi elle attend ; en erreur, pourquoi elle ne s'est pas écrite. */
  error: string;
};

export type FicheTitle = {
  id: number;
  title: string;
  artist: string;
  album: string;
  year: number | null;
  duration: number | null;
  zone: string;
  collection: string;
  path: string;
  status: string;
  level: string;
  reasons: string[];
  source: string;
  url: string;
  propositions: FicheProposition[];
};

export type FichesPage = {
  enabled: boolean;
  progress: { library: number; searched: number; remaining_hours: number | null };
  statuses: Record<string, number>;
  levels: FichesCount[];
  fields: FichesCount[];
  states: FichesCount[];
  banks: FichesCount[];
  failures: { error: string; count: number }[];
  titles: FicheTitle[];
  total: number;
  next: number | null;
};

export type FicheDetail = {
  title: Omit<FicheTitle, "status" | "level" | "reasons" | "source" | "url" | "propositions"> & {
    label: string;
    isrc: string;
  };
  fiche: {
    status: string;
    level: string;
    reasons: string[];
    source: string;
    url: string;
    error: string;
    attempts: number;
    searched_at: string | null;
    next_at: string | null;
  };
  propositions: FicheProposition[];
  evidence: {
    found_at: string;
    platform: string;
    url: string;
    title: string;
    artists: string;
    album: string;
    duration: number | null;
    genres: string;
    year_source: string;
    doubt: string;
    /** Le lien de sa pochette, quand la station les montre (FON-83) ; absent d'un moteur plus ancien. */
    cover?: string | null;
  } | null;
  listen: string;
};

export type FichesSettings = {
  enabled: boolean;
  verdict: boolean;
  /** Les pochettes, dans la console (FON-83) ; absent d'un moteur plus ancien. */
  covers?: boolean;
  acoustid_key_set: boolean;
  sources: { tidal: boolean; apple_music: boolean; bandcamp: boolean; tidal_key_set: boolean };
  sent: string;
};

export const LEVEL_LABELS: Record<string, string> = {
  sûr: "Sûr",
  "à revoir": "À revoir",
  rapproché: "Rapproché",
  introuvable: "Introuvable",
  écarté: "Écarté",
  erreur: "En erreur",
};

export const FIELD_LABELS: Record<string, string> = {
  title: "Titre",
  artist: "Artiste",
  album: "Album",
  year: "Année",
  label: "Label",
  isrc: "ISRC",
  famille: "Famille",
  fmg: "Verdict",
};

export const STATE_LABELS: Record<string, string> = {
  proposée: "À relire",
  acceptée: "Acceptée",
  écrite: "Écrite",
  refusée: "Refusée",
  périmée: "Périmée",
  revenue: "Revenue",
  "en erreur": "En erreur",
};

/** La couleur d'un niveau : vert pour le plus sûr, orange pour ce qui demande un œil. */
export function levelColor(level: string): "green" | "orange" | "blue" | "gray" | "red" {
  if (level === "sûr") return "green";
  if (level === "à revoir") return "orange";
  if (level === "rapproché") return "blue";
  if (level === "erreur") return "red";
  return "gray";
}

/** Une banque comme le filtre la nomme : la rotation, ou le nom de sa collection. */
export function bankLabel(value: string): string {
  return value === "rotation" ? "Rotation" : value;
}

/** Les niveaux à montrer en tête : ceux qui attendent une relecture, puis les introuvables et les erreurs. */
export function levelChips(page: Pick<FichesPage, "levels" | "statuses">): FichesCount[] {
  const chips = page.levels.filter((one) => one.count > 0);
  for (const level of ["introuvable", "erreur"]) {
    const total = page.statuses[level] ?? 0;
    if (total > 0 && !chips.some((one) => one.value === level)) chips.push({ value: level, count: total });
  }
  return chips;
}

export type FichesFilters = { level: string; field: string; bank: string; state: string; q: string };

export const NO_FILTERS: FichesFilters = { level: "", field: "", bank: "", state: "", q: "" };

/** La requête de la page, ses filtres et la suite. */
export function fichesQuery(filters: FichesFilters, offset?: number | null): string {
  const params = new URLSearchParams();
  for (const name of ["level", "field", "bank", "state"] as const) {
    if (filters[name]) params.set(name, filters[name]);
  }
  const q = filters.q.trim();
  if (q) params.set("q", q);
  if (offset) params.set("offset", String(offset));
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Un nombre comme la console l'écrit : « 7 123 ». */
export function count(value: number): string {
  return new Intl.NumberFormat("fr-FR").format(value).replace(/[  ]/g, " ");
}

/** Une durée en heures, arrondie comme on la dit. */
function hoursPhrase(hours: number): string {
  if (hours < 1) return "moins d’une heure";
  if (hours < 24) return `${Math.round(hours)} h environ`;
  const days = Math.round(hours / 24);
  return days === 1 ? "une journée environ" : `${days} jours environ`;
}

/** Où en est la recherche : « 4 210 titres cherchés sur 7 123, encore 3 h environ ». */
export function progressLine(page: Pick<FichesPage, "enabled" | "progress">): string {
  const { library, searched, remaining_hours } = page.progress;
  const done =
    searched === 0
      ? `Aucun titre cherché sur ${count(library)}`
      : `${count(searched)} titre${searched === 1 ? "" : "s"} cherché${searched === 1 ? "" : "s"} sur ${count(library)}`;
  if (!page.enabled) return `${done}. La recherche est coupée.`;
  if (searched >= library) return `${done} : toute la banque est passée.`;
  if (remaining_hours == null) return `${done}, recherche en cours.`;
  return `${done}, encore ${hoursPhrase(remaining_hours)}.`;
}

/** Une valeur de fiche, lisible : l'année 0 est une année vide. */
export function fieldValue(field: string, value: string): string {
  if (field === "year" && (value === "0" || value === "")) return "—";
  return value === "" ? "—" : value;
}

/** Une durée en minutes et secondes : « 2:52 ». */
export function duration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** L'écart entre la durée du fichier et celle trouvée, s'il y en a un à dire. */
export function durationGap(file: number | null, found: number | null): string {
  if (file == null || found == null) return "";
  const gap = Math.round(found - file);
  if (gap === 0) return "même durée";
  return `${gap > 0 ? "+" : "−"}${Math.abs(gap)} s`;
}

/** « Écouter sur Deezer » : le moteur nomme la plateforme du lien ; sans elle, la source. */
export function platformName(platform: string, foundAt: string): string {
  return platform || foundAt.split(",")[0].trim() || "la source";
}

export type FichesSettingsForm = {
  enabled: boolean;
  verdict: boolean;
  /** null : le moteur ne connaît pas les pochettes. */
  covers: boolean | null;
  tidal: boolean;
  apple_music: boolean;
  bandcamp: boolean;
  /** Vide : on garde la clé posée. */
  acoustid_key: string;
  clearAcoustid: boolean;
  tidal_client_id: string;
  tidal_client_secret: string;
  clearTidal: boolean;
};

export function settingsForm(settings: FichesSettings): FichesSettingsForm {
  return {
    enabled: settings.enabled,
    verdict: settings.verdict,
    covers: typeof settings.covers === "boolean" ? settings.covers : null,
    tidal: settings.sources.tidal,
    apple_music: settings.sources.apple_music,
    bandcamp: settings.sources.bandcamp,
    acoustid_key: "",
    clearAcoustid: false,
    tidal_client_id: "",
    tidal_client_secret: "",
    clearTidal: false,
  };
}

export function settingsChanged(form: FichesSettingsForm, settings: FichesSettings): boolean {
  return (
    form.enabled !== settings.enabled ||
    form.verdict !== settings.verdict ||
    (form.covers !== null && form.covers !== settings.covers) ||
    form.tidal !== settings.sources.tidal ||
    form.apple_music !== settings.sources.apple_music ||
    form.bandcamp !== settings.sources.bandcamp ||
    form.acoustid_key.trim() !== "" ||
    form.clearAcoustid ||
    form.tidal_client_id.trim() !== "" ||
    form.tidal_client_secret.trim() !== "" ||
    form.clearTidal
  );
}

/** Le corps du PUT : une clé n'y est que saisie ou effacée, jamais renvoyée telle qu'elle est gardée. */
export function settingsBody(form: FichesSettingsForm): Record<string, unknown> {
  const body: Record<string, unknown> = {
    enabled: form.enabled,
    verdict: form.verdict,
    tidal: form.tidal,
    apple_music: form.apple_music,
    bandcamp: form.bandcamp,
  };
  if (form.covers !== null) body.covers = form.covers;
  if (form.clearAcoustid) body.acoustid_key = "";
  else if (form.acoustid_key.trim()) body.acoustid_key = form.acoustid_key.trim();
  if (form.clearTidal) {
    body.tidal_client_id = "";
    body.tidal_client_secret = "";
  } else {
    if (form.tidal_client_id.trim()) body.tidal_client_id = form.tidal_client_id.trim();
    if (form.tidal_client_secret.trim()) body.tidal_client_secret = form.tidal_client_secret.trim();
  }
  return body;
}

// -- les décisions (FON-27) --------------------------------------------------------

export type DecisionIssue = { id: number; label: string; code: string; reason: string };

export type Decided = {
  accepted: number;
  refused: number;
  written: number;
  waiting: DecisionIssue[];
  failed: DecisionIssue[];
  stale: number;
  entry: number | null;
};

function counted(value: number, one: string, many: string): string {
  return `${count(value)} ${value === 1 ? one : many}`;
}

/** Ce qu'un geste a fait, pour le message en bas de l'écran. */
export function decidedMessage(decided: Decided): { text: string; tone: "success" | "error" | "info" } {
  const parts: string[] = [];
  if (decided.written) parts.push(counted(decided.written, "proposition écrite", "propositions écrites"));
  if (decided.refused) parts.push(counted(decided.refused, "proposition refusée", "propositions refusées"));
  const head = parts.length ? `${parts.join(", ")}.` : "";
  if (decided.failed.length) {
    const [first] = decided.failed;
    const more = decided.failed.length - 1;
    const name = first.label ? `« ${first.label} »` : "Un titre";
    const text = [
      head,
      `${name} n'a pas pu s'écrire : ${first.reason}`,
      more ? `Et ${counted(more, "autre titre", "autres titres")}.` : "",
    ]
      .filter(Boolean)
      .join(" ");
    return { text, tone: "error" };
  }
  if (decided.waiting.length) {
    const busy = decided.waiting.some((one) => one.code === "busy");
    const waiting = busy
      ? "La bibliothèque est occupée : les valeurs acceptées s'écriront dans un instant."
      : decided.waiting.length === 1 && decided.waiting[0].label
        ? `« ${decided.waiting[0].label} » s'écrira après son passage à l'antenne.`
        : `${counted(decided.waiting.length, "titre s'écrira", "titres s'écriront")} après leur passage à l'antenne.`;
    return { text: [head, waiting].filter(Boolean).join(" "), tone: "info" };
  }
  if (decided.stale) {
    const stale = `${counted(decided.stale, "proposition a changé", "propositions ont changé")} depuis : le titre sera cherché de nouveau.`;
    return { text: [head, stale].filter(Boolean).join(" "), tone: "info" };
  }
  return { text: head || "Rien n'a changé.", tone: head ? "success" : "info" };
}

export type PropositionStatus = { label: string; color: "gray" | "green" | "orange" | "red" | "blue"; note: string };

/** L'état d'une proposition, comme la page le dit. Une proposition à relire n'en montre pas. */
export function propositionStatus(proposition: Pick<FicheProposition, "state" | "error">): PropositionStatus | null {
  switch (proposition.state) {
    case "proposée":
      return null;
    case "acceptée":
      return proposition.error
        ? { label: "Reportée", color: "orange", note: proposition.error }
        : { label: "Acceptée", color: "blue", note: "Elle s'écrit dans un instant." };
    case "écrite":
      return { label: "Écrite", color: "green", note: "" };
    case "en erreur":
      return { label: "En erreur", color: "red", note: proposition.error || "Elle n'a pas pu s'écrire." };
    case "périmée":
      return { label: "Périmée", color: "gray", note: "Sa valeur a changé depuis : le titre sera cherché de nouveau." };
    case "revenue":
      return { label: "Revenue", color: "gray", note: proposition.error };
    default:
      return { label: STATE_LABELS[proposition.state] ?? proposition.state, color: "gray", note: proposition.error };
  }
}

/** Les propositions sûres à relire parmi les titres affichés : ce qu'un lot accepte. */
export function sureShown(titles: Pick<FicheTitle, "id" | "propositions">[]): { ids: number[]; titles: number } {
  const ids: number[] = [];
  let withSome = 0;
  for (const title of titles) {
    const sure = title.propositions.filter((one) => one.state === "proposée" && one.level === "sûr");
    if (sure.length) withSome += 1;
    ids.push(...sure.map((one) => one.id));
  }
  return { ids, titles: withSome };
}

/** Un lot coupé en gestes que le moteur prend. */
export function chunks<T>(values: T[], size = MAX_DECISIONS): T[][] {
  const out: T[][] = [];
  for (let index = 0; index < values.length; index += size) out.push(values.slice(index, index + size));
  return out;
}
