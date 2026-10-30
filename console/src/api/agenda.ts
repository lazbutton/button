import {
  API_PREFIX,
  apiDeleteJson,
  apiGet,
  ApiNoAnswerError,
  apiPostJson,
  apiPut,
  ApiUnavailableError,
} from "./client";

export type AgendaKind = "set" | "live";
export type AirStatus = "upcoming" | "on_air" | "aired" | "missed";
export type Prep = "attendu" | "analyse" | "a_revoir" | "pret";

export type AgendaGuest = {
  id: number;
  version: number;
  name: string;
  contact: string;
  token?: string;
  opened_at: string | null;
  created: string | null;
};

export type AgendaFileReport = {
  status: "pending" | "ok" | "error";
  error: string;
  format: string;
  codec: string;
  sample_rate: number | null;
  channels: number | null;
  bit_rate: number | null;
  lufs: number | null;
  warnings: string[];
};

export type AgendaFile = {
  id: number;
  path: string;
  media_id: string;
  origin: "depot" | "banque";
  original_name: string;
  duration: number;
  gain: number | null;
  late: boolean;
  created: string | null;
  report: AgendaFileReport;
};

export type Diffusion = {
  id: number;
  version: number;
  kind: AgendaKind;
  title: string;
  starts_at: string;
  ends_at: string;
  duration_min: number;
  guest: AgendaGuest | null;
  host_username: string;
  set_title: string;
  tracklist: string;
  rights: boolean;
  rights_at: string | null;
  deadline_at: string;
  deposit_closes_at: string;
  deposit_open: boolean;
  series_id: string | null;
  air_status: AirStatus;
  air_reason: string;
  aired_start: string | null;
  aired_end: string | null;
  stop_requested: boolean;
  prep: Prep;
  prep_reason: string;
  file: AgendaFile | null;
  overrun_seconds: number | null;
};

export type WeeklyOccurrence = {
  emission_id: number;
  date: string;
  title: string;
  artist: string;
  host_username: string;
  starts_at: string;
  ends_at: string;
  cancelled: boolean;
  replaced_by: number | null;
};

export type TodoRule = "set_waiting" | "review" | "link_unopened" | "live_host";

export type TodoLine = {
  diffusion_id: number;
  at: string;
  rule: TodoRule;
  text: string;
};

export type AgendaResponse = {
  enabled: boolean;
  now: string;
  from: string;
  to: string;
  diffusions: Diffusion[];
  weekly: WeeklyOccurrence[];
  todo: TodoLine[];
};

export type RepeatRule = "weekly" | "biweekly" | "monthly";

export type RepeatRequest = {
  rule: RepeatRule;
  count?: number;
  until?: string;
  nth?: number;
};

export type PreviewOccurrence = { start: string; end: string; label: string; problem: string };
export type PreviewResponse = { occurrences: PreviewOccurrence[]; nth: number };

/** What the dialog sends: Paris walls ("2026-11-07T22:00"), the server owns the hour changes. */
export type DiffusionFields = {
  kind?: AgendaKind;
  title?: string;
  start?: string;
  end?: string;
  guest_id?: number | null;
  guest_name?: string;
  host_username?: string;
  set_title?: string;
  tracklist?: string;
  repeat?: RepeatRequest;
  only?: string[];
  version?: number;
};

export function agendaPath(from: string, to: string): string {
  return `/agenda.json?from=${from}&to=${to}`;
}

export async function previewDiffusions(fields: DiffusionFields): Promise<PreviewResponse> {
  try {
    return await apiPostJson<PreviewResponse>("/agenda/diffusions/preview.json", fields);
  } catch (caught) {
    // Un aperçu ne crée rien : sans réponse, l'automate est injoignable, aucun geste n'a pu être fait.
    if (caught instanceof ApiNoAnswerError) throw new ApiUnavailableError();
    throw caught;
  }
}

export async function createDiffusions(fields: DiffusionFields): Promise<Diffusion[]> {
  const payload = await apiPostJson<{ diffusions: Diffusion[] }>("/agenda/diffusions.json", fields);
  return payload.diffusions;
}

export async function getDiffusion(id: number): Promise<Diffusion> {
  const payload = await apiGet<{ diffusion: Diffusion }>(`/agenda/diffusions/${id}.json`);
  return payload.diffusion;
}

