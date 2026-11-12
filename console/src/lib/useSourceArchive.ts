import { useCallback, useEffect, useRef, useState } from "react";
import { sourceStore, type SourceArchive } from "../api/sourceCode";

// Une seule pour la page : le menu du compte et l'onglet Station lisent la même.
const store = sourceStore();

/**
 * L'archive du code que sert la station (api/sourceCode.ts), ou null : absente, ou pas
 * encore lue. Lue au montage ; `refresh` la relit, à chaque ouverture du menu du compte.
 */
export function useSourceArchive(): { archive: SourceArchive | null; refresh: () => void } {
  const [archive, setArchive] = useState<SourceArchive | null>(store.known() ?? null);
  const mounted = useRef(true);
  const refresh = useCallback(() => {
    void store.read().then((value) => {
      if (mounted.current && value !== undefined) setArchive(value);
    });
  }, []);
  useEffect(() => {
    mounted.current = true;
    refresh();
    return () => {
      mounted.current = false;
    };
  }, [refresh]);
  return { archive, refresh };
}
