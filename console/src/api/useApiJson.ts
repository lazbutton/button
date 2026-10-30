import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import { ApiAuthError, apiGet } from "./client";
import { apiCacheGet, apiCacheSet, apiSameJson } from "./jsonCache";

export type ApiLoadError = "auth" | "down";

export function useApiJson<T>(path: string, pollMs?: number) {
  const [data, setDataState] = useState<T | null>(() => apiCacheGet<T>(path) ?? null);
  const [error, setError] = useState<ApiLoadError | null>(null);
  const [loading, setLoading] = useState(() => apiCacheGet<T>(path) == null);
  const dataRef = useRef<T | null>(data);
  dataRef.current = data;
  const failsRef = useRef(0);

  const setData = useCallback(
    (update: SetStateAction<T | null>) => {
      setDataState((prev) => {
        const next = typeof update === "function" ? (update as (value: T | null) => T | null)(prev) : update;
        if (next != null) apiCacheSet(path, next);
        return next;
      });
    },
    [path],
  );

  const reload = useCallback(async () => {
    try {
      const value = await apiGet<T>(path);
      if (!apiSameJson(dataRef.current, value)) {
        apiCacheSet(path, value);
        dataRef.current = value;
        setDataState(value);
      }
      setError(null);
      failsRef.current = 0;
    } catch (caught) {
      if (caught instanceof ApiAuthError) {
        setError("auth");
        return;
      }
      // La donnée d'avant reste, mais l'écran doit savoir qu'elle n'est plus lue.
      // Un raté seul, au réveil d'un téléphone ou sur un hoquet du réseau, ne
      // le dit pas encore : le deuxième de suite, si.
      failsRef.current += 1;
      if (dataRef.current == null || failsRef.current >= 2) setError("down");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    failsRef.current = 0;
    const cached = apiCacheGet<T>(path);
    if (cached != null) {
      dataRef.current = cached;
      setDataState(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    void reload();
  }, [path, reload]);

  useEffect(() => {
    if (!pollMs) return;
    const id = window.setInterval(() => void reload(), pollMs);
    const onVis = () => {
      if (document.visibilityState === "visible") void reload();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [pollMs, reload]);

  return { data, setData, error, loading, reload };
}
