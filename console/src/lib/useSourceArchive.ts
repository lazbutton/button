import { useCallback, useEffect, useRef, useState } from "react";
import { readSourceArchive, type SourceArchive } from "../api/sourceCode";

// L'archive ne change qu'avec l'image de la console : une réponse sûre vaut jusqu'au
// rechargement de la page. undefined : pas encore de réponse sûre.
let known: SourceArchive | null | undefined;
let reading: Promise<SourceArchive | null> | null = null;

function read(): Promise<SourceArchive | null> {
  reading ??= readSourceArchive().then((result) => {
    reading = null;
    if (!result.retry) known = result.archive;
    return result.archive;
  });
  return reading;
}

/**
 * L'archive du code que sert la station (api/sourceCode.ts), ou null : absente, ou pas
 * encore lue. `refresh` relit, tant que la console n'a pas eu de réponse sûre.
 */
export function useSourceArchive(): { archive: SourceArchive | null; refresh: () => void } {
  const [archive, setArchive] = useState<SourceArchive | null>(known ?? null);
  const mounted = useRef(true);
  const refresh = useCallback(() => {
    if (known !== undefined) {
      setArchive(known);
      return;
    }
    void read().then((value) => {
      if (mounted.current) setArchive(value);
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
