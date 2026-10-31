import { isEngineUnreachable, isUnreachableStatus } from "./engineUnreachable";
import { apiCacheClear, apiSharedGet } from "./jsonCache";
import { isPlayoutUnavailable, PLAYOUT_UNAVAILABLE_MESSAGE } from "./playoutUnavailable";
import { READ_DEADLINE_MS, withBodyDeadline, withDeadline } from "./readDeadline";
import { NO_ANSWER_MESSAGE, SEND_DEADLINE_MS, UPLOAD_IDLE_MS, withUploadDeadline } from "./sendDeadline";
import { closeSession } from "./sessionLogout";
import { isTooManyAttempts, tooManyAttemptsMessage } from "./tooManyAttempts";
import { isUnknownRoute, UNKNOWN_ROUTE_MESSAGE } from "./unknownRoute";

// `?.` : ce module se lit aussi en node, où les parcours importent lib/brand.ts.
export const API_PREFIX = import.meta.env?.DEV ? "/api" : "";

let csrfToken: string | null = null;

export class ApiAuthError extends Error {
  constructor() {
    super("unauthenticated");
    this.name = "ApiAuthError";
  }
}

export class ApiForbiddenError extends Error {
  constructor() {
    super("forbidden");
    this.name = "ApiForbiddenError";
  }
}

export class ApiUnavailableError extends Error {
  constructor() {
    super("unavailable");
    this.name = "ApiUnavailableError";
  }
}

export class ApiRequestError extends Error {
  status: number;
  /** Le champ refusé, quand le moteur le nomme : `{error, code, message, field}`. */
  field?: string;
  constructor(status: number, message: string, field?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.field = field;
  }
}

/**
 * Un geste resté sans réponse dans son délai (`sendDeadline.ts`) : le moteur
 * l'a peut-être fait. Une ApiRequestError, pour que chaque écran montre son
 * message tel quel. Sans réponse, pas de statut HTTP : 0.
 */
export class ApiNoAnswerError extends ApiRequestError {
  constructor() {
    super(0, NO_ANSWER_MESSAGE);
    this.name = "ApiNoAnswerError";
  }
}

function raiseForStatus(response: Pick<Response, "status">, body?: { error?: string; field?: unknown; retry_in?: unknown }): never {
  if (response.status === 401) {
    csrfToken = null;
    apiCacheClear();
    throw new ApiAuthError();
  }
  if (response.status === 403) throw new ApiForbiddenError();
  if (response.status === 405) {
    throw new ApiRequestError(405, "Cette action n’est pas disponible. Recharge la page.");
  }
  if (response.status === 413) {
    throw new ApiRequestError(413, "Envoi trop lourd pour le serveur. Dépose moins de fichiers à la fois, ou des fichiers plus légers.");
  }
  const detail = body?.error?.trim();
  if (isTooManyAttempts(response.status, detail)) throw new ApiRequestError(429, tooManyAttemptsMessage(body?.retry_in));
  if (isPlayoutUnavailable(response.status, detail)) throw new ApiRequestError(502, PLAYOUT_UNAVAILABLE_MESSAGE);
  if (isEngineUnreachable(response.status, detail)) throw new ApiUnavailableError();
  if (isUnknownRoute(response.status, detail)) throw new ApiRequestError(404, UNKNOWN_ROUTE_MESSAGE);
  if (detail) {
    throw new ApiRequestError(response.status, detail, typeof body?.field === "string" ? body.field : undefined);
  }
  throw new ApiUnavailableError();
}

async function parseJson<T>(response: Response): Promise<T> {
  return parseJsonText<T>(await response.text());
}

function parseJsonText<T>(text: string): T {
  if (!text) return undefined as T;
  const trimmed = text.trimStart();
  if (trimmed.startsWith("<") || trimmed.startsWith("<!")) {
    return { error: trimmed.slice(0, 120) } as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    return { error: text.slice(0, 120) } as T;
  }
}

// Le jeton se lit comme le reste : avec le délai des lectures, et une seule
// demande à la fois, que les gestes qui l'attendent partagent. Une demande
// restée sans réponse ne retient pas le geste suivant.
async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  const payload = await apiGet<{ csrf_token?: string }>("/csrf.json");
  if (!payload?.csrf_token) {
    throw new ApiRequestError(500, "Jeton CSRF manquant.");
  }
  csrfToken = payload.csrf_token;
  return csrfToken;
}

async function apiGetOnce<T>(path: string, signal: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      credentials: "include",
      cache: "no-store",
      signal,
    });
  } catch {
    throw new ApiUnavailableError();
  }
  const payload = await parseJson<{ error?: string } & T>(response);
  if (!response.ok) raiseForStatus(response, payload);
  return payload as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiSharedGet(path, () =>
    withDeadline(READ_DEADLINE_MS, (signal) => apiGetOnce<T>(path, signal), () => new ApiUnavailableError()),
  );
}

export function apiProbeSession(): Promise<{ csrf_token?: string }> {
  return apiGet("/csrf.json");
}

async function apiSendOnce<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  headers: Record<string, string>,
  body: unknown,
  signal: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      method,
      credentials: "include",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch {
    throw new ApiUnavailableError();
  }
  const payload = await parseJson<{ error?: string } & T>(response);
  if (!response.ok) raiseForStatus(response, payload);
  return payload as T;
}

async function apiSendJson<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  deadline = SEND_DEADLINE_MS,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (path !== "/login.json") headers["X-CSRF-Token"] = await ensureCsrfToken();
  return withDeadline(
    deadline,
    (signal) => apiSendOnce<T>(method, path, headers, body, signal),
    () => new ApiNoAnswerError(),
  );
}

export async function apiSend(method: "POST" | "DELETE", path: string): Promise<void> {
  await apiSendJson<void>(method, path);
}