export async function updateDiffusion(id: number, fields: DiffusionFields): Promise<Diffusion> {
  const payload = await apiPut<{ diffusion: Diffusion }>(`/agenda/diffusions/${id}.json`, fields);
  return payload.diffusion;
}

export async function deleteDiffusion(id: number, following = false): Promise<number> {
  const payload = await apiDeleteJson<{ deleted: number }>(
    `/agenda/diffusions/${id}.json${following ? "?suivantes=1" : ""}`,
  );
  return payload.deleted;
}

export async function stopDiffusion(id: number): Promise<Diffusion> {
  const payload = await apiPostJson<{ diffusion: Diffusion }>(`/agenda/diffusions/${id}/stop.json`, {});
  return payload.diffusion;
}

export async function attachBankFile(id: number, path: string, duration: number): Promise<Diffusion> {
  const payload = await apiPut<{ diffusion: Diffusion }>(`/agenda/diffusions/${id}/file.json`, {
    path,
    duration,
  });
  return payload.diffusion;
}

export async function detachFile(id: number): Promise<Diffusion> {
  const payload = await apiDeleteJson<{ diffusion: Diffusion }>(`/agenda/diffusions/${id}/file.json`);
  return payload.diffusion;
}

export function cancelOccurrence(emissionId: number, date: string): Promise<unknown> {
  return apiPostJson("/agenda/exceptions.json", { emission_id: emissionId, date });
}

export function restoreOccurrence(emissionId: number, date: string): Promise<unknown> {
  return apiDeleteJson(`/agenda/exceptions.json?emission_id=${emissionId}&date=${date}`);
}

export async function listGuests(): Promise<AgendaGuest[]> {
  const payload = await apiGet<{ guests: AgendaGuest[] }>("/agenda/guests.json");
  return payload.guests;
}

export async function renewGuestLink(id: number): Promise<AgendaGuest> {
  const payload = await apiPostJson<{ guest: AgendaGuest }>(`/agenda/guests/${id}/token.json`, {});
  return payload.guest;
}

export async function setAgendaEnabled(enabled: boolean): Promise<boolean> {
  const payload = await apiPut<{ enabled: boolean }>("/agenda/settings.json", { enabled });
  return payload.enabled;
}

export function fileAudioUrl(file: AgendaFile): string {
  return `${API_PREFIX}/agenda/files/${file.id}/audio`;
}

// -- the guest's page (no session) ----------------------------------------------

export type PublicDiffusion = {
  id: number;
  kind: AgendaKind;
  title: string;
  starts_at: string;
  ends_at: string;
  duration_min: number;
  deadline_at: string;
  deposit_closes_at: string;
  deposit_open: boolean;
  air_status: AirStatus;
  set_title: string;
  tracklist: string;
  rights: boolean;
  prep: Prep;
  prep_reason: string;
  overrun_seconds: number | null;
  file: {
    original_name: string;
    duration: number;
    late: boolean;
    status: "pending" | "ok" | "error";
    error: string;
    gain: number | null;
  } | null;
};

export type PublicGuestResponse = {
  station: string;
  guest: { name: string };
  now: string;
  max_bytes: number;
  formats: string[];
  diffusions: PublicDiffusion[];
};

export class PublicLinkError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "PublicLinkError";
    this.status = status;
  }
}

async function publicJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      ...init,
    });
  } catch {
    throw new PublicLinkError(0, "La radio ne répond pas. Réessaie dans un instant.");
  }
  let payload: { error?: string } & T;
  try {
    payload = (await response.json()) as { error?: string } & T;
  } catch {
    payload = {} as { error?: string } & T;
  }
  if (!response.ok) {
    throw new PublicLinkError(response.status, payload.error || "La radio ne répond pas. Réessaie dans un instant.");
  }
  return payload;
}

export function loadGuestPage(token: string): Promise<PublicGuestResponse> {
  return publicJson<PublicGuestResponse>(`/public/guest/${encodeURIComponent(token)}.json`);
}

export async function saveGuestDiffusion(
  token: string,
  id: number,
  fields: { set_title?: string; tracklist?: string; rights?: boolean },
): Promise<PublicDiffusion> {
  const payload = await publicJson<{ diffusion: PublicDiffusion }>(
    `/public/guest/${encodeURIComponent(token)}/diffusions/${id}.json`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    },
  );
  return payload.diffusion;
}
