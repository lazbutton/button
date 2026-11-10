import { useSyncExternalStore } from "react";

/** Vrai tant que la requête média tient, et suit ses changements : une fenêtre resserrée, un zoom. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
