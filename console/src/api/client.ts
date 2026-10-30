import { isEngineUnreachable, isUnreachableStatus } from "./engineUnreachable";
import { apiCacheClear, apiSharedGet } from "./jsonCache";
import { isUnknownRoute, UNKNOWN_ROUTE_MESSAGE } from "./unknownRoute";

export const API_PREFIX = import.meta.env.DEV ? "/api" : "";

let csrfToken: string | null = null;
let csrfPromise: Promise<string> | null = null;

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
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

function raiseForStatus(response: Response, body?: { error?: string }): never {
  if (response.status === 401) {
    csrfToken = null;
    csrfPromise = null;
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
  if (isEngineUnreachable(response.status, detail)) throw new ApiUnavailableError();
  if (isUnknownRoute(response.status, detail)) throw new ApiRequestError(404, UNKNOWN_ROUTE_MESSAGE);
  if (detail) throw new ApiRequestError(response.status, detail);
  throw new ApiUnavailableError();
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
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

async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  if (!csrfPromise) {
    csrfPromise = (async () => {
      let response: Response;
      try {
        response = await fetch(`${API_PREFIX}/csrf.json`, {
          credentials: "include",
          cache: "no-store",
        });
      } catch {
        throw new ApiUnavailableError();
      }
      const payload = await parseJson<{ csrf_token?: string; error?: string }>(response);
      if (!response.ok) raiseForStatus(response, payload);
      if (!payload.csrf_token) {
        throw new ApiRequestError(500, "Jeton CSRF manquant.");
      }
      csrfToken = payload.csrf_token;
      return csrfToken;
    })().finally(() => {
      csrfPromise = null;
    });
  }
  return csrfPromise;
}

async function apiGetOnce<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiUnavailableError();
  }
  const payload = await parseJson<{ error?: string } & T>(response);
  if (!response.ok) raiseForStatus(response, payload);
  return payload as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiSharedGet(path, () => apiGetOnce<T>(path));
}

export function apiProbeSession(): Promise<{ csrf_token?: string }> {
  return apiGet("/csrf.json");
}

async function apiSendJson<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (path !== "/login.json") headers["X-CSRF-Token"] = await ensureCsrfToken();
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      method,
      credentials: "include",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiUnavailableError();
  }
  const payload = await parseJson<{ error?: string } & T>(response);
  if (!response.ok) raiseForStatus(response, payload);
  return payload as T;
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

export function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  return apiSendJson<T>("POST", path, body);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiSendJson<T>("PUT", path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiSendJson<T>("PATCH", path, body);
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
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": token },
      body: form,
    });
  } catch {
    throw new ApiUnavailableError();
  }
  const payload = await parseJson<{ error?: string } & T>(response);
  if (!response.ok) raiseForStatus(response, payload);
  return payload as T;
}

export async function apiBlob(path: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { credentials: "include" });
  } catch {
    throw new ApiUnavailableError();
  }
  if (!response.ok) {
    const payload = await parseJson<{ error?: string }>(response);
    raiseForStatus(response, payload);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function apiArrayBuffer(path: string): Promise<ArrayBuffer> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { credentials: "include" });
  } catch {
    throw new ApiUnavailableError();
  }
  if (!response.ok) {
    const payload = await parseJson<{ error?: string }>(response);
    raiseForStatus(response, payload);
  }
  return response.arrayBuffer();
}

export async function apiLogin(username: string, password: string): Promise<void> {
  try {
    await apiPostJson<{ ok?: boolean; username?: string; permissions?: Record<string, boolean> }>(
      "/login.json",
      { username, password },
    );
    csrfToken = null;
    csrfPromise = null;
    apiCacheClear();
    return;
  } catch (caught) {
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
    csrfPromise = null;
    apiCacheClear();
    return;
  }
  // La page de nginx devant un moteur arrêté n'est pas un mot de passe refusé.
  if (isUnreachableStatus(response.status)) throw new ApiUnavailableError();
  throw new ApiAuthError();
}

export async function apiLogout(): Promise<void> {
  try {
    await fetch(`${API_PREFIX}/logout`, {
      method: "GET",
      credentials: "include",
      redirect: "manual",
    });
  } catch {
    /* la session locale est abandonnée même si le moteur ne répond pas */
  }
  csrfToken = null;
  csrfPromise = null;
  apiCacheClear();
}
