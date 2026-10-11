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
    } catch (caught) {
      if (caught instanceof ApiAuthError) {
        setError("auth");
        return;
      }
      if (dataRef.current == null) setError("down");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
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
