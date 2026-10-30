const memory = new Map<string, unknown>();
const inflight = new Map<string, Promise<unknown>>();
/** L'heure de la dernière réponse du moteur, par chemin, en ms. */
const answeredAt = new Map<string, number>();

export function apiCacheGet<T>(path: string): T | undefined {
  return memory.get(path) as T | undefined;
}

export function apiCacheSet(path: string, value: unknown): void {
  memory.set(path, value);
}

export function apiCacheClear(): void {
  memory.clear();
  inflight.clear();
  answeredAt.clear();
}

/** Quand le moteur a donné ce chemin pour la dernière fois, à n'importe quel écran. */
export function apiAnsweredAt(path: string): number | undefined {
  return answeredAt.get(path);
}

export function apiCacheDrop(path: string): void {
  memory.delete(path);
  inflight.delete(path);
}

export function apiSameJson(left: unknown, right: unknown): boolean {
  try {
    return JSON.stringify(left) === JSON.stringify(right);
  } catch {
    return false;
  }
}

export function apiSharedGet<T>(path: string, run: () => Promise<T>): Promise<T> {
  const existing = inflight.get(path);
  if (existing) return existing as Promise<T>;
  const promise = run()
    .then((value) => {
      answeredAt.set(path, Date.now());
      return value;
    })
    .finally(() => {
      if (inflight.get(path) === promise) inflight.delete(path);
    });
  inflight.set(path, promise);
  return promise;
}
