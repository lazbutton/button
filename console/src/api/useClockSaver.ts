import { useCallback, useRef, useState } from "react";
import { saveClock } from "./clockWrite";
import type { Clock } from "./types";

export type SaveState = "idle" | "saving" | "saved" | "error";

/**
 * Every gesture on an heure type writes at once. Writes to one heure type leave one by one,
 * each with the version the previous one returned, so quick gestures never collide.
 */
export function useClockSaver(handlers: {
  /** Once nothing is left to send for this heure type: the engine's answer, and what was sent. */
  onSaved: (saved: Clock, sent: Clock) => void;
  onFailed: (caught: unknown, clockId: number) => void;
}) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;
  const pending = useRef(new Map<number, Clock>());
  const inflight = useRef(new Set<number>());
  const versions = useRef(new Map<number, number | undefined>());
  const [state, setState] = useState<SaveState>("idle");

  const flush = useCallback(async (id: number) => {
    if (inflight.current.has(id)) return;
    const next = pending.current.get(id);
    if (!next) return;
    pending.current.delete(id);
    inflight.current.add(id);
    setState("saving");
    try {
      const version = versions.current.has(id) ? versions.current.get(id) : next.version;
      const saved = await saveClock({ ...next, version });
      versions.current.set(id, saved.version);
      inflight.current.delete(id);
      if (pending.current.has(id)) {
        void flush(id);
        return;
      }
      handlersRef.current.onSaved(saved, next);
      setState(inflight.current.size || pending.current.size ? "saving" : "saved");
    } catch (caught) {
      inflight.current.delete(id);
      pending.current.delete(id);
      versions.current.delete(id);
      setState("error");
      handlersRef.current.onFailed(caught, id);
    }
  }, []);

  const save = useCallback(
    (clock: Clock) => {
      pending.current.set(clock.id, clock);
      void flush(clock.id);
    },
    [flush],
  );

  /** After the engine's copy was reloaded: its versions win. */
  const forget = useCallback((id?: number) => {
    if (id == null) versions.current.clear();
    else versions.current.delete(id);
  }, []);

  /** Something is still to send, or on its way, for this heure type. */
  const busy = useCallback((id: number) => inflight.current.has(id) || pending.current.has(id), []);

  return { save, forget, busy, state };
}
