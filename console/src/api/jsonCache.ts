const memory = new Map<string, unknown>();
const inflight = new Map<string, Promise<unknown>>();

export function apiCacheGet<T>(path: string): T | undefined {
  return memory.get(path) as T | undefined;
}

export function apiCacheSet(path: string, value: unknown): void {
  memory.set(path, value);
}

export function apiCacheClear(): void {
  memory.clear();
  inflight.clear();
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
  const promise = run().finally(() => {
    if (inflight.get(path) === promise) inflight.delete(path);
  });
  inflight.set(path, promise);
  return promise;
}