export function apiPost(path: string): Promise<void> {
  return apiSend("POST", path);
}

export function apiDelete(path: string): Promise<void> {
  return apiSend("DELETE", path);
}

export function apiDeleteJson<T>(path: string): Promise<T> {
  return apiSendJson<T>("DELETE", path);
}

/** `deadline` : le temps qu'a ce geste, s'il en demande plus qu'un autre (`sendDeadline.ts`). */
export function apiPostJson<T>(path: string, body: unknown, deadline?: number): Promise<T> {
  return apiSendJson<T>("POST", path, body, deadline);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiSendJson<T>("PUT", path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiSendJson<T>("PATCH", path, body);
}

type FormAnswer = { ok: boolean; status: number; text: string };

// Par XMLHttpRequest : fetch ne dit pas où en est l'envoi du corps. Chaque
// octet parti est un signe de vie, et le dernier ouvre l'attente de la réponse.
function postForm(path: string, form: FormData, token: string): Promise<FormAnswer> {
  return withUploadDeadline(
    UPLOAD_IDLE_MS,
    (signal, alive, sent) =>
      new Promise<FormAnswer>((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", `${API_PREFIX}${path}`);
        request.withCredentials = true;
        request.setRequestHeader("X-CSRF-Token", token);
        request.upload.onprogress = alive;
        request.upload.onload = sent;
        request.onload = () =>
          resolve({
            ok: request.status >= 200 && request.status < 300,
            status: request.status,
            text: request.responseText,
          });
        request.onerror = () => reject(new ApiUnavailableError());
        request.onabort = () => reject(new ApiUnavailableError());
        signal.addEventListener("abort", () => request.abort());
        request.send(form);
      }),
    () => new ApiUnavailableError(),
    () => new ApiNoAnswerError(),
  );
}

export async function apiUpload<T>(
  path: string,
  files: File | File[],
  field = "sounds",
): Promise<T> {
  const form = new FormData();
  const list = Array.isArray(files) ? files : [files];
  for (const file of list) form.append(field, file);
  const token = await ensureCsrfToken();
  const response = await postForm(path, form, token);
  const payload = parseJsonText<{ error?: string } & T>(response.text);
  if (!response.ok) raiseForStatus(response, payload);
  return payload as T;
}

// Un son se lit en entier avant d'être joué : sur un réseau lent, bien plus que
// le délai des lectures. Ce délai vaut pour la réponse, puis pour chaque
// morceau du son : seul un son qui n'avance plus est abandonné.
function apiSound<T>(path: string, read: (body: Response) => Promise<T>): Promise<T> {
  return withBodyDeadline(
    READ_DEADLINE_MS,
    async (signal) => {
      let response: Response;
      try {
        response = await fetch(`${API_PREFIX}${path}`, { credentials: "include", signal });
      } catch {
        throw new ApiUnavailableError();
      }
      if (response.ok) return response;
      // Le moteur rend lui-même en HTML l'erreur d'un son, introuvable ou absent
      // du disque : seul le statut dit qu'il est injoignable, comme sur /login.
      if (response.status === 401 || response.status === 403 || isUnreachableStatus(response.status)) {
        raiseForStatus(response);
      }
      throw new ApiRequestError(response.status, "Lecture impossible.");
    },
    read,
    () => new ApiUnavailableError(),
  );
}

export async function apiBlob(path: string): Promise<string> {
  return URL.createObjectURL(await apiSound(path, (body) => body.blob()));
}

export function apiArrayBuffer(path: string): Promise<ArrayBuffer> {
  return apiSound(path, (body) => body.arrayBuffer());
}

export async function apiLogin(username: string, password: string): Promise<void> {
  try {
    await apiPostJson<{ ok?: boolean; username?: string; permissions?: Record<string, boolean> }>(
      "/login.json",
      { username, password },
    );
    csrfToken = null;
    apiCacheClear();
    return;
  } catch (caught) {
    // Sans réponse, la session n'est pas venue : un moteur injoignable. Le
    // formulaire de repli attendrait le même moteur muet.
    if (caught instanceof ApiNoAnswerError) throw new ApiUnavailableError();
    if (caught instanceof ApiUnavailableError) {
      /* form fallback below */
    } else {
      throw caught;
    }
  }
  const body = new URLSearchParams({ username, password });
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/login`, {
      method: "POST",
      credentials: "include",
      redirect: "manual",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    throw new ApiUnavailableError();
  }
  const location = response.headers.get("Location") ?? "";
  if (location.includes("login")) throw new ApiAuthError();
  if (response.headers.get("HX-Redirect")) {
    apiCacheClear();
    return;
  }
  if (response.status === 302 || response.status === 0 || response.type === "opaqueredirect") {
    csrfToken = null;
    apiCacheClear();
    return;
  }
  // La page de nginx devant un moteur arrêté n'est pas un mot de passe refusé.
  if (isUnreachableStatus(response.status)) throw new ApiUnavailableError();
  // Trop d'essais depuis cette adresse : le moteur ou nginx la bloque.
  if (response.status === 429) {
    throw new ApiRequestError(429, tooManyAttemptsMessage(response.headers.get("Retry-After")));
  }
  throw new ApiAuthError();
}

/**
 * La session locale est abandonnée même si le moteur ne répond pas, au plus
 * tard au bout du délai des lectures. Rend false si rien ne dit que le moteur
 * a reçu la déconnexion : la session y est peut-être encore ouverte.
 */
export async function apiLogout(): Promise<boolean> {
  const reached = await closeSession((signal) =>
    fetch(`${API_PREFIX}/logout`, {
      method: "GET",
      credentials: "include",
      redirect: "manual",
      signal,
    }),
  );
  csrfToken = null;
  apiCacheClear();
  return reached;
}
